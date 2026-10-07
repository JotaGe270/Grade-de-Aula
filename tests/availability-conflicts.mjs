import assert from 'node:assert/strict';
const base=process.env.TEST_URL;
if(!base||!base.endsWith(':5051'))throw Error('Use somente o servidor isolado na porta 5051.');
let checks=0;
const check=(value,label)=>{assert.ok(value,label);checks++;console.log('OK: '+label);};
function client(){return{cookie:'',async call(path,body,status=200){
 const r=await fetch(base+'/api'+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json','X-Requested-With':'GradeAcademica',Cookie:this.cookie},body:body?JSON.stringify(body):undefined});
 const cookie=r.headers.get('set-cookie');if(cookie)this.cookie=cookie.split(';')[0];
 const text=await r.text();assert.equal(r.status,status,path+' '+text);checks++;return text?JSON.parse(text):null;
}};}
const c=client(),p=client(),q=client();
await c.call('/status');
await c.call('/login',await c.call('/test/coordinator-login',{}));
const password='TesteSomenteIsolado2026!';
for(const [user,name]of [[p,'Professor A'],[q,'Professor B']]){
 const account=await user.call('/register',{name,password});
 await user.call('/login',{email:account.email,password});
 user.id=(await user.call('/me')).id;
}
await c.call('/semesters',{year:2026,number:1});
await c.call('/semesters',{year:2026,number:2});
let data=await c.call('/data');
const sem=data.semesters.find(s=>s.semestre===1).id_sistema_letivo;
const sem2=data.semesters.find(s=>s.semestre===2).id_sistema_letivo;
const slots=data.slots.filter(s=>s.turno==='matutino'&&s.dia_semana===1);
const a=slots[0].id_slot,b=slots[1].id_slot;
const subjects=[];
for(let n=1;n<=7;n++){
 const user=n<=3||n===7?p:q,semester=n===7?sem2:sem;
 await c.call('/classes',{period:n,shift:'matutino',semester});
 data=await c.call('/data');
 const cls=data.classes.find(t=>t.periodo==n);
 const grade=data.grades.find(g=>g.id_turma===cls.id_turma);
 const disc=(await c.call('/disciplines',{name:'Disciplina '+n,workload:50,weeklySlots:1,class:cls.id_turma}))[0];
 const invite=(await c.call('/invitations',{discipline:disc.id_disciplina,professor:user.id}))[0];
 await user.call('/invitations/'+invite.id_convite+'/reply',{status:'aceito'});
 await user.call('/invitations/'+invite.id_convite+'/availability',{slots:[a,b]});
 subjects.push({user,grade:grade.id_grade,invite:invite.id_convite});
}
const first=subjects[0],second=subjects[3];
await c.call('/allocations',{grade:first.grade,invitation:first.invite,slot:a});
data=await p.call('/data');
check(data.availabilityConflicts.length===0,'Rascunho não marca conflito nem retira disponibilidades');
await p.call('/invitations/'+subjects[1].invite+'/availability',{slots:[a,b]});
await c.call('/grades/'+first.grade+'/publish',{});
data=await p.call('/data');
for(const s of subjects.slice(1,3)){
 check(data.availabilityConflicts.some(x=>x.id_convite===s.invite&&x.id_slot===a),'Conflito de grade finalizada em outra matéria do professor A');
 check(!data.availability.some(x=>x.id_convite===s.invite&&x.id_slot===a),'Publicação retira automaticamente o horário conflitante');
 check(data.availability.some(x=>x.id_convite===s.invite&&x.id_slot===b),'Horário livre preservado');
 await p.call('/invitations/'+s.invite+'/availability',{slots:[a,b]},400);
 await p.call('/invitations/'+s.invite+'/availability',{slots:[b]});
}
check(data.availability.some(x=>x.id_convite===first.invite&&x.id_slot===a),'Disponibilidade da própria aula publicada preservada');
check(data.availability.some(x=>x.id_convite===subjects[6].invite&&x.id_slot===a),'Mesmo professor em outro semestre não é bloqueado');
data=await q.call('/data');
check(data.availabilityConflicts.length===0,'Outro professor não é bloqueado pelo professor A');
check(data.availability.some(x=>x.id_convite===second.invite&&x.id_slot===a),'Disponibilidade do professor B preservada');
await c.call('/allocations',{grade:second.grade,invitation:second.invite,slot:a});
await c.call('/grades/'+second.grade+'/publish',{});
data=await q.call('/data');
for(const s of subjects.slice(4,6)){
 check(data.availabilityConflicts.some(x=>x.id_convite===s.invite&&x.id_slot===a),'Conflito independente nas matérias do professor B');
 check(!data.availability.some(x=>x.id_convite===s.invite&&x.id_slot===a),'Retirada automática nas matérias do professor B');
 await q.call('/invitations/'+s.invite+'/availability',{slots:[a]},400);
}
console.log('PASSOU: '+checks+' verificações; 2 professores, 7 disciplinas, 2 semestres.');
