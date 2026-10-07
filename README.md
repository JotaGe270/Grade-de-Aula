# UGB — Gestão de grade acadêmica

Para instalar em outro computador, consulte [REQUIREMENTS.md](REQUIREMENTS.md), com os instaladores e o passo a passo.

Guia prático para um novo PC: [guia.md](guia.md).

Aplicação web local em ASP.NET Core 10 e PostgreSQL, baseada no diagrama fornecido. A primeira versão usa montagem manual da grade. Nenhum algoritmo de organização automática foi implementado.

## Abrir e entrar

O sistema local está em **http://localhost:5049**.

- Acesso do coordenador: `.local/acesso-inicial.json`.
- Contas dos professores de demonstração: `.local/contas-demonstracao.json`.
- Configuração e senha inicial do coordenador: `appsettings.Local.json`.
- Resultado dos testes: `.local/test-results.json`.

Esses arquivos contêm credenciais locais e são ignorados pelo Git. A senha do coordenador é aleatória. Use o e-mail ou a matrícula e a senha indicada no arquivo de acesso. A página Meu perfil permite trocar a senha e atualizar nome e titulação.

Professores podem criar sua conta na tela de login. O sistema gera matrícula e e-mail; o perfil público de cadastro é sempre professor. Não há escolha de perfil privilegiado nesse formulário.

## Matrícula e e-mail

Todos os perfis, inclusive o coordenador, têm matrícula única de oito dígitos: ano de criação no fuso de São Paulo + quatro números aleatórios, com zeros à esquerda quando necessário. Exemplo: `20260427`, e-mail `20260427@ugb.com.br`.

O identificador é gerado no servidor e protegido por restrições únicas no PostgreSQL. Em caso de colisão, o sistema sorteia outra matrícula. O espaço numérico permite até 10.000 matrículas por ano. O e-mail é um identificador institucional de login; o sistema não cria uma caixa postal real no domínio UGB.

## Fluxo do coordenador

1. O coordenador já está vinculado a **Engenharia de Software**. Em **Turmas e semestres**, cadastre um semestre letivo e uma turma matutina ou noturna. O curso é preenchido pelo servidor; não há cadastro ou escolha de outros cursos.
2. Em **Disciplinas**, selecione a turma e informe nome, carga horária total e quantidade de aulas semanais de 50 minutos.
3. Em **Convites**, selecione a disciplina, busque o professor cadastrado por nome ou matrícula e clique em Selecionar. Envie o convite interno.
4. Acompanhe o status e consulte a disponibilidade recebida. Há um convite pendente ou aceito por disciplina; após recusa ou cancelamento, é possível convidar novamente.
5. Em **Montagem da grade**, selecione a turma/versão, o convite aceito e um horário disponível. Adicione as aulas manualmente.
6. Para mudar um horário do rascunho, remova a aula e adicione o novo horário. A remoção não altera uma versão já publicada.
7. Publique quando todas as disciplinas tiverem exatamente a quantidade semanal de aulas definida.
8. Para alterar uma grade publicada, clique em **Criar revisão**. A versão anterior segue visível aos professores até a publicação da revisão; depois fica arquivada.

## Fluxo do professor

1. Crie sua conta e guarde a matrícula e o e-mail gerados.
2. Entre no sistema e abra **Meus convites**.
3. Aceite ou recuse o convite.
4. Após aceitar, abra **Informar disponibilidade** e marque os horários na matriz semanal. Salve.
5. Em **Minhas aulas**, consulte todas as aulas publicadas por semestre, curso e período da turma. Rascunhos não aparecem como aulas oficiais.

Uma disponibilidade pertence ao convite, portanto pode ser diferente entre disciplinas. Horários que já possuem alocações em rascunhos ou grades publicadas não podem ser retirados sem a intervenção do coordenador.

## Horários

A matriz contempla segunda a sábado. Sábado é uma opção; não precisa ser utilizado. Os intervalos não são slots de aula.

| Aula | Matutino | Noturno |
|---|---|---|
| 1ª | 08:10–09:00 | 19:10–20:00 |
| 2ª | 09:00–09:50 | 20:00–20:50 |
| Intervalo | 09:50–10:10 | 20:50–21:10 |
| 3ª | 10:10–11:00 | 21:10–22:00 |
| 4ª | 11:00–11:50 | 22:00–22:50 |

O período da turma (ex.: 3º período) é separado do semestre letivo (ex.: 2026/2). A quantidade semanal é explícita: a carga horária total não é convertida automaticamente, pois faltam a definição de horas-aula/horas-relógio e o calendário de semanas letivas.

## Regras implementadas

