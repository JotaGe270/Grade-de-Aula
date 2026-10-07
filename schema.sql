CREATE SCHEMA IF NOT EXISTS grade_app;
CREATE TABLE IF NOT EXISTS grade_app.schema_version(version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS grade_app.usuario(
 id_usuario serial PRIMARY KEY,nome varchar(150) NOT NULL,email varchar(150) NOT NULL UNIQUE,
 senha_hash text NOT NULL,role varchar(30) NOT NULL CHECK(role IN('coordenador','professor')),
 matricula_funcional varchar(8) NOT NULL UNIQUE CHECK(matricula_funcional ~ '^[0-9]{8}$'),titulacao varchar(100),
 CHECK(email=matricula_funcional||'@ugb.com.br')
);
CREATE TABLE IF NOT EXISTS grade_app.sistema_letivo(
 id_sistema_letivo serial PRIMARY KEY,ano int NOT NULL CHECK(ano BETWEEN 2000 AND 2200),
 semestre int NOT NULL CHECK(semestre IN(1,2)),UNIQUE(ano,semestre)
);
CREATE TABLE IF NOT EXISTS grade_app.curso(
 id_curso serial PRIMARY KEY,nome varchar(150) NOT NULL,id_coordenador int REFERENCES grade_app.usuario,
 UNIQUE(id_coordenador,nome)
);
-- Migração 3: o coordenador atual fica exclusivamente em Engenharia de Software.
ALTER TABLE grade_app.curso ALTER COLUMN id_coordenador DROP NOT NULL;
UPDATE grade_app.curso SET id_coordenador=NULL
WHERE id_coordenador=(SELECT id_usuario FROM grade_app.usuario WHERE matricula_funcional='20269184')
  AND nome<>'Engenharia de Software'
  AND NOT EXISTS(SELECT 1 FROM grade_app.schema_version WHERE version=3);
CREATE UNIQUE INDEX IF NOT EXISTS curso_coordenador_unico ON grade_app.curso(id_coordenador);
INSERT INTO grade_app.schema_version(version) VALUES(3) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS grade_app.turma(
 id_turma serial PRIMARY KEY,periodo varchar(150) NOT NULL,turno varchar(20) NOT NULL CHECK(turno IN('matutino','noturno')),
 id_curso int NOT NULL REFERENCES grade_app.curso,id_sistema_letivo int NOT NULL REFERENCES grade_app.sistema_letivo,
 UNIQUE(id_curso,id_sistema_letivo,periodo,turno)
);
CREATE TABLE IF NOT EXISTS grade_app.disciplina(
 id_disciplina serial PRIMARY KEY,nome varchar(150) NOT NULL,
 carga_horaria int NOT NULL CHECK(carga_horaria>0),slots_semanais int NOT NULL CHECK(slots_semanais BETWEEN 1 AND 24),
 id_turma int NOT NULL REFERENCES grade_app.turma
);
-- Migração 2: remove somente o código dispensado, preservando disciplinas e vínculos.
ALTER TABLE grade_app.disciplina DROP COLUMN IF EXISTS codigo;
CREATE TABLE IF NOT EXISTS grade_app.slot(
 id_slot serial PRIMARY KEY,dia_semana int NOT NULL CHECK(dia_semana BETWEEN 1 AND 6),
 turno varchar(20) NOT NULL CHECK(turno IN('matutino','noturno')),numero_aula int NOT NULL CHECK(numero_aula BETWEEN 1 AND 4),
 hora_inicio time NOT NULL,hora_fim time NOT NULL,CHECK(hora_fim>hora_inicio),UNIQUE(dia_semana,turno,numero_aula)
);
INSERT INTO grade_app.slot(dia_semana,turno,numero_aula,hora_inicio,hora_fim)
SELECT dia,turno,n,ini::time,fim::time FROM generate_series(1,6) dia CROSS JOIN(VALUES
 ('matutino',1,'08:10','09:00'),('matutino',2,'09:00','09:50'),('matutino',3,'10:10','11:00'),('matutino',4,'11:00','11:50'),
 ('noturno',1,'19:10','20:00'),('noturno',2,'20:00','20:50'),('noturno',3,'21:10','22:00'),('noturno',4,'22:00','22:50')
) s(turno,n,ini,fim) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS grade_app.convite_docente(
 id_convite serial PRIMARY KEY,id_coordenador int REFERENCES grade_app.usuario,
 id_professor int NOT NULL REFERENCES grade_app.usuario,id_disciplina int NOT NULL REFERENCES grade_app.disciplina,
 status varchar(20) NOT NULL DEFAULT 'pendente' CHECK(status IN('pendente','aceito','recusado','cancelado')),
 data_envio timestamptz NOT NULL DEFAULT now(),data_resposta timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS convite_ativo ON grade_app.convite_docente(id_disciplina) WHERE status IN('pendente','aceito');
CREATE TABLE IF NOT EXISTS grade_app.disponibilidade(
 id_convite int NOT NULL REFERENCES grade_app.convite_docente,id_slot int NOT NULL REFERENCES grade_app.slot,
 PRIMARY KEY(id_convite,id_slot)
);
CREATE TABLE IF NOT EXISTS grade_app.grade(
 id_grade serial PRIMARY KEY,id_turma int NOT NULL REFERENCES grade_app.turma,versao int NOT NULL,
 status varchar(20) NOT NULL CHECK(status IN('rascunho','publicada','arquivada')),
 data_criacao timestamptz NOT NULL DEFAULT now(),data_publicacao timestamptz,UNIQUE(id_turma,versao)
);
CREATE UNIQUE INDEX IF NOT EXISTS grade_rascunho ON grade_app.grade(id_turma) WHERE status='rascunho';
CREATE UNIQUE INDEX IF NOT EXISTS grade_publicada ON grade_app.grade(id_turma) WHERE status='publicada';
CREATE TABLE IF NOT EXISTS grade_app.alocacao_grade(
 id_alocacao serial PRIMARY KEY,id_grade int NOT NULL REFERENCES grade_app.grade,
 id_convite int NOT NULL REFERENCES grade_app.convite_docente,id_slot int NOT NULL REFERENCES grade_app.slot,
 UNIQUE(id_grade,id_slot)
);
CREATE INDEX IF NOT EXISTS alocacao_convite ON grade_app.alocacao_grade(id_convite);
CREATE INDEX IF NOT EXISTS convite_professor ON grade_app.convite_docente(id_professor);
CREATE OR REPLACE FUNCTION grade_app.valida_alocacao() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE turma_id int; semestre_id int; turno_turma text; professor_id int; disciplina_id int;
 horario grade_app.slot%ROWTYPE; limite int;
BEGIN
 PERFORM pg_advisory_xact_lock(741963);
 SELECT g.id_turma,t.id_sistema_letivo,t.turno INTO turma_id,semestre_id,turno_turma
 FROM grade_app.grade g JOIN grade_app.turma t USING(id_turma) WHERE g.id_grade=NEW.id_grade AND g.status='rascunho';
 IF turma_id IS NULL THEN RAISE EXCEPTION 'A grade precisa estar em rascunho.' USING ERRCODE='P0001'; END IF;
 SELECT i.id_professor,i.id_disciplina,d.slots_semanais INTO professor_id,disciplina_id,limite
 FROM grade_app.convite_docente i JOIN grade_app.disciplina d USING(id_disciplina)
 WHERE i.id_convite=NEW.id_convite AND i.status='aceito' AND d.id_turma=turma_id;
 IF professor_id IS NULL THEN RAISE EXCEPTION 'Selecione um convite aceito desta turma.'; END IF;
 SELECT * INTO horario FROM grade_app.slot WHERE id_slot=NEW.id_slot;
 IF horario.turno<>turno_turma OR NOT EXISTS(SELECT 1 FROM grade_app.disponibilidade WHERE id_convite=NEW.id_convite AND id_slot=NEW.id_slot)
 THEN RAISE EXCEPTION 'O professor não informou disponibilidade para esse horário.'; END IF;
 IF EXISTS(
  SELECT 1 FROM grade_app.alocacao_grade a JOIN grade_app.grade g USING(id_grade)
  JOIN grade_app.turma t USING(id_turma) JOIN grade_app.convite_docente i USING(id_convite) JOIN grade_app.slot s USING(id_slot)
  WHERE a.id_alocacao IS DISTINCT FROM NEW.id_alocacao AND g.status IN('rascunho','publicada')
  AND t.id_sistema_letivo=semestre_id AND s.dia_semana=horario.dia_semana
  AND s.hora_inicio<horario.hora_fim AND horario.hora_inicio<s.hora_fim
  AND (g.id_grade=NEW.id_grade OR (g.id_turma<>turma_id AND (i.id_professor=professor_id OR t.id_turma=turma_id)))
  AND (t.id_turma=turma_id OR i.id_professor=professor_id)
 ) THEN RAISE EXCEPTION 'Conflito: professor ou turma já tem aula nesse horário e semestre.'; END IF;
 IF (SELECT count(*) FROM grade_app.alocacao_grade a JOIN grade_app.convite_docente i USING(id_convite)
     WHERE a.id_grade=NEW.id_grade AND i.id_disciplina=disciplina_id AND a.id_alocacao IS DISTINCT FROM NEW.id_alocacao)>=limite
 THEN RAISE EXCEPTION 'A quantidade semanal dessa disciplina já foi preenchida.'; END IF;
 RETURN NEW;
END $$;
CREATE OR REPLACE TRIGGER valida_alocacao BEFORE INSERT OR UPDATE ON grade_app.alocacao_grade FOR EACH ROW EXECUTE FUNCTION grade_app.valida_alocacao();
INSERT INTO grade_app.schema_version(version) VALUES(1) ON CONFLICT DO NOTHING;
INSERT INTO grade_app.schema_version(version) VALUES(2) ON CONFLICT DO NOTHING;
