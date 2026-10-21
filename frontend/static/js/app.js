const $=s=>document.querySelector(s);
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const DAYS=["Segunda","Terça","Quarta","Quinta","Sexta","Sábado"],ROLES={manager:"Gestor",coordinator:"Coordenador",professor:"Professor"};
let S={token:sessionStorage.getItem("t"),user:null};
async function api(path,method="GET",body){
  const r=await fetch("/api/"+path,{method,headers:{"Content-Type":"application/json",...(S.token?{Authorization:"Token "+S.token}:{})},body:body?JSON.stringify(body):undefined});
  if(r.status===204)return null;
  const d=await r.json().catch(()=>({}));
  if(!r.ok){if(r.status===401&&S.token)logout();throw d}
  return d}
const errText=e=>typeof e==="string"?e:Object.entries(e).map(([k,v])=>(["detail","non_field_errors"].includes(k)?"":k+": ")+[].concat(v).map(x=>typeof x==="object"?JSON.stringify(x):x).join(" ")).join(" • ")||"Erro inesperado.";
function toast(m,bad){const t=$("#toast");t.textContent=m;t.className=bad?"bad":"";t.style.display="block";clearTimeout(t._h);t._h=setTimeout(()=>t.style.display="none",3500)}
const fmt=t=>t.slice(0,5);

/* ---- definição dos recursos (CRUD genérico) ---- */
const act=a=>a?"Ativo":"Inativo";
const R={
 users:{title:"Usuários",path:"users",w:["manager"],cols:[["first_name","Nome"],["email","E-mail"],["role","Perfil",v=>ROLES[v]]],
  extra:[["Disponibilidade",r=>showAvail(asProf(r)),["manager"],r=>r.role==="professor"],["Atribuir disciplinas",(r,done)=>assignSubjects(asProf(r),done),["coordinator"],r=>r.role==="professor"]],
  fields:[{k:"first_name",l:"Nome",req:1},{k:"email",l:"E-mail",t:"email",req:1},{k:"role",l:"Perfil",t:"select",o:[["coordinator","Coordenador"],["manager","Gestor"]]},{k:"password",l:"Senha",t:"password",pw:1}]},
 courses:{title:"Cursos",path:"courses",w:["coordinator"],cols:[["code","Código"],["name","Nome"],["coordinator_name","Coordenador"]],
  fields:[{k:"name",l:"Nome",req:1},{k:"code",l:"Código",req:1},{k:"description",l:"Descrição",t:"textarea"},{k:"coordinator",l:"Coordenador responsável",t:"select",src:"users",filter:u=>u.role==="coordinator",lab:u=>u.first_name,only:["manager"],nullable:1}]},
 subjects:{title:"Disciplinas",path:"subjects",w:["coordinator"],cols:[["code","Código"],["name","Nome"],["course_name","Curso"],["student_count","Alunos"],["weekly_lessons","Aulas/sem"],["lesson_minutes","Min/aula"]],
  fields:[{k:"name",l:"Nome",req:1},{k:"code",l:"Código",req:1},{k:"course",l:"Curso",t:"select",src:"courses",lab:c=>c.name,req:1},{k:"student_count",l:"Número de alunos previstos",t:"number",req:1,def:30},{k:"weekly_lessons",l:"Aulas por semana",t:"number",req:1,def:1},{k:"lesson_minutes",l:"Duração da aula (min)",t:"number",req:1,def:50},{k:"preferred_days",l:"Dias preferidos (opcional)",t:"multi",o:DAYS.map((d,i)=>[i,d])}]},
 professors:{title:"Professores",path:"professors",w:["manager"],cols:[["full_name","Nome"],["email","E-mail"],["max_weekly_hours","Carga máx. (h)"],["availability_count","Horários disponíveis"]],
  extra:[["Disponibilidade",p=>showAvail(p),["manager"]],["Atribuir disciplinas",p=>assignSubjects(p),["coordinator"]]],
  fields:[{k:"full_name",l:"Nome completo",req:1},{k:"email",l:"E-mail",t:"email",req:1},{k:"password",l:"Senha inicial",t:"password",pw:1},{k:"institutional_id",l:"Identificador institucional"},{k:"max_weekly_hours",l:"Carga horária semanal máxima (h)",t:"number",req:1,def:20},{k:"subjects",l:"Disciplinas habilitadas",t:"multi",src:"subjects",lab:s=>s.name+" ("+s.code+")"}]},
 slots:{title:"Horários (slots)",path:"slots",w:["manager"],nosearch:1,cols:[["weekday","Dia",v=>DAYS[v]],["start","Início",fmt],["end","Fim",fmt]],
  fields:[{k:"weekday",l:"Dia da semana",t:"select",o:DAYS.map((d,i)=>[i,d]),req:1},{k:"start",l:"Início",t:"time",req:1},{k:"end",l:"Fim",t:"time",req:1}]},
};
const asProf=r=>({...r,id:r.professor_id,full_name:r.full_name||r.first_name,subjects:r.subjects||[]});
const NAV={manager:[["dash","Início"],["users","Usuários"],["slots","Horários"]],
 coordinator:[["dash","Início"],["alloc","Alocação"],["courses","Meus cursos"],["subjects","Disciplinas"],["users","Usuários"]],
 professor:[["dash","Início"],["avail","Meu perfil"],["mygrid","Minha grade"],["subjects","Minhas disciplinas"]]};

