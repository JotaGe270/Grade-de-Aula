using System.Security.Claims;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Identity;
using Npgsql;
using Microsoft.AspNetCore.RateLimiting;
using System.Threading.RateLimiting;

var builder = WebApplication.CreateBuilder(args);
builder.Configuration.AddJsonFile("appsettings.Local.json",optional:true).AddJsonFile("appsettings.Testing.json",optional:true).AddEnvironmentVariables();
builder.Services.AddAuthentication("Cookies").AddCookie(o => {
    o.Cookie.Name="grade.session"; o.Cookie.HttpOnly=true; o.Cookie.SameSite=SameSiteMode.Strict; o.ExpireTimeSpan=TimeSpan.FromHours(8);
    o.Events.OnRedirectToLogin=c=>{c.Response.StatusCode=401;return Task.CompletedTask;};
    o.Events.OnRedirectToAccessDenied=c=>{c.Response.StatusCode=403;return Task.CompletedTask;};
});
builder.Services.AddAuthorization(); builder.Services.AddSingleton<Database>();
builder.Services.AddRateLimiter(options=>{
    options.RejectionStatusCode=429;
    options.AddPolicy("login",ctx=>RateLimitPartition.GetFixedWindowLimiter(ctx.Connection.RemoteIpAddress?.ToString()??"local",_=>new FixedWindowRateLimiterOptions{PermitLimit=12,Window=TimeSpan.FromMinutes(1),QueueLimit=0}));
    options.AddPolicy("register",ctx=>RateLimitPartition.GetFixedWindowLimiter(ctx.Connection.RemoteIpAddress?.ToString()??"local",_=>new FixedWindowRateLimiterOptions{PermitLimit=6,Window=TimeSpan.FromMinutes(1),QueueLimit=0}));
});
var app=builder.Build();
app.Use(async (ctx,next)=>{
    ctx.Response.Headers["X-Content-Type-Options"]="nosniff";
    ctx.Response.Headers["Content-Security-Policy"]="default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'";
    if(ctx.Request.Path.StartsWithSegments("/api")) {
        ctx.Response.Headers.CacheControl="no-store";
        if(ctx.Request.Method!="GET" && ctx.Request.Headers["X-Requested-With"]!="GradeAcademica") {ctx.Response.StatusCode=400;await ctx.Response.WriteAsJsonAsync(new{error="Requisição inválida."});return;}
    }
    try{await next();}
    catch(RuleException e){ctx.Response.StatusCode=400;await ctx.Response.WriteAsJsonAsync(new{error=e.Message});}
    catch(PostgresException e) when(e.SqlState is "23505" or "23503" or "23514" or "P0001"){ctx.Response.StatusCode=400;await ctx.Response.WriteAsJsonAsync(new{error=e.SqlState=="P0001"?e.MessageText:"Dados duplicados, inválidos ou referência inexistente."});}
    catch(Exception e){app.Logger.LogError(e,"Erro na operação");ctx.Response.StatusCode=503;await ctx.Response.WriteAsJsonAsync(new{error="Confira a configuração e a conexão com o PostgreSQL."});}
});
app.UseDefaultFiles();app.UseStaticFiles();app.UseAuthentication();app.UseAuthorization();app.UseRateLimiter();
app.MapGet("/api/status",async(Database db,HttpContext ctx)=>{if(db.Configured)await db.Initialize();return new{configured=db.Configured,application="GradeAcademica",version="1.0",testLogin=TestShortcutAllowed(ctx)};});
app.MapPost("/api/test/coordinator-login",async(HttpContext ctx,Database db)=>{
    if(!TestShortcutAllowed(ctx))return Results.NotFound();
    var user=(await db.Query("SELECT email,senha_hash FROM grade_app.usuario WHERE role='coordenador' ORDER BY id_usuario LIMIT 1")).FirstOrDefault();
    var password=builder.Configuration["Bootstrap:Password"];
    if(user==null||string.IsNullOrWhiteSpace(password)||new PasswordHasher<object>().VerifyHashedPassword(new object(),(string)user["senha_hash"]!,password)==PasswordVerificationResult.Failed)
        return Results.BadRequest(new{error="O atalho não está disponível: a senha inicial do coordenador foi alterada."});
    return Results.Ok(new{email=user["email"],password});
}).RequireRateLimiting("login");
app.MapPost("/api/register",async(Register x,Database db)=>{
    Required(x.Name);
    if(x.Password.Length<10 || x.Password.Length>200)throw new RuleException("Use uma senha de 10 a 200 caracteres.");
    var account=await db.CreateAccount(x.Name.Trim(),x.Password,"professor",x.Titulacao??"");
    return Results.Ok(new{message="Conta criada. Guarde sua matrícula e entre com o e-mail abaixo.",email=account["email"],matricula=account["matricula_funcional"]});
}).RequireRateLimiting("register");
app.MapPost("/api/login",async(Login x,HttpContext ctx,Database db)=>{
    var u=(await db.Query("SELECT * FROM grade_app.usuario WHERE email=@p0 OR matricula_funcional=@p0",x.Email.Trim().ToLowerInvariant())).FirstOrDefault();
    if(u==null || new PasswordHasher<object>().VerifyHashedPassword(new object(),(string)u["senha_hash"]!,x.Password)==PasswordVerificationResult.Failed)return Results.Json(new{error="E-mail ou senha inválidos."},statusCode:401);
    await ctx.SignInAsync("Cookies",new ClaimsPrincipal(new ClaimsIdentity(new[]{new Claim(ClaimTypes.NameIdentifier,u["id_usuario"]!.ToString()!),new Claim(ClaimTypes.Name,(string)u["nome"]!),new Claim(ClaimTypes.Role,(string)u["role"]!)},"Cookies")));return Results.Ok();
}).RequireRateLimiting("login");
app.MapPost("/api/logout",async(HttpContext ctx)=>{await ctx.SignOutAsync();return Results.Ok();}).RequireAuthorization();
app.MapGet("/api/me",async(HttpContext ctx,Database db)=>{
    var u=(await db.Query("SELECT u.*,(SELECT nome FROM grade_app.curso WHERE id_coordenador=u.id_usuario) curso FROM grade_app.usuario u WHERE id_usuario=@p0",UserId(ctx)))[0];
    return new{id=u["id_usuario"],name=u["nome"],role=u["role"],email=u["email"],matricula=u["matricula_funcional"],titulacao=u["titulacao"],course=u["curso"]};
}).RequireAuthorization();
app.MapPost("/api/profile",async(Profile x,HttpContext c,Database db)=>{
    Required(x.Name);if((x.Titulacao??"").Length>100)throw new RuleException("Titulação deve ter até 100 caracteres.");
    await db.Query("UPDATE grade_app.usuario SET nome=@p0,titulacao=@p1 WHERE id_usuario=@p2",x.Name.Trim(),x.Titulacao??"",UserId(c));return Results.Ok();
}).RequireAuthorization();
app.MapPost("/api/password",async(PasswordChange x,HttpContext c,Database db)=>{
    if(x.Password.Length<10||x.Password.Length>200)throw new RuleException("Use senha de 10 a 200 caracteres.");
    var u=(await db.Query("SELECT senha_hash FROM grade_app.usuario WHERE id_usuario=@p0",UserId(c)))[0];
    var hasher=new PasswordHasher<object>();if(hasher.VerifyHashedPassword(new object(),(string)u["senha_hash"]!,x.Current)==PasswordVerificationResult.Failed)throw new RuleException("Senha atual incorreta.");
    await db.Query("UPDATE grade_app.usuario SET senha_hash=@p0 WHERE id_usuario=@p1",hasher.HashPassword(new object(),x.Password),UserId(c));await c.SignOutAsync();return Results.Ok();
}).RequireAuthorization();
app.MapGet("/api/data",async(HttpContext ctx,Database db)=>{
    var id=UserId(ctx);var coord=ctx.User.IsInRole("coordenador");var owner=coord?"id_coordenador":"id_professor";
    var courses=await db.Query("SELECT * FROM grade_app.curso WHERE id_coordenador=@p0 ORDER BY nome",id);
    var semesters=await db.Query("SELECT * FROM grade_app.sistema_letivo ORDER BY ano DESC,semestre DESC");
    var classes=await db.Query("SELECT t.*,c.nome curso,l.ano,l.semestre FROM grade_app.turma t JOIN grade_app.curso c USING(id_curso) JOIN grade_app.sistema_letivo l USING(id_sistema_letivo) WHERE c.id_coordenador=@p0 ORDER BY l.ano DESC,l.semestre DESC,t.periodo",id);
    var disciplines=await db.Query("SELECT d.*,t.periodo,t.turno,c.nome curso,l.ano,l.semestre FROM grade_app.disciplina d JOIN grade_app.turma t USING(id_turma) JOIN grade_app.curso c USING(id_curso) JOIN grade_app.sistema_letivo l USING(id_sistema_letivo) WHERE c.id_coordenador=@p0 ORDER BY d.nome",id);
    var invitations=await db.Query($"SELECT i.*,u.nome professor,u.matricula_funcional,d.nome disciplina,d.slots_semanais,t.id_turma,t.periodo,t.turno,t.id_sistema_letivo,c.nome curso,l.ano,l.semestre FROM grade_app.convite_docente i JOIN grade_app.usuario u ON u.id_usuario=i.id_professor JOIN grade_app.disciplina d USING(id_disciplina) JOIN grade_app.turma t USING(id_turma) JOIN grade_app.curso c USING(id_curso) JOIN grade_app.sistema_letivo l USING(id_sistema_letivo) WHERE {(coord?"c.id_coordenador=@p0":"i.id_professor=@p0")} ORDER BY i.id_convite DESC",id);
    var slots=await db.Query("SELECT * FROM grade_app.slot ORDER BY dia_semana,hora_inicio");
    var availability=await db.Query($"SELECT a.* FROM grade_app.disponibilidade a JOIN grade_app.convite_docente i USING(id_convite) JOIN grade_app.disciplina d USING(id_disciplina) JOIN grade_app.turma t USING(id_turma) JOIN grade_app.curso c USING(id_curso) WHERE {(coord?"c.id_coordenador=@p0":"i.id_professor=@p0")}",id);
    var grades=await db.Query("SELECT g.*,t.periodo,t.turno,c.nome curso,l.ano,l.semestre FROM grade_app.grade g JOIN grade_app.turma t USING(id_turma) JOIN grade_app.curso c USING(id_curso) JOIN grade_app.sistema_letivo l USING(id_sistema_letivo) WHERE c.id_coordenador=@p0 ORDER BY g.id_grade DESC",id);
    var allocations=await db.Query($"SELECT a.*,g.status grade_status,g.id_turma,g.versao,i.id_professor,u.nome professor,d.nome disciplina,t.periodo,t.turno,c.nome curso,l.ano,l.semestre,s.dia_semana,s.hora_inicio,s.hora_fim FROM grade_app.alocacao_grade a JOIN grade_app.grade g USING(id_grade) JOIN grade_app.convite_docente i USING(id_convite) JOIN grade_app.usuario u ON u.id_usuario=i.id_professor JOIN grade_app.disciplina d USING(id_disciplina) JOIN grade_app.turma t ON t.id_turma=g.id_turma JOIN grade_app.curso c USING(id_curso) JOIN grade_app.sistema_letivo l USING(id_sistema_letivo) JOIN grade_app.slot s USING(id_slot) WHERE {(coord?"c.id_coordenador=@p0":"i.id_professor=@p0 AND g.status='publicada'")} ORDER BY l.ano DESC,l.semestre DESC,s.dia_semana,s.hora_inicio",id);
    var availabilityConflicts=await db.Query($"SELECT DISTINCT target.id_convite,a.id_slot,d.nome disciplina FROM grade_app.convite_docente target JOIN grade_app.disciplina td ON td.id_disciplina=target.id_disciplina JOIN grade_app.turma tt ON tt.id_turma=td.id_turma JOIN grade_app.curso tc ON tc.id_curso=tt.id_curso JOIN grade_app.convite_docente booked ON booked.id_professor=target.id_professor AND booked.id_convite<>target.id_convite JOIN grade_app.disciplina d ON d.id_disciplina=booked.id_disciplina JOIN grade_app.alocacao_grade a ON a.id_convite=booked.id_convite JOIN grade_app.grade g ON g.id_grade=a.id_grade AND g.status='publicada' JOIN grade_app.turma bt ON bt.id_turma=g.id_turma AND bt.id_sistema_letivo=tt.id_sistema_letivo WHERE {(coord?"tc.id_coordenador=@p0":"target.id_professor=@p0")}",id);
    return new{courses,semesters,classes,disciplines,invitations,slots,availability,grades,allocations,availabilityConflicts};
}).RequireAuthorization();
app.MapGet("/api/professors",async(string q,Database db)=>{
    if(q.Trim().Length<2)return new List<Dictionary<string,object?>>();
    return await db.Query("SELECT id_usuario,nome,matricula_funcional,titulacao FROM grade_app.usuario WHERE role='professor' AND (nome ILIKE @p0 OR matricula_funcional ILIKE @p0) ORDER BY nome LIMIT 30","%"+q.Trim()+"%");
}).RequireAuthorization(p=>p.RequireRole("coordenador"));

