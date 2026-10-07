const root=document.getElementById('root');
let me=null,data=null,page='painel',selectedProfessor=null,gradeId=null,activeInvitation=null,gradeInvitation=null,savingSlot=false;
const gradeEdits=new Map();
let editingDiscipline=null;
window.addEventListener('beforeunload',event=>{if([...gradeEdits.values()].some(x=>x.changes.size)){event.preventDefault();event.returnValue='';}});
const days=['','Segunda','Terça','Quarta','Quinta','Sexta','Sábado'];
const e=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pill=s=>`<span class="pill ${e(s)}">${e(s)}</span>`;
const periodName=value=>parseInt(value,10)+"º período";
const className=t=>`${t.curso} · ${periodName(periodName(t.periodo))} · ${t.turno} · ${t.ano}/${t.semestre}`;
const opts=(list,id,label)=>list.map(x=>`<option value="${x[id]}">${e(label(x))}</option>`).join('');
const field=(label,name,type='text',extra='')=>`<label>${label}<input name="${name}" type="${type}" required ${extra}></label>`;
const select=(label,name,options)=>`<label>${label}<select name="${name}" required><option value="">Selecione</option>${options}</select></label>`;
function toast(text,error=false){const t=document.getElementById('toast');t.textContent=text;t.className=error?'error':'';t.style.display='block';clearTimeout(toast.timer);toast.timer=setTimeout(()=>t.style.display='none',7000);}
async function api(path,body,method){const r=await fetch('/api'+path,{method:method||(body?'POST':'GET'),headers:{'Content-Type':'application/json','X-Requested-With':'GradeAcademica'},body:body?JSON.stringify(body):undefined});let j=await r.text();try{j=j?JSON.parse(j):null;}catch{j=null;}if(!r.ok){if(r.status===401&&me){me=null;login();}throw Error(j?.error||(r.status===429?'Muitas tentativas. Aguarde um minuto e tente novamente.':r.status===403?'Acesso não autorizado.':'Não foi possível concluir a operação.'));}return j;}
function bindForms(){document.querySelectorAll('form[data-form]').forEach(f=>f.onsubmit=async ev=>{ev.preventDefault();const b=f.querySelector('button[type=submit]');if(b)b.disabled=true;try{await submit(f.dataset.form,Object.fromEntries(new FormData(f)),f);}catch(err){toast(err.message,true);}finally{if(b)b.disabled=false;}});}
document.addEventListener('click',async ev=>{const b=ev.target.closest('[data-action]');if(!b)return;try{await action(b.dataset.action,b.dataset.id,b);}catch(err){toast(err.message,true);}});
function login(register=false){root.innerHTML=`<div class="login"><section class="intro"><div class="brand">UGB<span> / acadêmico</span></div><h1>Uma grade organizada.<br>Mais espaço para ensinar.</h1><p>Convites, disponibilidade e aulas em um só lugar. Planeje cada semestre em colaboração com seus professores.</p><div class="eyebrow">Gestão de grade acadêmica</div></section><section class="loginbox"><div class="card"><div class="eyebrow">${register?'Novo professor':'Bem-vindo de volta'}</div><h2 class="section-title">${register?'Crie sua conta':'Entre na sua conta'}</h2><p class="muted small">${register?'Sua matrícula de 8 dígitos e seu e-mail UGB serão gerados automaticamente.':'Use seu e-mail institucional ou matrícula.'}</p><form data-form="${register?'register':'login'}" class="stack">${register?field('Nome completo','name'):field('E-mail ou matrícula','email','text','autocomplete="username"')}${field('Senha','password','password',`minlength="10" maxlength="200" autocomplete="${register?'new-password':'current-password'}"`)}<button type="submit">${register?'Cadastrar professor':'Entrar'}</button></form><button class="link" data-action="${register?'login':'register'}">${register?'Já tenho conta':'Sou professor e quero criar minha conta'}</button>${register?'':'<button type="button" id="coordinator-test-login" class="secondary" data-action="fill-coordinator" hidden>Preencher login do coordenador · teste</button>'}<div id="login-info"></div></div></section></div>`;bindForms();if(!register)api('/status').then(s=>{const b=document.getElementById('coordinator-test-login');if(b)b.hidden=!s.testLogin;}).catch(()=>{});}
async function load(){data=await api('/data');render();}
function render(){const coord=me.role==='coordenador';const pending=data.invitations.filter(i=>i.status==='pendente').length;const nav=coord?[['painel','Visão geral'],['cadastros','Turmas e semestres'],['disciplinas','Disciplinas'],['convites',`Convites · ${pending}`],['grade','Montagem da grade'],['perfil','Meu perfil']]:[['painel','Visão geral'],['convites',`Meus convites · ${pending}`],['aulas','Minhas aulas'],['perfil','Meu perfil']];root.innerHTML=`<div class="layout"><aside><div class="brand">UGB<span> / grade</span></div><nav>${nav.map(([id,label])=>`<button data-action="nav" data-id="${id}" class="${page===id?'active':''}">${label}</button>`).join('')}</nav><footer>Planejamento acadêmico<br>Manhã e noite · aulas de 50 min</footer></aside><main><header class="row spread"><div><div class="eyebrow">${coord?'Área do coordenador':'Área do professor'}</div><h1 class="section-title">${e(nav.find(n=>n[0]===page)?.[1].split(' · ')[0]||'Visão geral')}</h1></div><div class="row"><div class="avatar">${e(me.name[0])}</div><div><strong>${e(me.name)}</strong><div class="muted small">${coord?'Coordenador':'Professor'}</div></div><button class="secondary" data-action="logout">Sair</button></div></header><div id="content">${content(coord,pending)}</div></main></div>`;bindForms();bindGrade();bindDashboard();bindDiscipline();}
function content(coord,pending){
 if(page==='painel'){
  if(coord){
   const counts={faltando:0,andamento:0,concluidas:0};
   for(const turma of data.classes){
    const grades=data.grades.filter(g=>g.id_turma===turma.id_turma);
    const draft=grades.find(g=>g.status==='rascunho'),published=grades.find(g=>g.status==='publicada');
    if(draft&&(published||data.allocations.some(a=>a.id_grade===draft.id_grade)))counts.andamento++;
    else if(published)counts.concluidas++;
    else counts.faltando++;
   }
   return `<div class="grid stats">${[[data.classes.length,'Turmas'],[counts.faltando,'Grades faltando'],[counts.andamento,'Grades em andamento'],[counts.concluidas,'Grades concluídas']].map(([n,t])=>`<div class="card stat"><span class="muted small">${t}</span><strong>${n}</strong></div>`).join('')}</div>`;
  }
  return `<div class="card section row spread"><div><h2>Convites pendentes</h2><p class="muted">${pending?pending+' convite(s) aguardando sua resposta.':'Você não tem convites pendentes.'}</p></div>${pending?'<button data-action="nav" data-id="convites">Ver convites</button>':''}</div><div class="card"><h2>Minha grade da semana</h2><div class="filters"><label>Semestre letivo<select id="dashboard-semester"></select></label></div><div id="dashboard-week"></div></div>`;
 }
 if(page==='cadastros')return `<div class="banner"><h2>${e(data.courses[0]?.nome||'Curso não vinculado')}</h2><p class="muted">Você gerencia as turmas e disciplinas deste curso.</p></div><div class="grid"><div class="card"><h2>Semestre letivo</h2><form data-form="semesters" class="stack">${field('Ano','year','number','min="2000" max="2200" value="'+new Date().getFullYear()+'"')}${select('Semestre','number','<option value="1">1º semestre</option><option value="2">2º semestre</option>')}<button type="submit">Criar semestre</button></form></div><div class="card"><h2>Nova turma</h2><form data-form="classes" class="stack">${select('Semestre','semester',opts(data.semesters,'id_sistema_letivo',x=>x.ano+'/'+x.semestre))}${select('Período do curso','period',Array.from({length:8},(_,i)=>'<option value="'+(i+1)+'">'+(i+1)+'º período · Eng. Soft</option>').join(''))}${select('Turno','shift','<option value="matutino">Matutino · 08:10–11:50</option><option value="noturno">Noturno · 19:10–22:50</option>')}<button type="submit">Criar turma</button></form></div></div><h2 class="section-title">Turmas cadastradas</h2><div class="grid">${data.classes.map(t=>`<div class="card"><h3>${e(t.curso)}</h3><p>${e(periodName(t.periodo))} · ${e(t.turno)}</p><span class="pill">${t.ano}/${t.semestre}</span></div>`).join('')||empty('Cadastre um semestre e sua primeira turma.')}</div>`;
 if(page==='disciplinas')return `<div class="card section"><h2>${editingDiscipline?'Editar disciplina':'Disciplina para uma turma'}</h2><form data-form="${editingDiscipline?'edit-disciplines':'disciplines'}" class="formgrid">${select('Turma','class',opts(data.classes,'id_turma',className))}${field('Nome','name')}${field('Carga horária total','workload','number','min="1"')}${field('Aulas de 50 minutos por semana','weeklySlots','number','min="1" max="24" value="2"')}<div><p class="small muted">Defina explicitamente as aulas semanais. A carga horária total não é convertida automaticamente.</p><button type="submit">${editingDiscipline?'Salvar alterações':'Criar disciplina'}</button>${editingDiscipline?'<button type="button" class="secondary" data-action="cancel-discipline-edit">Cancelar edição</button>':''}</div></form></div><div class="card tablewrap"><table><thead><tr><th>Disciplina</th><th>Turma / semestre</th><th>Carga horária</th><th>Aulas semanais</th><th>Ações</th></tr></thead><tbody>${data.disciplines.map(d=>`<tr><td><strong>${e(d.nome)}</strong></td><td>${e(className(d))}</td><td>${d.carga_horaria}</td><td>${d.slots_semanais}</td><td><button class="secondary" data-action="edit-discipline" data-id="${d.id_disciplina}">Editar</button></td></tr>`).join('')}</tbody></table>${!data.disciplines.length?empty('Nenhuma disciplina cadastrada.') :''}</div>`;
 if(page==='convites')return `${coord?inviteForm():''}<div class="grid">${data.invitations.map(i=>`<article class="card"><div class="row spread"><h3>${e(i.disciplina)}</h3>${pill(i.status)}</div><p class="muted small">${e(className(i))}</p><p>${e(i.professor)} <span class="muted small">· ${e(i.matricula_funcional)}</span></p><div class="small muted">${i.slots_semanais} aula(s) por semana · ${data.availability.filter(a=>a.id_convite===i.id_convite).length} horários disponíveis</div><div class="actions">${!coord&&i.status==='pendente'?`<button data-action="accept" data-id="${i.id_convite}">Aceitar</button><button class="secondary" data-action="reject" data-id="${i.id_convite}">Recusar</button>`:''}${i.status==='aceito'?`<button class="secondary" data-action="availability" data-id="${i.id_convite}">${coord?'Ver disponibilidade':'Informar disponibilidade'}</button>`:''}${coord&&['pendente','aceito'].includes(i.status)?`<button class="danger" data-action="cancel" data-id="${i.id_convite}">Cancelar convite</button>`:''}</div></article>`).join('')||empty('Nenhum convite por enquanto.')}</div><div id="availability-panel"></div>`;
 if(page==='grade')return gradeView();
 if(page==='aulas')return lessons();
 if(page==='perfil')return `<div class="card"><h2>Meu perfil</h2><form data-form="profile" class="stack">${field('Nome completo','name','text',`value="${e(me.name)}"`)}<label>Titulação<input name="titulacao" value="${e(me.titulacao)}" maxlength="100"></label><p class="muted">Matrícula: <strong>${e(me.matricula)}</strong><br>E-mail: ${e(me.email)}</p><button type="submit">Salvar perfil</button></form></div><div class="card section-title"><h2>Alterar senha</h2><form data-form="password" class="stack">${field('Senha atual','current','password','autocomplete="current-password"')}${field('Nova senha','password','password','minlength="10" maxlength="200" autocomplete="new-password"')}<button type="submit">Alterar senha</button></form></div>`;
 return '';
}
function empty(text){return `<div class="empty">${e(text)}</div>`;}
function inviteForm(){
 const groups=data.classes.map(turma=>{
  const disciplines=data.disciplines.filter(d=>d.id_turma===turma.id_turma);
  return `<details class="course-group" name="invite-classes"><summary><span>${e(periodName(turma.periodo))} · ${e(turma.turno)} · ${turma.ano}/${turma.semestre}</span><span class="course-count">${disciplines.length} disciplina(s)</span></summary><div class="course-disciplines">${disciplines.map(d=>`<label class="discipline-option"><input type="radio" name="discipline" value="${d.id_disciplina}"><span><strong>${e(d.nome)}</strong><span class="small muted">${d.slots_semanais} aula(s) por semana</span></span></label>`).join('')||'<p class="muted small">Nenhuma disciplina cadastrada para esta turma.</p>'}</div></details>`;
 }).join('');
 return `<div class="card section"><h2>Convidar professor cadastrado</h2><form data-form="invitations" class="stack"><fieldset class="course-picker"><legend>Selecione a turma e a disciplina</legend><p class="muted small">Abra o período e turno desejados para escolher a disciplina.</p><div class="course-list">${groups||empty('Cadastre uma turma e suas disciplinas para enviar convites.')}</div><p id="selected-discipline" class="selected-discipline" aria-live="polite">Nenhuma disciplina selecionada.</p></fieldset><label>Buscar por nome ou matrícula<input id="prof-search" placeholder="Digite pelo menos 2 caracteres" autocomplete="off"></label><button type="button" data-action="search">Buscar professor</button><div id="searchresults" class="searchresults"></div><input type="hidden" name="professor" id="professor-id"><button type="submit">Enviar convite interno</button></form></div>`;
}
document.addEventListener('change',event=>{
 if(event.target.matches('input[type="radio"][name="discipline"]')){
  const d=data.disciplines.find(d=>d.id_disciplina===Number(event.target.value));
  document.getElementById('selected-discipline').textContent='Selecionada: '+d.nome+' · '+className(d);
 }
});
function availabilityPanel(id){const i=data.invitations.find(i=>i.id_convite===Number(id));activeInvitation=i.id_convite;const selected=data.availability.filter(a=>a.id_convite===i.id_convite).map(a=>a.id_slot);const slots=data.slots.filter(s=>s.turno===i.turno);const readonly=me.role==='coordenador';const panel=document.getElementById('availability-panel');panel.innerHTML=`<div class="card section-title"><div class="row spread"><h2>${e(i.disciplina)} · disponibilidade</h2><button class="secondary" data-action="close-availability">Fechar</button></div><p class="muted">${e(i.professor)} · ${e(i.turno)} · ${i.ano}/${i.semestre}</p><form data-form="availability"><div class="tablewrap"><table class="availability"><thead><tr><th>Horário</th>${days.slice(1).map(d=>`<th>${d}</th>`).join('')}</tr></thead><tbody>${[1,2,3,4].map(n=>`${n===3?`<tr class="break"><td colspan="7">INTERVALO · ${i.turno==='noturno'?'20:50–21:10':'09:50–10:10'}</td></tr>`:''}<tr><th>${slots.find(s=>s.numero_aula===n).hora_inicio}–${slots.find(s=>s.numero_aula===n).hora_fim}</th>${days.slice(1).map((d,k)=>{const s=slots.find(s=>s.numero_aula===n&&s.dia_semana===k+1);const conflicts=(data.availabilityConflicts||[]).filter(a=>a.id_convite===i.id_convite&&a.id_slot===s.id_slot);if(conflicts.length){const message='Conflito: '+conflicts.map(a=>a.disciplina).join(', ')+' já está agendada neste dia e horário em uma grade finalizada.';return `<td><span class="availability-warning" tabindex="0" role="checkbox" aria-checked="false" aria-disabled="true" aria-label="${e(d+' '+s.hora_inicio+'. '+message)}"><span aria-hidden="true">!</span><span class="availability-tooltip" role="tooltip">${e(message)}</span></span></td>`;}return `<td><input aria-label="${d} ${s.hora_inicio}" type="checkbox" name="slots" value="${s.id_slot}" ${selected.includes(s.id_slot)&&!conflicts.length?'checked':''} ${readonly||conflicts.length?'disabled':''}></td>`;}).join('')}</tr>`).join('')}</tbody></table></div>${readonly?'':`<div class="actions"><button type="submit">Salvar disponibilidade</button></div>`}</form></div>`;bindForms();panel.scrollIntoView({behavior:'smooth',block:'start'});}
function gradeView(){
 if(!data.grades.length)return empty('Crie uma turma do seu curso para iniciar sua grade.');
 if(!data.grades.some(g=>g.id_grade===Number(gradeId)))gradeId=data.grades[0].id_grade;
 const g=data.grades.find(g=>g.id_grade===Number(gradeId));
 const invites=data.invitations.filter(i=>i.id_turma===g.id_turma&&i.status==='aceito');
 const disciplines=data.disciplines.filter(d=>d.id_turma===g.id_turma);
 const waiting=!disciplines.length||disciplines.some(d=>!invites.some(i=>i.id_disciplina===d.id_disciplina&&data.availability.some(a=>a.id_convite===i.id_convite)));
 const stage=g.status==='publicada'?'Finalizada':waiting?'Aguardando professores':'Aguardando montagem';
 if(!invites.some(i=>i.id_convite===Number(gradeInvitation)))gradeInvitation=invites[0]?.id_convite??null;
 return `<div class="filters">${select('Período / turma e semestre','grade-choice',opts(data.classes,'id_turma',x=>`${periodName(x.periodo)} · Eng. Soft · ${x.turno} · ${x.ano}/${x.semestre}`))}</div><div class="card section"><div class="row spread"><div><h2>${e(g.curso)} · ${e(periodName(g.periodo))}</h2><span class="muted small">${g.ano}/${g.semestre} · versão ${g.versao}</span></div><div class="row"><span class="pill ${stage==='Finalizada'?'publicada':'pendente'}">${stage}</span>${g.status==='rascunho'?`<button data-action="publish" data-id="${g.id_grade}">Publicar grade</button>`:g.status==='publicada'?`<button class="secondary" data-action="revise" data-id="${g.id_grade}">Criar revisão</button>`:''}</div></div>${g.status==='rascunho'?combinedAvailability(g,invites):''}${g.status==='rascunho'?`<div class="section-title"><h2>Montagem manual</h2>${select('Disciplina / professor','invitation',opts(invites,'id_convite',i=>`${i.disciplina} · ${i.professor}`))}<p class="small muted">Clique nos horários disponíveis para marcar ou desmarcar as aulas. Depois, clique em Salvar alterações.</p></div>`:''}${g.status==='rascunho'?`<div class="actions section"><button data-action="save-grade" ${savingSlot||!gradeEdits.get(g.id_grade)?.changes.size?'disabled':''}>${savingSlot?'Salvando…':'Salvar alterações'}</button><button class="secondary" data-action="discard-grade" ${savingSlot||!gradeEdits.get(g.id_grade)?.changes.size?'disabled':''}>Descartar alterações</button><span class="small muted">${gradeEdits.get(g.id_grade)?.changes.size?'Alterações ainda não salvas.':'Todas as alterações salvas.'}</span></div>`:''}${g.status==='rascunho'?interactiveGrade(g,invites):weeklyTable(data.allocations.filter(a=>a.id_grade===g.id_grade),g.turno)}</div>`;
}
function combinedAvailability(g,invites){
 const slots=data.slots.filter(s=>s.turno===g.turno);
 const disciplines=data.disciplines.filter(d=>d.id_turma===g.id_turma);
 const ready=invites.filter(i=>data.availability.some(a=>a.id_convite===i.id_convite)).length;
 return `<section class="section-title"><h2>Disponibilidade de todos os professores</h2><p class="muted small">${ready} de ${disciplines.length} disciplinas com professor confirmado e disponibilidade preenchida. Os nomes abaixo representam disponibilidade, não aulas alocadas.</p><div class="tablewrap"><table><thead><tr><th>Aula</th>${days.slice(1).map(d=>`<th>${d}</th>`).join('')}</tr></thead><tbody>${[1,2,3,4].map(n=>`${n===3?`<tr class="break"><td colspan="7">INTERVALO · ${g.turno==='noturno'?'20:50–21:10':'09:50–10:10'}</td></tr>`:''}<tr><th>${slots.find(s=>s.numero_aula===n).hora_inicio}<br>${slots.find(s=>s.numero_aula===n).hora_fim}</th>${days.slice(1).map((day,k)=>{
  const slot=slots.find(s=>s.numero_aula===n&&s.dia_semana===k+1);
  const matches=invites.filter(i=>data.availability.some(a=>a.id_convite===i.id_convite&&a.id_slot===slot.id_slot));
  const overlap=new Set(matches.map(i=>i.id_professor)).size>1;
  return `<td class="slotcell ${overlap?'availability-overlap':''}">${overlap?'<div class="small overlap-label">Disponibilidades coincidentes</div>':''}${matches.map(i=>`<div class="available-professor"><strong>${e(i.professor)}</strong><div class="small muted">${e(i.disciplina)}</div></div>`).join('')||'<span class="muted small">Nenhum professor</span>'}</td>`;
 }).join('')}</tr>`).join('')}</tbody></table></div></section>`;
}
function gradeRows(g){
 const rows=data.allocations.filter(a=>a.id_grade===g.id_grade);
 const changes=gradeEdits.get(g.id_grade)?.changes;
 if(!changes)return rows;
 const result=rows.filter(a=>!changes.has(a.id_slot));
 for(const [slot,invitation]of changes){
  if(!invitation)continue;
  const i=data.invitations.find(i=>i.id_convite===invitation);
  result.push({...i,id_grade:g.id_grade,id_slot:slot,pending:true});
 }
 return result;
}
function interactiveGrade(g,invites){
 const invite=invites.find(i=>i.id_convite===Number(gradeInvitation));
 const rows=gradeRows(g);
 const count=rows.filter(a=>a.id_convite===invite?.id_convite).length;
 const available=new Set(data.availability.filter(a=>a.id_convite===invite?.id_convite).map(a=>a.id_slot));
 const slots=data.slots.filter(s=>s.turno===g.turno);
 const otherConflicts=new Set(data.allocations.filter(a=>a.id_turma!==g.id_turma&&a.ano===g.ano&&a.semestre===g.semestre&&a.id_professor===invite?.id_professor&&['rascunho','publicada'].includes(a.grade_status)).map(a=>a.id_slot));
 return `<div class="row spread section"><strong>${invite?count+' / '+invite.slots_semanais+' aulas semanais de '+e(invite.disciplina):'Selecione um convite aceito.'}</strong><span class="small muted">Verde claro: disponível · verde escuro: aula alocada · cinza: indisponível</span></div><div class="tablewrap"><table><thead><tr><th>Aula</th>${days.slice(1).map(d=>`<th>${d}</th>`).join('')}</tr></thead><tbody>${[1,2,3,4].map(n=>`${n===3?`<tr class="break"><td colspan="7">INTERVALO · ${g.turno==='noturno'?'20:50–21:10':'09:50–10:10'}</td></tr>`:''}<tr><th>${slots.find(s=>s.numero_aula===n).hora_inicio}<br>${slots.find(s=>s.numero_aula===n).hora_fim}</th>${days.slice(1).map((day,k)=>{
 const s=slots.find(s=>s.numero_aula===n&&s.dia_semana===k+1),allocated=rows.find(a=>a.id_slot===s.id_slot);
 const mine=allocated&&allocated.id_convite===invite?.id_convite;
 const conflict=otherConflicts.has(s.id_slot),canAdd=invite&&available.has(s.id_slot)&&!allocated&&!conflict&&count<invite.slots_semanais;
 const text=mine?'✓ '+allocated.disciplina:allocated?allocated.disciplina:conflict?'Professor ocupado':!invite?'Selecione a disciplina':!available.has(s.id_slot)?'Indisponível':count>=invite.slots_semanais?'Limite semanal atingido':'Disponível';
 return `<td class="slotcell"><button type="button" class="grade-slot ${mine?'marked':allocated?'occupied':canAdd?'available':'blocked'}" data-action="toggle-slot" data-id="${s.id_slot}" aria-pressed="${!!mine}" aria-label="${e(day+' '+s.hora_inicio+' · '+text)}" ${(!mine&&!canAdd)||savingSlot?'disabled':''}><strong>${e(text)}</strong><span class="small">${mine?(allocated.pending?'Não salva · clique para remover':'Clique para remover'):allocated?e(allocated.professor):canAdd?'Clique para marcar':''}</span></button></td>`;
 }).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function weeklyTable(rows,shift,editable=false,own=false){const slots=data.slots.filter(s=>s.turno===shift);return `<div class="tablewrap"><table><thead><tr><th>Aula</th>${days.slice(1).map(d=>`<th>${d}</th>`).join('')}</tr></thead><tbody>${[1,2,3,4].map(n=>`${n===3?`<tr class="break"><td colspan="7">INTERVALO DE 20 MINUTOS · ${shift==='noturno'?'20:50–21:10':'09:50–10:10'}</td></tr>`:''}<tr><th>${slots.find(s=>s.numero_aula===n).hora_inicio}<br><span class="muted">${slots.find(s=>s.numero_aula===n).hora_fim}</span></th>${days.slice(1).map((d,k)=>{const s=slots.find(s=>s.numero_aula===n&&s.dia_semana===k+1);const rs=rows.filter(a=>a.id_slot===s.id_slot);return `<td class="slotcell">${rs.map(a=>`<div class="lesson"><strong>${e(a.disciplina)}</strong>${own?'':`<div class="small">${e(a.professor)}</div>`}<div class="small muted">${e(periodName(a.periodo))} · Eng. Soft</div>${editable?`<button class="danger" data-action="remove-allocation" data-id="${a.id_alocacao}">Remover</button>`:''}</div>`).join('')||'<span class="muted">—</span>'}</td>`;}).join('')}</tr>`).join('')}</tbody></table></div>`;}
function bindGrade(){
 const choice=document.querySelector('[name=grade-choice]');
 if(choice){choice.value=data.grades.find(g=>g.id_grade===Number(gradeId))?.id_turma??'';choice.onchange=()=>{const versions=data.grades.filter(g=>g.id_turma===Number(choice.value)&&g.status!=='arquivada').sort((a,b)=>b.versao-a.versao);gradeId=versions[0]?.id_grade??null;gradeInvitation=null;render();};}
 const invitation=document.querySelector('[name=invitation]');
 if(invitation){invitation.value=gradeInvitation??'';invitation.onchange=()=>{gradeInvitation=Number(invitation.value)||null;render();};}
}
function lessons(){const semesters=[...new Set(data.allocations.map(a=>a.ano+'/'+a.semestre))];return `<div class="filters"><label>Semestre letivo<select id="lesson-semester"><option value="">Todos os semestres</option>${semesters.map(s=>`<option>${s}</option>`).join('')}</select></label><label>Curso / período<select id="lesson-class"><option value="">Todas as turmas</option>${[...new Map(data.allocations.map(a=>[a.id_turma,a])).values()].map(a=>`<option value="${a.id_turma}">${e(className(a))}</option>`).join('')}</select></label><button data-action="filter-lessons">Filtrar</button></div><div id="lessons-result">${lessonResults(data.allocations)}</div>`;}
function lessonResults(rows){return rows.length?[...new Set(rows.map(a=>a.ano+'/'+a.semestre))].map(sem=>['matutino','noturno'].filter(t=>rows.some(r=>r.turno===t&&r.ano+'/'+r.semestre===sem)).map(t=>`<div class="card section"><h2>${sem} · ${t==='matutino'?'Manhã':'Noite'}</h2>${weeklyTable(rows.filter(r=>r.turno===t&&r.ano+'/'+r.semestre===sem),t)}</div>`).join('')).join('')+`<div class="card tablewrap"><h2>Detalhamento das aulas</h2><table><thead><tr><th>Semestre</th><th>Disciplina</th><th>Curso / turma</th><th>Dia e horário</th></tr></thead><tbody>${rows.map(a=>`<tr><td>${a.ano}/${a.semestre}</td><td>${e(a.disciplina)}</td><td>${e(a.curso)} · ${e(periodName(a.periodo))}</td><td>${days[a.dia_semana]} ${a.hora_inicio}–${a.hora_fim}</td></tr>`).join('')}</tbody></table></div>`:empty('Nenhuma aula publicada para os filtros selecionados.');}
function bindDashboard(){
 if(page!=='painel'||me.role!=='professor')return;
 const own=data.allocations.filter(a=>a.id_professor===me.id&&a.grade_status==='publicada');
 const semesters=[...new Set([...own,...data.invitations].map(a=>a.ano+'/'+a.semestre))].sort().reverse();
 const select=document.getElementById('dashboard-semester');
 select.innerHTML=semesters.map(s=>`<option value="${s}">${s}</option>`).join('')||'<option value="">Semestre atual</option>';
 const parts=new Intl.DateTimeFormat('en',{year:'numeric',month:'numeric',timeZone:'America/Sao_Paulo'}).formatToParts(new Date());
 const current=parts.find(p=>p.type==='year').value+'/'+(Number(parts.find(p=>p.type==='month').value)<=6?1:2);
 if(semesters.includes(current))select.value=current;
 function update(){
  const rows=own.filter(a=>a.ano+'/'+a.semestre===select.value);
  document.getElementById('dashboard-week').innerHTML=rows.length?['matutino','noturno'].filter(t=>rows.some(r=>r.turno===t)).map(t=>`<h3>${t==='matutino'?'Manhã':'Noite'}</h3>${weeklyTable(rows.filter(r=>r.turno===t),t,false,true)}`).join(''):empty('Você ainda não tem aulas publicadas neste semestre.');
 }
 select.onchange=update;update();
}
function bindDiscipline(){
 if(page!=='disciplinas'||!editingDiscipline)return;
 const d=data.disciplines.find(d=>d.id_disciplina===editingDiscipline);
 if(!d){editingDiscipline=null;return;}
 const form=document.querySelector('form[data-form="edit-disciplines"]');
 for(const [name,value]of Object.entries({name:d.nome,workload:d.carga_horaria,weeklySlots:d.slots_semanais,class:d.id_turma}))form.elements.namedItem(name).value=value;
}
async function submit(type,x,f){
 if(type==='edit-disciplines'){
  await api('/disciplines/'+editingDiscipline,{name:x.name,workload:Number(x.workload),weeklySlots:Number(x.weeklySlots),class:Number(x.class)},'PUT');
  editingDiscipline=null;await load();toast('Disciplina atualizada.');return;
 }
 if(type==='login'){await api('/login',x);me=await api('/me');page='painel';await load();return;}
 if(type==='register'){const r=await api('/register',x);login();document.getElementById('login-info').innerHTML=`<div class="credential"><strong>Conta criada!</strong><p>Matrícula: ${e(r.matricula)}<br>E-mail: ${e(r.email)}</p><p class="small">Guarde esses dados. Use a senha que você acabou de cadastrar.</p></div>`;document.querySelector('[name=email]').value=r.email;return;}
 if(type==='availability'){await api(`/invitations/${activeInvitation}/availability`,{slots:[...f.querySelectorAll('input:checked')].map(c=>Number(c.value))});await load();toast('Disponibilidade salva.');return;}
 if(type==='password'){await api('/password',x);toast('Senha alterada. Entre novamente.');me=null;login();return;}
 if(type==='profile'){await api('/profile',x);me=await api('/me');await load();toast('Perfil atualizado.');return;}
 for(const k of ['period','year','number','course','semester','class','workload','weeklySlots','discipline','professor','invitation','slot'])if(k in x)x[k]=Number(x[k]);
 if(type==='invitations'&&!x.discipline)throw Error('Abra um curso e selecione a disciplina e a turma.');
 if(type==='invitations'&&!x.professor)throw Error('Selecione um professor cadastrado.');
 if(type==='allocations')x.grade=Number(gradeId);
 await api('/'+type,x);await load();toast('Salvo com sucesso.');
}
async function action(type,id,b){
 if(type==='edit-discipline'){editingDiscipline=Number(id);render();document.querySelector('form[data-form="edit-disciplines"]').scrollIntoView({behavior:'smooth',block:'start'});return;}
 if(type==='cancel-discipline-edit'){editingDiscipline=null;render();return;}
 if(type==='fill-coordinator'){const credentials=await api('/test/coordinator-login',{});document.querySelector('[name=email]').value=credentials.email;document.querySelector('[name=password]').value=credentials.password;toast('Login do coordenador preenchido. Clique em Entrar.');return;}
 if(type==='toggle-slot'){
  if(savingSlot)return;
  const g=data.grades.find(g=>g.id_grade===Number(gradeId)),slot=Number(id);
  let state=gradeEdits.get(g.id_grade);
  if(!state){state={expectedIds:data.allocations.filter(a=>a.id_grade===g.id_grade).map(a=>a.id_alocacao),changes:new Map()};gradeEdits.set(g.id_grade,state);}
  const current=gradeRows(g).find(a=>a.id_slot===slot);
  const desired=current&&current.id_convite===Number(gradeInvitation)?null:Number(gradeInvitation);
  const original=data.allocations.find(a=>a.id_grade===g.id_grade&&a.id_slot===slot)?.id_convite??null;
  if(desired===original)state.changes.delete(slot);else state.changes.set(slot,desired);
  render();return;
 }
 if(type==='save-grade'){
  if(savingSlot)return;
  const state=gradeEdits.get(Number(gradeId));if(!state?.changes.size)return;
  savingSlot=true;render();
  try{
   await api('/grades/'+gradeId+'/allocations',{expectedIds:state.expectedIds,changes:[...state.changes].map(([slot,invitation])=>({slot,invitation}))});
   gradeEdits.delete(Number(gradeId));data=await api('/data');toast('Alterações salvas.');
  }finally{savingSlot=false;render();}
  return;
 }
 if(type==='discard-grade'){gradeEdits.delete(Number(gradeId));await load();return;}
 if(type==='login'||type==='register'){login(type==='register');return;}
 if(type==='nav'){page=id;await load();return;}
 if(type==='logout'){gradeEdits.clear();await api('/logout',{});me=null;login();return;}
 if(type==='search'){const q=document.getElementById('prof-search').value;selectedProfessor=null;document.getElementById('professor-id').value='';const list=await api('/professors?q='+encodeURIComponent(q));document.getElementById('searchresults').innerHTML=list.map(p=>`<div class="result" id="prof-${p.id_usuario}"><div><strong>${e(p.nome)}</strong><div class="small muted">${e(p.matricula_funcional)} · ${e(p.titulacao)}</div></div><button type="button" class="secondary" data-action="select-professor" data-id="${p.id_usuario}">Selecionar</button></div>`).join('')||empty('Nenhum professor encontrado. Digite pelo menos 2 caracteres.');return;}
 if(type==='select-professor'){selectedProfessor=Number(id);document.getElementById('professor-id').value=id;document.querySelectorAll('.result').forEach(r=>r.classList.remove('selected'));document.getElementById('prof-'+id).classList.add('selected');return;}
 if(type==='availability'){await load();availabilityPanel(id);return;}
 if(type==='close-availability'){document.getElementById('availability-panel').innerHTML='';return;}
 if(type==='filter-lessons'){const sem=document.getElementById('lesson-semester').value;const cls=document.getElementById('lesson-class').value;document.getElementById('lessons-result').innerHTML=lessonResults(data.allocations.filter(a=>(!sem||a.ano+'/'+a.semestre===sem)&&(!cls||a.id_turma===Number(cls))));return;}
 if(type==='accept'||type==='reject')await api(`/invitations/${id}/reply`,{status:type==='accept'?'aceito':'recusado'});
 if(type==='cancel'){if(!confirm('Cancelar este convite?'))return;await api(`/invitations/${id}/cancel`,{});}
 if(type==='remove-allocation')await api('/allocations/'+id,null,'DELETE');
 if(type==='publish'){if(gradeEdits.get(Number(id))?.changes.size)throw Error('Salve as alterações antes de publicar a grade.');if(!confirm('Publicar esta versão da grade para os professores?'))return;await api(`/grades/${id}/publish`,{});}
 if(type==='revise')await api(`/grades/${id}/revise`,{});
 await load();toast('Operação concluída.');
}
(async()=>{try{me=await api('/me');await load();}catch{login();const s=await api('/status').catch(()=>null);if(s&&!s.configured)document.getElementById('login-info').innerHTML='<p class="small muted">O administrador precisa executar Setup.ps1 para configurar o PostgreSQL.</p>';}})();