/* ---- shell ---- */
function logout(){api("auth/logout/","POST").catch(()=>{});sessionStorage.removeItem("t");S.token=S.user=null;$("#main").innerHTML="";boot()}
async function boot(){
  if(S.token&&!S.user){try{S.user=await api("auth/me/")}catch{S.token=null}}
  $("#login").hidden=!!S.user;$("#app").hidden=!S.user;
  if(!S.user)return;
  $("#who").textContent=`${S.user.name} · ${ROLES[S.user.role]}`;
  $("#nav").innerHTML='<b><span class="mark" aria-hidden="true">G</span>Grade Acadêmica</b>'+NAV[S.user.role].map(([k,l])=>`<button data-k="${k}">${l}</button>`).join("");
  go("dash")}
async function go(k){
  document.querySelectorAll("#nav button").forEach(b=>b.toggleAttribute("aria-current",b.dataset.k===k)||b.removeAttribute("aria-current"));
  document.querySelectorAll("#nav button").forEach(b=>{if(b.dataset.k===k)b.setAttribute("aria-current","page")});
  $("#main").innerHTML='<p class="mut">Carregando…</p>';
  try{k==="dash"?await dash():k==="avail"?await availPage():k==="alloc"?await allocPage():k==="mygrid"?await myGridPage():await listPage(k)}catch(e){$("#main").innerHTML=`<p class="err">${esc(errText(e))}</p>`}}
$("#nav").onclick=e=>{const b=e.target.closest("button");if(b)go(b.dataset.k)};
$("#out").onclick=logout;
$("#go").onclick=async()=>{$("#lerr").textContent="";$("#go").disabled=true;
  try{const d=await api("auth/login/","POST",{email:$("#em").value,password:$("#pw").value});S.token=d.token;S.user=d.user;sessionStorage.setItem("t",d.token);$("#pw").value="";boot()}
  catch(e){$("#lerr").textContent=errText(e)}finally{$("#go").disabled=false}};
$("#pw").onkeydown=e=>{if(e.key==="Enter")$("#go").click()};

async function dash(){
  const d=await api("dashboard/");
  $("#main").innerHTML=`<div class="bar"><h2>Olá, ${esc(S.user.name)}</h2></div><div class="cards">${d.cards.map(c=>`<div class="card"><b>${esc(c.value)}</b>${esc(c.label)}</div>`).join("")}</div>
  <p class="mut" style="margin-top:20px">${{manager:"Cadastre coordenadores, professores e os horários em que as aulas podem acontecer.",coordinator:"Crie o curso, cadastre as disciplinas nele e gere a alocação: cada aula entra num horário e o professor é quem está disponível, qualquer disciplina.",professor:"Marque seus horários disponíveis em “Meu perfil”; o coordenador atribui as disciplinas com base neles."}[S.user.role]}</p>`}