app.MapPost("/api/semesters",async(Semester x,Database db)=>await db.Query("INSERT INTO grade_app.sistema_letivo(ano,semestre) VALUES(@p0,@p1) ON CONFLICT(ano,semestre) DO NOTHING",x.Year,x.Number)).RequireAuthorization(p=>p.RequireRole("coordenador"));
app.MapPost("/api/classes",async(ClassInput x,HttpContext c,Database db)=>{
    if(x.Period<1)throw new RuleException("Informe um período inteiro positivo.");
    await db.Transaction(async tx=>{
        var r=await tx.Query("INSERT INTO grade_app.turma(periodo,turno,id_curso,id_sistema_letivo) SELECT @p0,@p1,id_curso,@p2 FROM grade_app.curso WHERE id_coordenador=@p3 RETURNING id_turma",x.Period.ToString(),x.Shift,x.Semester,UserId(c));
        if(r.Count==0)throw new RuleException("Curso não autorizado.");
        await tx.Query("INSERT INTO grade_app.grade(id_turma,versao,status) VALUES(@p0,1,'rascunho')",r[0]["id_turma"]!);
    });return Results.Ok();
}).RequireAuthorization(p=>p.RequireRole("coordenador"));
app.MapPost("/api/disciplines",async(Discipline x,HttpContext c,Database db)=>{
    Required(x.Name);
    var r=await db.Query("INSERT INTO grade_app.disciplina(nome,carga_horaria,slots_semanais,id_turma) SELECT @p0,@p1,@p2,t.id_turma FROM grade_app.turma t JOIN grade_app.curso c USING(id_curso) WHERE t.id_turma=@p3 AND c.id_coordenador=@p4 RETURNING *",x.Name.Trim(),x.Workload,x.WeeklySlots,x.Class,UserId(c));
    if(r.Count==0)throw new RuleException("Turma não autorizada.");return r;
}).RequireAuthorization(p=>p.RequireRole("coordenador"));
app.MapPut("/api/disciplines/{id:int}",async(int id,Discipline x,HttpContext c,Database db)=>{
    Required(x.Name);
    if(x.Workload<1||x.WeeklySlots<1||x.WeeklySlots>24)throw new RuleException("Informe carga horária positiva e entre 1 e 24 aulas semanais.");
    await db.Transaction(async tx=>{
        var rows=await tx.Query("SELECT d.* FROM grade_app.disciplina d JOIN grade_app.turma t USING(id_turma) JOIN grade_app.curso c USING(id_curso) WHERE d.id_disciplina=@p0 AND c.id_coordenador=@p1",id,UserId(c));
        if(rows.Count==0)throw new RuleException("Disciplina não autorizada.");
        var target=await tx.Query("SELECT t.id_turma FROM grade_app.turma t JOIN grade_app.curso c USING(id_curso) WHERE t.id_turma=@p0 AND c.id_coordenador=@p1",x.Class,UserId(c));
        if(target.Count==0)throw new RuleException("Turma não autorizada.");
        if(Convert.ToInt32(rows[0]["id_turma"])!=x.Class&&(await tx.Query("SELECT 1 FROM grade_app.convite_docente WHERE id_disciplina=@p0 LIMIT 1",id)).Count>0)
            throw new RuleException("Não é possível trocar a turma de uma disciplina que já possui convites.");
        if(Convert.ToInt32(rows[0]["slots_semanais"])!=x.WeeklySlots){
            if((await tx.Query("SELECT 1 FROM grade_app.alocacao_grade a JOIN grade_app.grade g USING(id_grade) JOIN grade_app.convite_docente i USING(id_convite) WHERE i.id_disciplina=@p0 AND g.status='publicada' LIMIT 1",id)).Count>0)
                throw new RuleException("A quantidade semanal não pode ser alterada enquanto a disciplina tem uma grade publicada.");
            if((await tx.Query("SELECT g.id_grade FROM grade_app.alocacao_grade a JOIN grade_app.grade g USING(id_grade) JOIN grade_app.convite_docente i USING(id_convite) WHERE i.id_disciplina=@p0 AND g.status='rascunho' GROUP BY g.id_grade HAVING count(*)>@p1",id,x.WeeklySlots)).Count>0)
                throw new RuleException("Remova as aulas excedentes do rascunho antes de reduzir a quantidade semanal.");
        }
        await tx.Query("UPDATE grade_app.disciplina SET nome=@p0,carga_horaria=@p1,slots_semanais=@p2,id_turma=@p3 WHERE id_disciplina=@p4",x.Name.Trim(),x.Workload,x.WeeklySlots,x.Class,id);
    });
    return Results.Ok();
}).RequireAuthorization(p=>p.RequireRole("coordenador"));
app.MapPost("/api/invitations",async(Invite x,HttpContext c,Database db)=>{
    var r=await db.Query("INSERT INTO grade_app.convite_docente(id_coordenador,id_professor,id_disciplina) SELECT @p0,u.id_usuario,d.id_disciplina FROM grade_app.disciplina d JOIN grade_app.turma t USING(id_turma) JOIN grade_app.curso c USING(id_curso) CROSS JOIN grade_app.usuario u WHERE d.id_disciplina=@p1 AND c.id_coordenador=@p0 AND u.id_usuario=@p2 AND u.role='professor' RETURNING *",UserId(c),x.Discipline,x.Professor);
    if(r.Count==0)throw new RuleException("Disciplina ou professor inválido.");return r;
}).RequireAuthorization(p=>p.RequireRole("coordenador"));
app.MapPost("/api/invitations/{id:int}/reply",async(int id,Reply x,HttpContext c,Database db)=>{
    if(x.Status is not("aceito" or "recusado"))throw new RuleException("Resposta inválida.");
    var r=await db.Query("UPDATE grade_app.convite_docente SET status=@p0,data_resposta=now() WHERE id_convite=@p1 AND id_professor=@p2 AND status='pendente' RETURNING *",x.Status,id,UserId(c));
    if(r.Count==0)throw new RuleException("Convite indisponível.");return r;
}).RequireAuthorization(p=>p.RequireRole("professor"));
app.MapPost("/api/invitations/{id:int}/cancel",async(int id,HttpContext c,Database db)=>{
    await db.Transaction(async tx=>{
        if((await tx.Query("SELECT 1 FROM grade_app.convite_docente i JOIN grade_app.disciplina d USING(id_disciplina) JOIN grade_app.turma t USING(id_turma) JOIN grade_app.curso c USING(id_curso) WHERE id_convite=@p0 AND c.id_coordenador=@p1 AND i.status IN ('pendente','aceito')",id,UserId(c))).Count==0)throw new RuleException("Convite indisponível.");
        if((await tx.Query("SELECT 1 FROM grade_app.alocacao_grade WHERE id_convite=@p0",id)).Count>0)throw new RuleException("Remova as alocações antes de cancelar o convite.");
        await tx.Query("UPDATE grade_app.convite_docente SET status='cancelado' WHERE id_convite=@p0",id);
    });return Results.Ok();
}).RequireAuthorization(p=>p.RequireRole("coordenador"));
app.MapPost("/api/invitations/{id:int}/availability",async(int id,Availability x,HttpContext c,Database db)=>{
    await db.Transaction(async tx=>{
        var r=await tx.Query("SELECT t.turno FROM grade_app.convite_docente i JOIN grade_app.disciplina d USING(id_disciplina) JOIN grade_app.turma t USING(id_turma) WHERE i.id_convite=@p0 AND i.id_professor=@p1 AND i.status='aceito'",id,UserId(c));
        if(r.Count==0)throw new RuleException("Aceite o convite antes de informar disponibilidade.");
        var slots=x.Slots.Distinct().ToArray();if(slots.Length==0)throw new RuleException("Selecione pelo menos um horário.");
        var conflicts=await tx.Query("SELECT a.id_slot FROM grade_app.convite_docente target JOIN grade_app.disciplina td ON td.id_disciplina=target.id_disciplina JOIN grade_app.turma tt ON tt.id_turma=td.id_turma JOIN grade_app.convite_docente booked ON booked.id_professor=target.id_professor AND booked.id_convite<>target.id_convite JOIN grade_app.alocacao_grade a ON a.id_convite=booked.id_convite JOIN grade_app.grade g ON g.id_grade=a.id_grade AND g.status='publicada' JOIN grade_app.turma bt ON bt.id_turma=g.id_turma AND bt.id_sistema_letivo=tt.id_sistema_letivo WHERE target.id_convite=@p0",id);
        if(conflicts.Any(a=>slots.Contains(Convert.ToInt32(a["id_slot"]))))throw new RuleException("Conflito: você já tem aula em uma grade finalizada nesse horário. Atualize a disponibilidade e retire os horários em amarelo.");
        foreach(var slot in slots)if((await tx.Query("SELECT 1 FROM grade_app.slot WHERE id_slot=@p0 AND turno=@p1",slot,r[0]["turno"]!)).Count==0)throw new RuleException("Horário incompatível com a turma.");
        var allocated=await tx.Query("SELECT a.id_slot FROM grade_app.alocacao_grade a JOIN grade_app.grade g USING(id_grade) WHERE a.id_convite=@p0 AND g.status IN ('rascunho','publicada')",id);
        if(allocated.Any(a=>!slots.Contains(Convert.ToInt32(a["id_slot"]))))throw new RuleException("Há aulas nesses horários. Solicite ao coordenador a alteração da grade antes de removê-los.");
        await tx.Query("DELETE FROM grade_app.disponibilidade WHERE id_convite=@p0",id);
        foreach(var slot in slots)await tx.Query("INSERT INTO grade_app.disponibilidade VALUES(@p0,@p1)",id,slot);
    });return Results.Ok();
}).RequireAuthorization(p=>p.RequireRole("professor"));
app.MapPost("/api/allocations",async(Allocation x,HttpContext c,Database db)=>{
    await db.Transaction(async tx=>{await OwnDraft(tx,x.Grade,UserId(c));await tx.Query("INSERT INTO grade_app.alocacao_grade(id_grade,id_convite,id_slot) VALUES(@p0,@p1,@p2)",x.Grade,x.Invitation,x.Slot);});return Results.Ok();
}).RequireAuthorization(p=>p.RequireRole("coordenador"));
app.MapDelete("/api/allocations/{id:int}",async(int id,HttpContext c,Database db)=>{
    await db.Transaction(async tx=>{var r=await tx.Query("SELECT id_grade FROM grade_app.alocacao_grade WHERE id_alocacao=@p0",id);if(r.Count==0)throw new RuleException("Aula inexistente.");await OwnDraft(tx,Convert.ToInt32(r[0]["id_grade"]),UserId(c));await tx.Query("DELETE FROM grade_app.alocacao_grade WHERE id_alocacao=@p0",id);});return Results.Ok();
}).RequireAuthorization(p=>p.RequireRole("coordenador"));
app.MapPost("/api/grades/{id:int}/publish",async(int id,HttpContext c,Database db)=>{
    await db.Transaction(async tx=>{
        await OwnDraft(tx,id,UserId(c));
        var missing=await tx.Query("SELECT d.nome FROM grade_app.disciplina d JOIN grade_app.grade g USING(id_turma) WHERE g.id_grade=@p0 AND (SELECT count(*) FROM grade_app.alocacao_grade a JOIN grade_app.convite_docente i USING(id_convite) WHERE a.id_grade=g.id_grade AND i.id_disciplina=d.id_disciplina)<>d.slots_semanais",id);
        if(missing.Count>0)throw new RuleException("Complete a quantidade semanal de aulas: "+string.Join(", ",missing.Select(x=>x["nome"])));
        if((await tx.Query("SELECT 1 FROM grade_app.alocacao_grade WHERE id_grade=@p0",id)).Count==0)throw new RuleException("A grade está vazia.");
        await tx.Query("UPDATE grade_app.alocacao_grade SET id_slot=id_slot WHERE id_grade=@p0",id);
        await tx.Query("UPDATE grade_app.grade SET status='arquivada' WHERE id_turma=(SELECT id_turma FROM grade_app.grade WHERE id_grade=@p0) AND status='publicada'",id);
        await tx.Query("UPDATE grade_app.grade SET status='publicada',data_publicacao=now() WHERE id_grade=@p0",id);
        await tx.Query("DELETE FROM grade_app.disponibilidade available USING grade_app.convite_docente target,grade_app.disciplina td,grade_app.turma tt,grade_app.alocacao_grade a,grade_app.convite_docente booked,grade_app.grade g,grade_app.turma bt WHERE available.id_convite=target.id_convite AND td.id_disciplina=target.id_disciplina AND tt.id_turma=td.id_turma AND a.id_grade=@p0 AND booked.id_convite=a.id_convite AND booked.id_professor=target.id_professor AND booked.id_convite<>target.id_convite AND available.id_slot=a.id_slot AND g.id_grade=a.id_grade AND bt.id_turma=g.id_turma AND bt.id_sistema_letivo=tt.id_sistema_letivo",id);
    });return Results.Ok();
}).RequireAuthorization(p=>p.RequireRole("coordenador"));
app.MapPost("/api/grades/{id:int}/revise",async(int id,HttpContext c,Database db)=>{
    await db.Transaction(async tx=>{
        if((await tx.Query("SELECT 1 FROM grade_app.grade g JOIN grade_app.turma t USING(id_turma) JOIN grade_app.curso c USING(id_curso) WHERE g.id_grade=@p0 AND c.id_coordenador=@p1 AND g.status='publicada'",id,UserId(c))).Count==0)throw new RuleException("Grade indisponível para revisão.");
        var r=await tx.Query("INSERT INTO grade_app.grade(id_turma,versao,status) SELECT id_turma,versao+1,'rascunho' FROM grade_app.grade WHERE id_grade=@p0 RETURNING id_grade",id);
        await tx.Query("INSERT INTO grade_app.alocacao_grade(id_grade,id_convite,id_slot) SELECT @p0,id_convite,id_slot FROM grade_app.alocacao_grade WHERE id_grade=@p1",r[0]["id_grade"]!,id);
    });return Results.Ok();
}).RequireAuthorization(p=>p.RequireRole("coordenador"));
app.MapPost("/api/grades/{id:int}/allocations",async(int id,GradeChanges x,HttpContext c,Database db)=>{
    await db.Transaction(async tx=>{
        await OwnDraft(tx,id,UserId(c));
        var current=await tx.Query("SELECT id_alocacao FROM grade_app.alocacao_grade WHERE id_grade=@p0 ORDER BY id_alocacao",id);
        if(!current.Select(a=>Convert.ToInt32(a["id_alocacao"])).SequenceEqual(x.ExpectedIds.Order()))throw new RuleException("A grade foi alterada em outra sessão. Descarte as alterações e tente novamente.");
        if(x.Changes.Select(a=>a.Slot).Distinct().Count()!=x.Changes.Length)throw new RuleException("Horários repetidos.");
        foreach(var change in x.Changes)await tx.Query("DELETE FROM grade_app.alocacao_grade WHERE id_grade=@p0 AND id_slot=@p1",id,change.Slot);
        foreach(var change in x.Changes)if(change.Invitation.HasValue)await tx.Query("INSERT INTO grade_app.alocacao_grade(id_grade,id_convite,id_slot) VALUES(@p0,@p1,@p2)",id,change.Invitation.Value,change.Slot);
    });return Results.Ok();
}).RequireAuthorization(p=>p.RequireRole("coordenador"));
bool TestShortcutAllowed(HttpContext ctx)=>builder.Configuration.GetValue<bool>("Testing:CoordinatorShortcut")&&ctx.Connection.RemoteIpAddress!=null&&System.Net.IPAddress.IsLoopback(ctx.Connection.RemoteIpAddress);
app.Run();