- Login no banco, hash de senha com PasswordHasher, cookie HttpOnly/SameSite, limite de tentativas e proteção de requisições de alteração.
- Matrícula e e-mail gerados para coordenador e professor.
- Busca de professores cadastrados por nome ou matrícula.
- Convites exclusivamente internos, sem e-mail externo, token ou link de aceite.
- Aceitação, recusa e cancelamento, com datas registradas.
- Disponibilidade somente após aceite e no turno da turma.
- Cada coordenador está vinculado a um único curso, com unicidade garantida no PostgreSQL. Ele gerencia somente as turmas, disciplinas, convites e grades desse curso; professor acessa seus convites e aulas.
- Professor e turma não podem ter aulas sobrepostas no mesmo semestre. Horários iguais em semestres diferentes são permitidos.
- Aulas respeitam disponibilidade, disciplina/turma e quantidade semanal.
- Rascunho, publicação, revisão e histórico de versões.
- Transações e bloqueio consultivo PostgreSQL serializam alterações da grade; a trigger valida conflitos também no banco.

Rascunhos de outras turmas reservam os horários do professor, assim como grades publicadas. Uma revisão da mesma turma pode repetir os horários da sua versão publicada, pois representa uma substituição futura dela.

## Executar novamente

Pré-requisitos já utilizados neste computador: .NET 10 e os binários de PostgreSQL 18 em `C:\Program Files\PostgreSQL\18\bin`.

No PowerShell, dentro desta pasta:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup.ps1 -StartApp
```

O script gera senhas locais quando necessário, inicializa uma instância PostgreSQL exclusiva em `.local/pgdata`, inicia na porta **55432**, cria o banco **grade_academica** e inicia a aplicação em **5049**. É reutilizável: dados e credenciais existentes são preservados. A instância ou os bancos PostgreSQL preexistentes na porta 5432 não são alterados.

O início automático verifica a aplicação, aplica `schema.sql`, cria o coordenador e salva o arquivo de acesso inicial. Para atualizar esse arquivo posteriormente:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\GetAccess.ps1
```

Esse arquivo informa a senha original de bootstrap, não uma senha que você tenha alterado posteriormente.

Para desenvolvimento, pare somente o processo deste projeto antes de recompilar; depois execute:

```powershell
dotnet build
dotnet run --no-launch-profile --urls http://localhost:5049
```

O banco tem usuário `grade_owner`. A senha e a conexão completa estão no arquivo local de configuração. Uma configuração externa pode substituir a conexão usando `ConnectionStrings__Postgres`.

## Banco e relação com o diagrama

Todas as tabelas ficam no esquema `grade_app`; o esquema `public` não é modificado. O SQL original não precisa ser executado antes desta aplicação.

| Entidade | Implementação |
|---|---|
| Usuário / coordenador / professor | `usuario`, com perfil, matrícula, e-mail e hash de senha |
| Semestre letivo | `sistema_letivo` |
| Curso e turma | `curso` e `turma` |
| Disciplina oferecida à turma | `disciplina`, vinculada diretamente à turma |
| Convite / atribuição docente | `convite_docente`; aceite representa o vínculo confirmado |
| Horário | `slot`, com dia, turno, número da aula e horários fixos |
| Disponibilidade | `disponibilidade`, vinculada ao convite e slot |
| Versão da grade | `grade` |
| Aula alocada | `alocacao_grade` |
| Registro de versão do esquema | `schema_version` |

Essa versão usa a disciplina como oferta da turma e não exige código de matéria. A separação futura entre catálogo de disciplinas e ofertas é compatível com a evolução do projeto. Os arquivos SQL enviados serviram como referência; os dados e IDs dos scripts de teste antigos não foram importados.

## Verificação

```powershell
node .\tests\integration.mjs
```

O teste cria dados de demonstração e contas próprias na instância local; cada execução cria um conjunto novo. Não deve ser executado em um banco de produção. Verifica autenticação, permissões, geração de matrícula, convites, disponibilidade, horários, conflitos, concorrência, publicação, revisão, isolamento entre professores e separação entre semestres.

## Evolução futura

A organização automática não faz parte desta entrega. Os convites aceitos, disponibilidades por slot, aulas semanais e regras de conflito já oferecem a base de dados para um futuro gerador de sugestões.

Antes de disponibilizar para toda a instituição, será necessário preparar hospedagem com HTTPS, backups/restore, administração de coordenadores, recuperação de conta, calendário letivo e política de cadastro. A execução entregue é local; não foi publicada na internet. O banco isolado está dentro do diretório de trabalho no OneDrive: para operação permanente, use armazenamento próprio do servidor PostgreSQL, fora de sincronização de arquivos.