/* ---- lista genérica + formulário ---- */
async function listPage(key){
  const c=R[key],canW=c.w.includes(S.user.role),PS=10;let page=1,rows=[],total=0,h;
  $("#main").innerHTML=`<div class="bar"><h2>${c.title}</h2>${c.nosearch?"":'<input id="q" type="search" placeholder="Pesquisar…" aria-label="Pesquisar">'}${canW?'<button class="pri" id="new">+ Novo</button>':""}</div><div class="tw" id="tbl"></div><div class="bar" id="pager" style="margin-top:12px"></div>`;
  const q=()=>c.nosearch?"":$("#q").value.trim();
  const load=async()=>{
    const profs=key==="users"&&S.user.role!=="manager";
    const d=await api(`${profs?"professors":c.path}/?page=${page}${q()?"&search="+encodeURIComponent(q()):""}`);
    rows=profs?d.results.map(p=>({...p,first_name:p.full_name,role:"professor",professor_id:p.id})):d.results;
    total=d.count;const pages=Math.max(1,Math.ceil(total/PS));
    if(page>pages){page=pages;return load()}draw(pages)};
  const safe=()=>load().catch(e=>toast(errText(e),1));
  const draw=pages=>{
    if(!rows.length)$("#tbl").innerHTML=`<div class="empty">${q()?"Nada encontrado para a pesquisa.":"Nada cadastrado ainda."+(canW?" Use “+ Novo” para começar.":"")}</div>`;
    else $("#tbl").innerHTML=`<table><thead><tr>${c.cols.map(x=>`<th>${x[1]}</th>`).join("")}<th>Status</th><th></th></tr></thead><tbody>${rows.map(r=>`<tr>${c.cols.map(([k,,fn])=>`<td>${esc(fn?fn(r[k]):r[k])}</td>`).join("")}<td><span class="tag ${r.is_active===false?"off":""}">${act(r.is_active!==false)}</span></td>
    <td class="act">${(c.extra||[]).map(([l,,rl,when],i)=>(!rl||rl.includes(S.user.role))&&(!when||when(r))?`<button data-x="${i}" data-id="${r.id}">${l}</button>`:"").join("")}${canW?`<button data-e="${r.id}">Editar</button><button data-d="${r.id}">${r.is_active===false?"Reativar":"Desativar"}</button><button class="dang" data-del="${r.id}">Excluir</button>`:""}</td></tr>`).join("")}</tbody></table>`;
    $("#pager").innerHTML=total>PS?`<button data-p="-1" ${page<=1?"disabled":""}>Anterior</button><span class="mut">Página ${page} de ${pages} · ${total} registros</span><button data-p="1" ${page>=pages?"disabled":""}>Próxima</button>`:(total?`<span class="mut">${total} registro${total>1?"s":""}</span>`:"")};
  $("#pager").onclick=e=>{const b=e.target.closest("button");if(b){page+=+b.dataset.p;safe()}};
  if(!c.nosearch)$("#q").oninput=()=>{clearTimeout(h);h=setTimeout(()=>{page=1;safe()},250)};
  if(canW)$("#new").onclick=()=>form(c,null,safe);
  $("#tbl").onclick=async e=>{const b=e.target.closest("button");if(!b)return;
    if(b.dataset.e){const r=rows.find(r=>r.id==b.dataset.e);r.role==="professor"&&c.path==="users"?form({...R.professors,title:"Usuários"},await api(`professors/${r.professor_id}/`),safe):form(c,r,safe);return}
    if(b.dataset.x)c.extra[b.dataset.x][1](rows.find(r=>r.id==b.dataset.id),safe);
    const urlOf=r=>r.role==="professor"&&c.path==="users"?`professors/${r.professor_id}/`:`${c.path}/${r.id}/`;
    if(b.dataset.d){const r=rows.find(r=>r.id==b.dataset.d),on=r.is_active!==false;
      if(!confirm(on?"Desativar este registro? Ele deixa de receber novas alocações, mas continua cadastrado.":"Reativar este registro?"))return;
      try{await api(urlOf(r),"PATCH",{is_active:!on});toast(on?"Desativado.":"Reativado.");safe()}catch(er){toast(errText(er),1)}}
    if(b.dataset.del){const r=rows.find(r=>r.id==b.dataset.del);if(!confirm("Excluir definitivamente? Esta ação não pode ser desfeita."))return;
      try{await api(urlOf(r),"DELETE");toast("Excluído.");safe()}catch(er){toast(errText(er),1)}}};
  await load()}

