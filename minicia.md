# Guia de Inicialização (`minicia.md`) — Grade Acadêmica

Este documento lista todas as dependências, variáveis de ambiente e comandos necessários para configurar, popular, testar e executar o sistema **Grade Acadêmica** (API Django REST + Front-end integrado + Motor Híbrido SA & Busca Tabu).

---

## 1. Pré-requisitos do Sistema

- **Python**: `3.10+` (recomendado `3.12+`)
- **Banco de Dados**: `SQLite 3` (já incluído nativamente no Python; o arquivo `db.sqlite3` é criado automaticamente na raiz do projeto)
- **Front-end**: HTML5 / CSS3 / JavaScript Vanilla servidos diretamente pelo Django (não requer Node.js ou `npm`)

---

## 2. Dependências Python (`requirements.txt`)

As bibliotecas necessárias para rodar o projeto estão listadas no arquivo `requirements.txt`:

| Pacote | Versão Mínima | Finalidade |
| :--- | :--- | :--- |
| `Django` | `>= 5.0` | Framework web principal, ORM, autenticação e servidor de arquivos estáticos |
| `djangorestframework` | `>= 3.15` | Construção da API REST e autenticação via Token (`rest_framework.authtoken`) |

> **Dependências transitivas instaladas automaticamente pelo `pip`:** `asgiref` e `sqlparse`.

---

## 3. Passo a Passo: Instalação e Execução Rápida

### 3.1. Criar e ativar o ambiente virtual

**No macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**No Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3.2. Instalar as dependências

Com o ambiente virtual ativado:
```bash
pip install -r requirements.txt
```
*(Ou, caso utilize o gerenciador `uv`: `uv pip install -r requirements.txt`)*

### 3.3. Executar as migrações do banco de dados

Cria as tabelas necessárias no arquivo `db.sqlite3` e **já popula automaticamente todas as contas nativas do sistema** (migração `0005_native_accounts`):
```bash
python manage.py migrate
```

### 3.4. Restaurar / sincronizar os dados nativos manualmente (Opcional)

As contas nativas já são criadas automaticamente no `migrate` e também verificadas automaticamente ao subir o `runserver`. Caso queira restaurar o estado inicial das 21 contas nativas (1 gestor, 2 coordenadores — um com 2 cursos `SI` e `CC` e outro com 1 curso `ES` — e 18 professores, removendo quaisquer contas extras):
```bash
python manage.py seed_demo
```
> Caso `DJANGO_DEBUG=0` esteja definido e mesmo assim deseje forçar a restauração:
> ```bash
> python manage.py seed_demo --force
> ```

### 3.5. Iniciar o servidor de desenvolvimento

```bash
python manage.py runserver
```
> **Nota:** Mesmo que você apenas dê `git pull` e rode `python manage.py runserver` diretamente, o sistema verifica na inicialização (`CoreConfig.ready()`) se as 21 contas nativas e os 3 cursos estão presentes e sincroniza automaticamente caso necessário.

O sistema estará disponível no navegador em:
- **URL:** `http://127.0.0.1:8000/`

Para rodar em outra porta (ex.: `8080`):
```bash
python manage.py runserver 8080
```

---

## 4. Credenciais Nativas de Acesso

Todas as 21 contas nativas do sistema utilizam a senha padrão:
- **Senha:** `Demo@12345`

| Perfil | E-mail de Login | Nome | Descrição |
| :--- | :--- | :--- | :--- |
| **Gestor (1)** | `gestor@demo.com` | Gestor Demo | Cadastra coordenadores, professores e horários (`slots`) |
| **Coordenadora (2 cursos)** | `coord@demo.com` | Coordenadora Demo | Coordena **2 cursos**: `SI` (Sistemas de Informação) e `CC` (Ciência da Computação); também possui perfil docente (`COORD-001`) |
| **Coordenador (1 curso)** | `coord2@demo.com` | Roberto Almeida | Coordena **1 só curso**: `ES` (Engenharia de Software) |
| **Professores (18)** | `prof1@demo.com` até `prof18@demo.com` | Carlos Silva .. Thiago Moreira (`DOC-001` a `DOC-018`) | Consultam a grade publicada e gerenciam sua disponibilidade semanal (`prof1`–`prof8` atuam em `SI`/`CC`; `prof9`–`prof18` atuam em `ES`) |

### Criar um usuário Gestor manualmente (sem `seed_demo`)

Caso queira iniciar o banco limpo e criar apenas o gestor real:
```bash
python manage.py shell -c 'from core.models import User; User.objects.create_user(username="admin@instituicao.edu", email="admin@instituicao.edu", first_name="Gestor", password="SuaSenhaSegura123", role="manager")'
```

---

## 5. Outros Comandos Úteis do Sistema

| Comando | Descrição |
| :--- | :--- |
| `python manage.py test` | Executa a suíte automatizada de testes da API, permissões e motor de otimização |
| `python manage.py makemigrations` | Gera novas migrações caso os modelos em `core/models.py` sejam alterados |
| `python manage.py migrate` | Aplica as migrações pendentes no banco de dados |
| `python manage.py flush` | Limpa todos os dados do banco `db.sqlite3` mantendo a estrutura de tabelas |
| `python manage.py shell` | Abre o console interativo do Django com os modelos carregados |

---

## 6. Variáveis de Ambiente (Produção)

Por padrão, o sistema roda em modo de desenvolvimento (`DJANGO_DEBUG=1`). Para execução em produção, defina as seguintes variáveis de ambiente antes de iniciar o servidor:

```bash
export DJANGO_DEBUG=0
export DJANGO_SECRET_KEY="sua-chave-secreta-forte-aqui"
export ALLOWED_HOSTS="seudominio.com,127.0.0.1,localhost"
```
