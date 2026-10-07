import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const base='http://localhost:5049';
const status=await fetch(base+'/api/status');assert.equal(status.status,200);assert.equal((await status.json()).application,'GradeAcademica');
const settings=JSON.parse((await readFile(new URL('../.local/acesso-inicial.json',import.meta.url),'utf8')).replace(/^\uFEFF/,''));
const auth=await fetch(base+'/api/login',{method:'POST',headers:{'Content-Type':'application/json','X-Requested-With':'GradeAcademica'},body:JSON.stringify({email:settings.Email,password:settings.Password})});assert.equal(auth.status,200);
const headers={Cookie:auth.headers.get('set-cookie').split(';')[0]};
const me=await (await fetch(base+'/api/me',{headers})).json();assert.equal(me.role,'coordenador');assert.match(me.matricula,/^\d{8}$/);assert.equal(me.email,me.matricula+'@ugb.com.br');
const data=await (await fetch(base+'/api/data',{headers})).json();assert.equal(data.slots.length,48);
for(const asset of ['/','/app.js','/style.css']){const r=await fetch(base+asset);assert.equal(r.status,200);assert.ok((await r.text()).length>100);}
assert.equal((await fetch(base+'/appsettings.Local.json')).status,404);
assert.equal((await fetch(base+'/.local/acesso-inicial.json')).status,404);
console.log('Smoke final passou: PostgreSQL, login do coordenador, matrícula/e-mail, 48 horários, interface e proteção dos arquivos locais.');