async function form(c,rec,done){
  const fs=c.fields.filter(f=>!f.only||f.only.includes(S.user.role)).map(f=>({...f})),dlg=$("#dlg");
  if(c.path==="users"&&!rec){const role=fs.find(f=>f.k==="role");if(role)role.o=[["coordinator","Coordenador"],["professor","Professor"]]}
  const srcs={};for(const f of fs)if(f.src&&!srcs[f.src])srcs[f.src]=(await api(f.src+"/")).filter(x=>x.is_active!==false);
  const val=f=>rec?rec[f.k]:f.def;
  const inp=f=>{const id="f_"+f.k,v=val(f),req=f.req&&!(f.pw&&rec)?"required":"";
    if(f.t==="textarea")return `<textarea id="${id}" rows="3">${esc(v)}</textarea>`;
    if(f.t==="select"||f.t==="multi"){let o=f.o||(srcs[f.src]||[]).filter(f.filter||(()=>1)).map(x=>[x.id,f.lab(x)]);
      const sel=[].concat(v??[]).map(String);
      return `<select id="${id}" ${f.t==="multi"?"multiple size=5":""} ${req}>${f.nullable||f.t==="select"&&!f.o?'<option value="">— selecione —</option>':""}${o.map(([k,l])=>`<option value="${esc(k)}" ${sel.includes(String(k))?"selected":""}>${esc(l)}</option>`).join("")}</select>${f.t==="multi"?'<small class="mut">Ctrl/Cmd para marcar vários.</small>':""}`}
    return `<input id="${id}" type="${f.t||"text"}" value="${f.pw?"":esc(f.t==="time"&&v?fmt(v):v)}" ${req} ${f.t==="number"?'min="1"':""} ${f.pw?'autocomplete="new-password"':""}>`};
  dlg.innerHTML=`<form method="dialog" id="fm"><h3>${rec?"Editar":"Novo"} — ${c.title}</h3>${fs.map(f=>`<label for="f_${f.k}">${f.l}</label>${inp(f)}`).join("")}<div class="err" id="ferr" role="alert"></div><div class="row"><button type="button" id="cx">Cancelar</button><button class="pri" id="sv">Salvar</button></div></form>`;
  dlg.showModal();$("#cx").onclick=()=>dlg.close();
  $("#fm").onsubmit=async e=>{e.preventDefault();const body={};
    for(const f of fs){const el=$("#f_"+f.k);let v;
      if(f.t==="multi")v=[...el.selectedOptions].map(o=>Number(o.value));
      else{v=el.value;if(f.pw&&!v){if(rec)continue}
        if(f.t==="number"||f.t==="select"&&(f.src||typeof f.o?.[0]?.[0]==="number"))v=v===""?null:Number(v);
        else if(v===""&&f.nullable)v=null}
      body[f.k]=v}
    $("#sv").disabled=true;
    try{if(!rec&&c.path==="users"&&body.role==="professor")await api("professors/","POST",{full_name:body.first_name,email:body.email,password:body.password,max_weekly_hours:20});
      else await api(rec?`${c.path}/${rec.id}/`:c.path+"/",rec?"PATCH":"POST",body);dlg.close();toast("Salvo.");done()}
    catch(er){$("#ferr").textContent=errText(er);$("#sv").disabled=false}}}

/* ---- grade de disponibilidade ---- */
function grid(slots,sel,edit){
  const days=[...new Set(slots.map(s=>s.weekday))].sort(),times=[...new Set(slots.map(s=>fmt(s.start)+"–"+fmt(s.end)))].sort();
  const by={};slots.forEach(s=>by[s.weekday+"|"+fmt(s.start)+"–"+fmt(s.end)]=s.id);
  return `<div class="tw"><table class="grid"><thead><tr><th>Horário</th>${days.map(d=>`<th style="text-align:center">${DAYS[d]}</th>`).join("")}</tr></thead><tbody>${times.map(t=>`<tr><td>${t}</td>${days.map(d=>{const id=by[d+"|"+t];
   return `<td>${id?`<button class="cell" data-s="${id}" aria-pressed="${sel.has(id)}" aria-label="${DAYS[d]} ${t}" ${edit?"":"disabled"}>${sel.has(id)?"Disponível":"—"}</button>`:""}</td>`}).join("")}</tr>`).join("")}</tbody></table></div>`}
function bindGrid(root,sel,onchange){
  let mode=null;const set=b=>{const id=+b.dataset.s,on=mode;on?sel.add(id):sel.delete(id);b.setAttribute("aria-pressed",on);b.textContent=on?"Disponível":"—";onchange()};
  root.onpointerdown=e=>{const b=e.target.closest(".cell");if(!b||b.disabled)return;e.preventDefault();mode=!sel.has(+b.dataset.s);set(b)};
  root.onpointerover=e=>{if(mode===null||e.buttons!==1)return;const b=e.target.closest(".cell");if(b&&!b.disabled&&sel.has(+b.dataset.s)!==mode)set(b)};
  addEventListener("pointerup",()=>mode=null);
  root.onkeydown=e=>{if((e.key==="Enter"||e.key===" ")&&e.target.classList.contains("cell")){e.preventDefault();mode=!sel.has(+e.target.dataset.s);set(e.target);mode=null}}}
