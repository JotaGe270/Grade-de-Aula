# Grade Acadêmica — API + Front-end + Motor Híbrido (SA + Busca Tabu)
## Rodar
    pip install -r requirements.txt
    python manage.py migrate          # já cria automaticamente as contas nativas do sistema
    python manage.py runserver        # abre http://127.0.0.1:8000/
Logins nativos (senha padrão: `Demo@12345`):
- **1 Gestor:** `gestor@demo.com`
- **2 Coordenadores:** `coord@demo.com` (2 cursos: `SI` e `CC`) e `coord2@demo.com` (1 curso: `ES`)
- **18 Professores:** `prof1@demo.com` até `prof18@demo.com`
Para restaurar os dados nativos a qualquer momento: `python manage.py seed_demo`
Para criar o gestor real: `python manage.py shell` → User.objects.create_user(username=e, email=e, password=..., role="manager")
## Testes
    python manage.py test
## Produção
DJANGO_DEBUG=0, DJANGO_SECRET_KEY e ALLOWED_HOSTS obrigatórios (Postgres/HTTPS a configurar).
## Estrutura
- `core/` — API (modelos, serializers, permissões, testes)
- `core/solver.py` — Motor Híbrido de Otimização (`HybridTimetableSolver`: Simulated Annealing + Tabu Search)
- `config/` — Django (settings, rotas)
- `frontend/index.html` — página
- `frontend/static/css/app.css` — componentes visuais
- `frontend/static/js/app.js` — comportamento da página e integração da tela de Alocação
## Decisões
- Desativar = PATCH {is_active:false}; excluir = DELETE (definitivo). Curso com disciplinas não pode ser excluído (409).
- Tela de Alocação integrada ao backend (`/api/schedules/generate/`, `/api/schedules/<id>/publish/`) com suporte a 3 modos de otimização: **Híbrido (SA + Busca Tabu)**, **Simulated Annealing** e **Busca Tabu**.
- Gestor cadastra coordenadores, professores e horários. Coordenador cadastra cursos, disciplinas e salas.
- A sala é volátil: a mesma turma pode mudar de sala de um dia para o outro, então nenhum perfil aloca sala na grade.
- "Restrições" = disponibilidade semanal (Availability) + carga máxima do professor + conflitos de curso/professor + preferências suaves (dias preferidos, habilitação na disciplina, distribuição semanal e redução de janelas).
- Token DRF; permissões por perfil no servidor (core/views.py: RolePerm).
