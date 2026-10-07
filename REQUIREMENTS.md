# Requisitos e instaladores — Grade Acadêmica

Guia para executar o projeto localmente no Windows. O sistema usa ASP.NET Core e PostgreSQL, não Python.

## Instaladores obrigatórios

| Programa | Versão | Download oficial |
|---|---|---|
| .NET SDK | 10.0 | [Instalar .NET SDK 10](https://dotnet.microsoft.com/en-us/download/dotnet/10.0) |
| PostgreSQL | 18 | [Instalar PostgreSQL para Windows](https://www.postgresql.org/download/windows/) |

No .NET, escolha **SDK**, Windows e a arquitetura do computador (normalmente x64). Instalar somente o Runtime não basta para compilar este projeto.

No PostgreSQL, instale o servidor e as ferramentas de linha de comando. Os scripts esperam os executáveis nesta pasta:

    C:\Program Files\PostgreSQL\18\bin

Confira se ela contém initdb.exe, pg_ctl.exe, psql.exe e createdb.exe. Caso escolha outro caminho, ajuste Setup.ps1, GetAccess.ps1 e Stop.ps1.

Use uma versão do Windows compatível com os instaladores escolhidos. PowerShell e navegador também são necessários e normalmente já estão disponíveis. Instalar esses programas pode exigir permissão de administrador.

## Baixar os instaladores pelo terminal

Abra o PowerShell e confira se o Windows Package Manager está disponível:

    winget --version

Se não for reconhecido, instale ou atualize o **Instalador de Aplicativo (App Installer)** pela Microsoft Store, depois abra um novo PowerShell. Alternativamente, use os links oficiais acima.

Para **somente baixar**, sem instalar, execute um comando por vez:

    winget download --id Microsoft.DotNet.SDK.10 --exact --source winget --download-directory ".\instaladores"
    winget download --id PostgreSQL.PostgreSQL.18 --exact --source winget --download-directory ".\instaladores"

Os arquivos serão salvos na pasta instaladores do diretório atual. Revise eventuais termos apresentados pelo WinGet. Depois abra os instaladores baixados e siga os assistentes.

Para **baixar e instalar** diretamente pelo terminal:

    winget install --id Microsoft.DotNet.SDK.10 --exact --source winget
    winget install --id PostgreSQL.PostgreSQL.18 --exact --source winget --interactive

Autorize a elevação de administrador se solicitada. No PostgreSQL, mantenha o caminho C:\Program Files\PostgreSQL\18 e inclua as ferramentas de linha de comando. Feche e abra o terminal depois das instalações.

Se algum pacote não for encontrado, atualize o catálogo e tente novamente:

    winget source update

Fontes dos comandos: [documentação WinGet download](https://learn.microsoft.com/en-us/windows/package-manager/winget/download), [instalação .NET no Windows](https://learn.microsoft.com/en-us/dotnet/core/install/windows) e [manifestos PostgreSQL 18](https://github.com/microsoft/winget-pkgs/tree/master/manifests/p/PostgreSQL/PostgreSQL/18).

## Opcionais

- [Git](https://git-scm.com/downloads): para clonar e atualizar o repositório. Baixar ZIP pelo GitHub dispensa Git.
- pgAdmin: pode ser selecionado no instalador PostgreSQL, para visualizar o banco. Não é necessário para rodar o site.
- [Node.js](https://nodejs.org/en/download): apenas para executar os testes JavaScript.
- Editor de código: opcional. Visual Studio, VS Code e Python não são necessários para iniciar o sistema.

Docker não é obrigatório e ainda não está configurado neste projeto.

Comandos para baixar os opcionais (não necessários para rodar o site):

    winget download --id Git.Git --exact --source winget --download-directory ".\instaladores"
    winget download --id OpenJS.NodeJS.LTS --exact --source winget --download-directory ".\instaladores"

Para instalar em vez de apenas baixar, substitua download por install e retire --download-directory ".\instaladores". O pgAdmin pode ser selecionado no assistente de instalação do PostgreSQL.

## Primeira execução

1. Instale .NET SDK 10 e PostgreSQL 18.
2. Baixe ou clone o projeto. Extraia o ZIP, se necessário.
3. Abra o PowerShell na pasta que contém GradeAcademica.csproj e Setup.ps1.
4. Verifique as instalações:

    dotnet --list-sdks
    & 'C:\Program Files\PostgreSQL\18\bin\psql.exe' --version

A primeira saída deve incluir um SDK 10.0.x; a segunda deve mostrar PostgreSQL 18.

5. Execute os comandos abaixo nessa pasta:

    dotnet restore
    powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup.ps1 -StartApp

A primeira restauração exige internet para baixar o pacote Npgsql, já declarado no projeto. Não é necessário instalar esse pacote manualmente ou importar schema.sql no pgAdmin.

6. Abra http://localhost:5049.
7. Consulte .local/acesso-inicial.json para ver o e-mail/matrícula e a senha inicial do coordenador. Professores criam suas contas pela tela de login.

## Preparação automática

O script cria uma instância PostgreSQL exclusiva em .local/pgdata, na porta 55432, o banco grade_academica e credenciais locais aleatórias. A aplicação prepara as tabelas, horários e o coordenador associado a Engenharia de Software.

O PostgreSQL eventualmente instalado na porta 5432 é separado. A senha do usuário postgres escolhida no instalador não é a senha desse banco isolado.

Em um clone novo, as turmas, disciplinas e professores do computador original não aparecem. Cada instalação tem seu banco e não existe sincronização automática.

## Iniciar novamente e parar

Iniciar, preservando os dados:

    powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup.ps1 -StartApp

Parar a aplicação e o PostgreSQL do projeto, preservando os dados:

    powershell -NoProfile -ExecutionPolicy Bypass -File .\Stop.ps1

Se falhar, consulte .local/web-error.log, .local/web.log e .local/postgres.log. Verifique se as portas 5049 e 55432 estão livres e se os instaladores estão nos caminhos esperados.

## Compartilhar no GitHub

Envie código, scripts, GradeAcademica.csproj, schema.sql, este guia e .gitignore.

Não envie nem force a inclusão de:

- .local/ (dados, backups, credenciais e logs);
- appsettings.Local.json;
- appsettings.Testing.json;
- bin/ e obj/.

Esses arquivos estão ignorados pelo Git. Cada pessoa deve gerar suas próprias credenciais executando Setup.ps1. O arquivo de acesso guarda a senha inicial, não acompanha mudanças de senha feitas pelo perfil.

## Acesso remoto

localhost significa o próprio computador. Esses comandos não publicam o site na internet ou liberam acesso pela rede. Para todos usarem o mesmo banco, será necessário hospedar o sistema ou configurar acesso remoto seguro ao servidor. Não exponha o PostgreSQL na internet.

Para uso permanente, evite colocar .local/pgdata em pastas sincronizadas pelo OneDrive; use armazenamento local adequado.