async function availPage(){
  const slots=(await api("slots/")).filter(s=>s.is_active),sel=new Set((await api("availability/me/")).slots),me=(await api("professors/"))[0];
  const mins=s=>{const [a,b]=[s.start,s.end].map(x=>+x.slice(0,2)*60+ +x.slice(3,5));return b-a};
  const hours=()=>(slots.filter(s=>sel.has(s.id)).reduce((n,s)=>n+mins(s),0)/60).toFixed(1).replace(".0","");
  $("#main").innerHTML=`<div class="bar"><h2>Meu perfil</h2></div>
  ${me?`<div class="card" style="margin-bottom:22px;max-width:520px"><label for="pn" style="font-weight:600">Nome completo</label><input id="pn" value="${esc(me.full_name)}">
   <label for="pi" style="font-weight:600;display:block;margin-top:12px">Identificador institucional</label><input id="pi" value="${esc(me.institutional_id)}">
   <p class="mut">${esc(me.email)} · carga semanal máxima: ${me.max_weekly_hours} h (definida pelo gestor)</p><div class="err" id="perr" role="alert"></div><div class="row" style="margin-top:6px"><button id="psave">Salvar dados</button></div></div>`:""}
  <div class="bar"><h2 style="font-size:18px">Horários em que posso lecionar</h2><button class="pri" id="save">Salvar disponibilidade</button></div>
  <p class="mut">Clique (ou arraste) para marcar. A disponibilidade vale para qualquer disciplina; o coordenador usa essa informação para atribuir disciplinas a você. Você pode marcar mais horas do que sua carga máxima — a alocação respeita o limite.</p>
  <div class="leg"><span class="swatch on">Azul = disponível</span><span class="swatch">Branco = indisponível</span><b id="hrs"></b></div>${slots.length?`<div id="g">${grid(slots,sel,true)}</div>`:'<div class="empty">O gestor ainda não configurou horários.</div>'}`;
  const upd=()=>$("#hrs").textContent=`${hours()} h marcadas`;upd();
  if(slots.length)bindGrid($("#g"),sel,upd);
  $("#save").onclick=async()=>{try{await api("availability/me/","PUT",{slots:[...sel]});toast("Disponibilidade salva.")}catch(e){toast(errText(e),1)}};
  if(me)$("#psave").onclick=async()=>{$("#perr").textContent="";try{const d=await api("profile/me/","PATCH",{full_name:$("#pn").value,institutional_id:$("#pi").value});S.user.name=d.full_name;$("#who").textContent=`${S.user.name} · ${ROLES[S.user.role]}`;toast("Dados salvos.")}catch(e){$("#perr").textContent=errText(e)}}}
function pwDialog(){
  const dlg=$("#dlg");dlg.innerHTML=`<form method="dialog" id="fm"><h3>Alterar senha</h3><label for="p0">Senha atual</label><input id="p0" type="password" autocomplete="current-password" required><label for="p1">Nova senha</label><input id="p1" type="password" autocomplete="new-password" required><div class="err" id="ferr" role="alert"></div><div class="row"><button type="button" id="cx">Cancelar</button><button class="pri">Salvar senha</button></div></form>`;
  dlg.showModal();$("#cx").onclick=()=>dlg.close();
  $("#fm").onsubmit=async e=>{e.preventDefault();try{await api("auth/password/","POST",{current:$("#p0").value,new:$("#p1").value});dlg.close();toast("Senha alterada.")}catch(er){$("#ferr").textContent=errText(er)}}}
$("#pwbtn").onclick=pwDialog;
async function assignSubjects(p,reload){
  const [slots,a,subs]=await Promise.all([api("slots/"),api(`professors/${p.id}/availability/`),api("subjects/")]),dlg=$("#dlg"),act=subs.filter(s=>s.is_active);
  dlg.innerHTML=`<form method="dialog" id="fm"><h3>Atribuir disciplinas — ${esc(p.full_name)}</h3><p class="mut">Disponibilidade informada pelo professor:</p>
  ${slots.length&&a.slots.length?grid(slots.filter(s=>s.is_active),new Set(a.slots),false):'<div class="empty">O professor ainda não marcou horários.</div>'}
  <label>Disciplinas dos seus cursos</label>${act.length?act.map(s=>`<label style="font-weight:400;display:flex;gap:8px;align-items:center;margin:6px 0"><input type="checkbox" style="width:auto" value="${s.id}" ${p.subjects.includes(s.id)?"checked":""}>${esc(s.name)} <span class="mut">(${esc(s.code)} · ${s.weekly_lessons} aulas/sem)</span></label>`).join(""):'<div class="empty">Você ainda não tem disciplinas cadastradas.</div>'}
  <div class="err" id="ferr" role="alert"></div><div class="row"><button type="button" id="cx">Cancelar</button><button class="pri" id="sv">Salvar atribuição</button></div></form>`;
  dlg.style.width="min(820px,96vw)";dlg.showModal();$("#cx").onclick=()=>dlg.close();
  $("#fm").onsubmit=async e=>{e.preventDefault();const ids=[...dlg.querySelectorAll("input[type=checkbox]:checked")].map(x=>+x.value);
    try{await api(`professors/${p.id}/subjects/`,"PUT",{subjects:ids});dlg.close();toast("Disciplinas atribuídas.");reload?reload():go("users")}catch(er){$("#ferr").textContent=errText(er)}}}
