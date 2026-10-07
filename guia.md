# Como rodar a Grade Acadêmica em um novo PC

Este guia é para Windows. Cada computador terá seu próprio banco de dados.

## 1. Instale os programas

- [.NET SDK 10](https://dotnet.microsoft.com/en-us/download/dotnet/10.0): escolha **SDK**, Windows e a arquitetura do PC, normalmente x64. Não escolha apenas Runtime.
- [PostgreSQL 18](https://www.postgresql.org/download/windows/): instale o servidor e as ferramentas de linha de comando no caminho padrão.

Os scripts utilizam esta pasta:

    C:\Program Files\PostgreSQL\18\bin

Ela deve conter initdb.exe, pg_ctl.exe, psql.exe e createdb.exe. Se instalar em outro lugar, ajuste os caminhos em Setup.ps1, GetAccess.ps1 e Stop.ps1.

O pgAdmin é opcional, para consultar o banco visualmente. Não precisa instalar Node.js, Docker ou um editor de código para rodar o sistema.

## 2. Baixe o projeto do GitHub

1. Abra o repositório.
2. Clique em **Code → Download ZIP**.
3. Extraia o ZIP para uma pasta local, de preferência fora do OneDrive.
4. Entre na pasta que contém **GradeAcademica.csproj** e **Setup.ps1**.

Se você usa Git, também pode clonar o repositório em vez de baixar o ZIP.

## 3. Abra o PowerShell nessa pasta

No Explorador de Arquivos, abra a pasta do projeto, digite **powershell** na barra de endereço e pressione Enter.

Confira as instalações executando um comando por vez:

    dotnet --list-sdks

Deve aparecer uma versão 10.0.x.

    & 'C:\Program Files\PostgreSQL\18\bin\psql.exe' --version

Deve aparecer PostgreSQL 18.

Se o comando dotnet não for encontrado, feche e abra o PowerShell depois de instalar o SDK.

## 4. Inicie o sistema

Execute:

    dotnet restore

Depois:

    powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup.ps1 -StartApp

A primeira execução precisa de internet para baixar as dependências do projeto. O script compila e inicia o site, cria um PostgreSQL separado na porta 55432 e prepara o banco, tabelas, horários e coordenador automaticamente.

Não é necessário criar o banco manualmente ou importar arquivos SQL pelo pgAdmin.

## 5. Abra o site e entre

Abra no navegador:

    http://localhost:5049

Na pasta do projeto, abra **.local/acesso-inicial.json** com o Bloco de Notas. Use os valores:

- **Email**: login do coordenador; você também pode usar **Matricula**.
- **Password**: senha inicial do coordenador.

O coordenador começa associado a Engenharia de Software. Professores podem criar suas contas na tela de login.

Se você alterar a senha pelo sistema, use a nova senha nas próximas entradas. O arquivo continua mostrando apenas a senha inicial.

## 6. Comece a cadastrar

1. Cadastre o semestre letivo.
2. Crie as turmas, informando período e turno.
3. Crie as disciplinas de cada turma e a quantidade de aulas semanais.
4. Cadastre contas de professores.
5. Envie os convites pelo perfil do coordenador.
6. Cada professor aceita seus convites e salva sua disponibilidade.
7. Monte a grade, clique em **Salvar alterações** e publique quando estiver completa.

## 7. Como abrir novamente

Abra o PowerShell na mesma pasta e execute:

    powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup.ps1 -StartApp

Depois abra http://localhost:5049. Os dados e as credenciais existentes são preservados.

Para parar o sistema e o banco deste projeto:

    powershell -NoProfile -ExecutionPolicy Bypass -File .\Stop.ps1

Isso não apaga os dados.

## Problemas comuns

- **Não encontra Setup.ps1:** abra o PowerShell na pasta correta, onde está GradeAcademica.csproj.
- **Não encontra PostgreSQL:** confira a versão 18 e o caminho de instalação.
- **Falha em dotnet restore:** confira a conexão com a internet e as mensagens do comando.
- **Site não abre:** confira a saída do Setup.ps1 e os arquivos .local/web-error.log e .local/web.log.
- **Banco não inicia:** consulte .local/postgres.log. A porta 55432 deve estar livre.
- **Porta do site ocupada:** verifique se outra aplicação está usando 5049.
- **Mudança visual não aparece:** pressione Ctrl + F5 no navegador.

O banco isolado usa o usuário grade_owner. As credenciais ficam em appsettings.Local.json; não use a senha do usuário postgres escolhida no instalador. Uma instalação PostgreSQL na porta 5432 é independente deste banco.

## Cuidados importantes

- Um novo PC começa com seu próprio banco: os dados do computador original não são copiados nem sincronizados automaticamente.
- Não apague .local/pgdata: essa pasta contém o banco.
- Não envie .local/, appsettings.Local.json ou appsettings.Testing.json ao GitHub. Preserve o .gitignore.
- Não compartilhe arquivos com senhas.
- localhost só abre no próprio computador. Para várias pessoas acessarem o mesmo banco, é necessário configurar hospedagem ou acesso remoto seguro.
- Não exponha a porta PostgreSQL na internet.

Para a lista de requisitos e instaladores, consulte [REQUIREMENTS.md](REQUIREMENTS.md).
