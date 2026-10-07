using Npgsql;
using Microsoft.AspNetCore.Identity;

class Database {
    readonly string? connectionString;
    readonly string schemaPath;
    readonly IConfiguration config;
    readonly SemaphoreSlim initialization=new(1);
    bool initialized;
    NpgsqlConnection? active;
    public bool Configured=>!string.IsNullOrWhiteSpace(connectionString);
    public Task Initialize()=>Ensure();
    public Database(IConfiguration configuration,IWebHostEnvironment environment){config=configuration;connectionString=config.GetConnectionString("Postgres");schemaPath=Path.Combine(environment.ContentRootPath,"schema.sql");}
    Database(Database parent,NpgsqlConnection conn){config=parent.config;schemaPath=parent.schemaPath;connectionString=parent.connectionString;active=conn;initialized=true;}
    async Task Ensure(){
        if(initialized)return;
        if(!Configured)throw new RuleException("Configure ConnectionStrings__Postgres para conectar o sistema ao banco.");
        await initialization.WaitAsync();
        try{
            if(initialized)return;
            await using var conn=new NpgsqlConnection(connectionString);await conn.OpenAsync();await using var transaction=await conn.BeginTransactionAsync();
            await Execute(conn,"SELECT pg_advisory_xact_lock(741963)",[]);
            await using var schema=new NpgsqlCommand(await File.ReadAllTextAsync(schemaPath),conn);await schema.ExecuteNonQueryAsync();
            var password=config["Bootstrap:Password"];
            if(!string.IsNullOrWhiteSpace(password)){
                if(password.Length<10)throw new RuleException("A senha inicial precisa ter pelo menos 10 caracteres.");
                var existing=await Execute(conn,"SELECT 1 FROM grade_app.usuario WHERE role='coordenador'",[]);
                if(existing.Count==0)await InsertAccount(conn,config["Bootstrap:Name"]??"Coordenador",password,"coordenador","");
            }
            var coordinator=await Execute(conn,"SELECT id_usuario FROM grade_app.usuario WHERE role='coordenador' ORDER BY id_usuario LIMIT 1",[]);
            if(coordinator.Count>0)await Execute(conn,"INSERT INTO grade_app.curso(nome,id_coordenador) SELECT @p0,@p1 WHERE NOT EXISTS(SELECT 1 FROM grade_app.curso WHERE id_coordenador=@p1)",[config["Bootstrap:Course"]??"Engenharia de Software",coordinator[0]["id_usuario"]!]);
            await transaction.CommitAsync();initialized=true;
        }finally{initialization.Release();}
    }
    public async Task<List<Dictionary<string,object?>>> Query(string sql,params object[] values){
        await Ensure();if(active!=null)return await Execute(active,sql,values);
        await using var conn=new NpgsqlConnection(connectionString);await conn.OpenAsync();return await Execute(conn,sql,values);
    }
    static async Task<List<Dictionary<string,object?>>> Execute(NpgsqlConnection conn,string sql,object[] values){
        await using var cmd=new NpgsqlCommand(sql,conn);for(var i=0;i<values.Length;i++)cmd.Parameters.AddWithValue("p"+i,values[i]);
        await using var reader=await cmd.ExecuteReaderAsync();var rows=new List<Dictionary<string,object?>>();
        while(await reader.ReadAsync()){var row=new Dictionary<string,object?>();for(var i=0;i<reader.FieldCount;i++){var v=reader.IsDBNull(i)?null:reader.GetValue(i);row[reader.GetName(i)]=v switch{TimeSpan t=>t.ToString(@"hh\:mm"),TimeOnly t=>t.ToString("HH:mm"),_=>v};}rows.Add(row);}return rows;
    }
    public async Task Transaction(Func<Database,Task> action){
        await Ensure();await using var conn=new NpgsqlConnection(connectionString);await conn.OpenAsync();await using var tx=await conn.BeginTransactionAsync();
        await Execute(conn,"SELECT pg_advisory_xact_lock(741963)",[]);await action(new Database(this,conn));await tx.CommitAsync();
    }
    public async Task<Dictionary<string,object?>> CreateAccount(string name,string password,string role,string title){
        await Ensure();await using var conn=new NpgsqlConnection(connectionString);await conn.OpenAsync();return await InsertAccount(conn,name,password,role,title);
    }
    static async Task<Dictionary<string,object?>> InsertAccount(NpgsqlConnection conn,string name,string password,string role,string title){
        var zone=TimeZoneInfo.FindSystemTimeZoneById("America/Sao_Paulo");
        var year=TimeZoneInfo.ConvertTime(DateTimeOffset.UtcNow,zone).Year;
        var hash=new PasswordHasher<object>().HashPassword(new object(),password);
        for(var attempt=0;attempt<200;attempt++){
            var matricula=year.ToString()+System.Security.Cryptography.RandomNumberGenerator.GetInt32(10000).ToString("D4");
            var rows=await Execute(conn,"INSERT INTO grade_app.usuario(nome,email,senha_hash,role,matricula_funcional,titulacao) VALUES(@p0,@p1,@p2,@p3,@p4,@p5) ON CONFLICT DO NOTHING RETURNING id_usuario,nome,email,matricula_funcional",[name,matricula+"@ugb.com.br",hash,role,matricula,title]);
            if(rows.Count>0)return rows[0];
        }
        throw new RuleException("Não foi possível gerar uma matrícula disponível. Tente novamente.");
    }
}