async function showAvail(p){
  const [slots,a]=await Promise.all([api("slots/"),api(`professors/${p.id}/availability/`)]),dlg=$("#dlg");
  dlg.innerHTML=`<h3>Disponibilidade — ${esc(p.full_name)}</h3>${slots.length?grid(slots.filter(s=>s.is_active),new Set(a.slots),false):'<div class="empty">Sem horários configurados.</div>'}<div class="row"><button id="cx">Fechar</button></div>`;
  dlg.style.width="min(820px,96vw)";dlg.showModal();$("#cx").onclick=()=>dlg.close()}

/* Alocação no navegador. Professor entra pelo horário livre, não pela disciplina. */
const AK="gradeapp_alloc_preview";
const store={get(){try{return JSON.parse(localStorage.getItem(AK))||{versions:[]}}catch{return{versions:[]}}},set(v){localStorage.setItem(AK,JSON.stringify(v))}};
const STAT={draft:["Rascunho","off"],published:["Publicada",""],archived:["Arquivada","off"]};
const hue=s=>{let h=0;for(const c of String(s))h=(h*31+c.charCodeAt(0))%28;return 205+h};
const mm=t=>+t.slice(0,2)*60+ +t.slice(3,5);
const BANNER='<div class="banner">A disciplina entra num horário do curso. O professor é qualquer um disponível naquele slot; a carga máxima semanal continua valendo.</div>';

async function readiness(){
  const [slots,subs,profs]=await Promise.all([api("slots/"),api("subjects/"),api("professors/")]);
  const as=slots.filter(x=>x.is_active),sb=subs.filter(x=>x.is_active),pr=profs.filter(x=>x.is_active),avail={};
  await Promise.all(pr.map(async p=>avail[p.id]=new Set((await api(`professors/${p.id}/availability/`)).slots)));
  const noAv=pr.filter(p=>!avail[p.id].size);
  const names=l=>l.slice(0,3).map(x=>x.full_name).join(", ")+(l.length>3?"…":"");
  const checks=[
    [as.length?"ok":"err",`${as.length} horário(s) ativo(s)`,as.length?"":"O gestor precisa cadastrar horários."],
    [sb.length?"ok":"err",`${sb.length} disciplina(s) ativa(s)`,sb.length?"":"Cadastre disciplinas no curso."],
    [pr.length?"ok":"err",`${pr.length} professor(es) ativo(s)`,pr.length?"":"O gestor precisa cadastrar professores."],
    [noAv.length?"warn":"ok",noAv.length?`${noAv.length} professor(es) sem disponibilidade marcada`:"Todos os professores marcaram disponibilidade",noAv.length?names(noAv):""]];
  return{slots:as,subs:sb,profs:pr,avail,checks,blocked:checks.some(c=>c[0]==="err")}}