static int UserId(HttpContext c)=>int.Parse(c.User.FindFirstValue(ClaimTypes.NameIdentifier)!);
static void Required(string s){if(string.IsNullOrWhiteSpace(s)||s.Length>150)throw new RuleException("Preencha os campos com até 150 caracteres.");}
static async Task OwnDraft(Database tx,int grade,int user){if((await tx.Query("SELECT 1 FROM grade_app.grade g JOIN grade_app.turma t USING(id_turma) JOIN grade_app.curso c USING(id_curso) WHERE g.id_grade=@p0 AND c.id_coordenador=@p1 AND g.status='rascunho'",grade,user)).Count==0)throw new RuleException("Você só pode editar seus próprios rascunhos.");}
record Login(string Email,string Password);
record Profile(string Name,string? Titulacao);
record PasswordChange(string Current,string Password);
record Register(string Name,string Password,string? Titulacao);

record Semester(int Year,int Number);
record ClassInput(int Period,string Shift,int Semester);
record Discipline(string Name,int Workload,int WeeklySlots,int Class);
record Invite(int Discipline,int Professor);
record Reply(string Status);
record Availability(int[] Slots);
record Allocation(int Grade,int Invitation,int Slot);
record SlotChange(int Slot,int? Invitation);
record GradeChanges(int[] ExpectedIds,SlotChange[] Changes);
class RuleException(string message):Exception(message);