function previewGenerate(d){  // guloso: slot do curso + professor livre, ignora disciplina habilitada
  const used=new Set(),mins={},days={},alloc=[],pending=[],dur=s=>mm(s.end)-mm(s.start);
  const qs=d.profs;
  [...d.subs].sort((a,b)=>b.weekly_lessons-a.weekly_lessons).forEach(s=>{
    const why=new Set();let done=0;
    if(!qs.length)why.add("Nenhum professor ativo.");
    for(let i=0;i<s.weekly_lessons&&qs.length;i++){let best=null,anyAv=false;
      for(const p of qs)for(const sl of d.slots){
        if(!d.avail[p.id].has(sl.id))continue;anyAv=true;
        if(used.has("c"+s.course+"|"+sl.id)){why.add("Esse horário já tem outra disciplina do curso.");continue}
        if(used.has("p"+p.id+"|"+sl.id)){why.add("Professores já ocupados nesse horário.");continue}
        if((mins[p.id]||0)+dur(sl)>p.max_weekly_hours*60){why.add("Carga horária máxima do professor atingida.");continue}
        const score=(days[s.id+"|"+sl.weekday]?10:0)+(mins[p.id]||0)/60;
        if(!best||score<best.score)best={p,sl,score}}
      if(!best){if(!anyAv)why.add("Nenhum professor marcou esse horário como disponível.");break}
      const{p,sl}=best;used.add("p"+p.id+"|"+sl.id);used.add("c"+s.course+"|"+sl.id);mins[p.id]=(mins[p.id]||0)+dur(sl);days[s.id+"|"+sl.weekday]=1;done++;
      alloc.push({subject:s.name,code:s.code,course:s.course_name,professor:p.full_name,professorId:p.id,slotId:sl.id,weekday:sl.weekday,start:sl.start,end:sl.end})}
    if(done<s.weekly_lessons)pending.push({subject:s.name,course:s.course_name,missing:s.weekly_lessons-done,reason:[...why].join(" ")||"Sem combinação viável."})});
  const total=d.subs.reduce((n,s)=>n+s.weekly_lessons,0);
  return{id:Date.now(),createdAt:new Date().toISOString(),by:S.user.name,scope:"Meus cursos",status:"draft",alloc,pending,total,slots:d.slots.map(({id,weekday,start,end})=>({id,weekday,start,end}))}}

function allocGrid(alloc,slots){
  const days=[...new Set(slots.map(s=>s.weekday))].sort(),times=[...new Set(slots.map(s=>fmt(s.start)+"–"+fmt(s.end)))].sort();
  return `<div class="tw"><table class="grid ag"><thead><tr><th>Horário</th>${days.map(d=>`<th style="text-align:center">${DAYS[d]}</th>`).join("")}</tr></thead><tbody>${times.map(t=>`<tr><td>${t}</td>${days.map(d=>`<td>${alloc.filter(a=>a.weekday===d&&fmt(a.start)+"–"+fmt(a.end)===t).map(a=>`<div class="blk" style="background:hsl(${hue(a.course)},80%,94%);border-color:hsl(${hue(a.course)},60%,42%)"><b>${esc(a.subject)}</b><small>${esc(a.professor)}</small></div>`).join("")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`}
const dt=iso=>new Date(iso).toLocaleString("pt-BR",{dateStyle:"short",timeStyle:"short"});

async function allocPage(){
  const d=await readiness();let vid=null,tab="grid",filt="";
  const render=()=>{
    const st=store.get(),v=st.versions.find(x=>x.id===vid)||st.versions[0];if(v)vid=v.id;
    const done=v?v.alloc.length:0,pct=v&&v.total?Math.round(100*done/v.total):0;
    const opts=v?[...new Set(v.alloc.map(a=>"c:"+a.course))].map(x=>[x,"Curso: "+x.slice(2)]).concat([...new Set(v.alloc.map(a=>"p:"+a.professor))].map(x=>[x,"Professor: "+x.slice(2)])):[];
    const shown=v?v.alloc.filter(a=>!filt||(filt[0]==="c"?a.course:a.professor)===filt.slice(2)):[];
    $("#main").innerHTML=BANNER+`<div class="bar"><h2>Alocação de aulas</h2><button class="pri" id="gen" ${d.blocked?"disabled":""}>Gerar nova proposta</button></div>
    <div class="card"><b style="font-size:16px;color:inherit">Dados para gerar a grade</b><ul class="chk">${d.checks.map(([k,l,h])=>`<li class="${k}">${esc(l)}${h?` <span class="mut">— ${esc(h)}</span>`:""}</li>`).join("")}</ul>${d.blocked?'<p class="err">Complete os itens com <i class="fa-solid fa-xmark" aria-hidden="true"></i> para poder gerar.</p>':'<p class="mut" style="margin:8px 0 0">Itens com <i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i> não bloqueiam, mas podem gerar pendências.</p>'}</div>
    ${v?`<div class="bar" style="margin-top:20px"><h2 style="font-size:18px">Proposta de ${dt(v.createdAt)}</h2><span class="tag ${STAT[v.status][1]}">${STAT[v.status][0]}</span>
      ${v.status==="draft"?`<button class="pri" id="pub">Publicar</button><button class="dang" id="disc">Descartar</button>`:""}</div>
      <div class="cards"><div class="card"><b>${pct}%</b>das aulas alocadas</div><div class="card"><b>${done}/${v.total}</b>aulas</div><div class="card"><b>${v.pending.length}</b>disciplinas pendentes</div><div class="card"><b>0</b>conflitos</div></div>
      <div class="tabs" role="tablist">${[["grid","Grade semanal"],["pend","Pendências ("+v.pending.length+")"],["hist","Histórico ("+st.versions.length+")"]].map(([k,l])=>`<button role="tab" data-t="${k}" aria-selected="${tab===k}">${l}</button>`).join("")}</div>
      ${tab==="grid"?`<div class="bar"><select id="flt" style="max-width:280px" aria-label="Filtrar grade"><option value="">Todas as aulas</option>${opts.map(([k,l])=>`<option value="${esc(k)}" ${k===filt?"selected":""}>${esc(l)}</option>`).join("")}</select></div>${shown.length?allocGrid(shown,v.slots):'<div class="empty">Nenhuma aula alocada nesta proposta.</div>'}`
       :tab==="pend"?(v.pending.length?`<div class="tw"><table><thead><tr><th>Disciplina</th><th>Curso</th><th>Aulas faltando</th><th>Motivo</th></tr></thead><tbody>${v.pending.map(p=>`<tr><td>${esc(p.subject)}</td><td>${esc(p.course)}</td><td>${p.missing}</td><td style="white-space:normal">${esc(p.reason)}</td></tr>`).join("")}</tbody></table></div>`:'<div class="empty">Nenhuma pendência. Todas as aulas foram alocadas.</div>')
       :`<div class="tw"><table><thead><tr><th>Gerada em</th><th>Por</th><th>Escopo</th><th>Alocação</th><th>Status</th><th></th></tr></thead><tbody>${st.versions.map(x=>`<tr><td>${dt(x.createdAt)}</td><td>${esc(x.by)}</td><td>${esc(x.scope)}</td><td>${x.alloc.length}/${x.total}</td><td><span class="tag ${STAT[x.status][1]}">${STAT[x.status][0]}</span></td><td class="act"><button data-v="${x.id}">Ver</button></td></tr>`).join("")}</tbody></table></div>`}`
     :'<div class="empty" style="margin-top:20px">Nenhuma proposta gerada ainda. Confira os dados acima e clique em “Gerar nova proposta”.</div>'}`;
    $("#gen").onclick=()=>{const n=previewGenerate(d),s=store.get();s.versions.unshift(n);s.versions=s.versions.slice(0,10);store.set(s);vid=n.id;tab="grid";filt="";toast(`Proposta gerada: ${n.alloc.length} de ${n.total} aulas.`);render()};
    if(v&&v.status==="draft"){
      $("#pub").onclick=()=>{if(!confirm("Publicar esta grade? Ela passa a valer para os professores e a publicada anterior é arquivada."))return;const s=store.get();s.versions.forEach(x=>{if(x.status==="published")x.status="archived"});s.versions.find(x=>x.id===v.id).status="published";store.set(s);toast("Grade publicada.");render()};
      $("#disc").onclick=()=>{if(!confirm("Descartar este rascunho?"))return;const s=store.get();s.versions=s.versions.filter(x=>x.id!==v.id);store.set(s);vid=null;toast("Rascunho descartado.");render()}}
    document.querySelectorAll(".tabs button").forEach(b=>b.onclick=()=>{tab=b.dataset.t;render()});
    if($("#flt"))$("#flt").onchange=e=>{filt=e.target.value;render()};
    document.querySelectorAll("[data-v]").forEach(b=>b.onclick=()=>{vid=+b.dataset.v;tab="grid";render()})};
  render()}

async function myGridPage(){
  const me=(await api("professors/"))[0],v=store.get().versions.find(x=>x.status==="published"),mine=v&&me?v.alloc.filter(a=>a.professorId===me.id):[];
  const mins=mine.reduce((n,a)=>n+mm(a.end)-mm(a.start),0)/60;
  $("#main").innerHTML=BANNER+`<div class="bar"><h2>Minha grade</h2>${v?`<span class="tag">Publicada em ${dt(v.createdAt)}</span>`:""}</div>`+
   (!v?'<div class="empty">Nenhuma grade publicada ainda. Quando o coordenador publicar, suas aulas aparecem aqui.</div>':!mine.length?'<div class="empty">Você não foi alocado em nenhuma aula nesta grade.</div>':
   `<div class="cards" style="margin-bottom:16px"><div class="card"><b>${mine.length}</b>aulas na semana</div><div class="card"><b>${mins.toFixed(1).replace(".0","")} h</b>carga alocada</div></div>${allocGrid(mine,v.slots)}`)}

$("#dlg").addEventListener("close",()=>$("#dlg").style.width="");
boot();
