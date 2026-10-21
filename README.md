# Grade Acadêmica — Fase 1 (API + front-end dos 3 perfis)
## Rodar
    pip install -r requirements.txt
    python manage.py migrate
    python manage.py seed_demo        # só em DEBUG; senha demo: Demo@12345
    python manage.py runserver        # abre http://127.0.0.1:8000/
Logins demo: gestor@demo.com, coord@demo.com, prof1@demo.com, prof2@demo.com, prof3@demo.com, prof4@demo.com
Para criar o gestor real: `python manage.py shell` → User.objects.create_user(username=e, email=e, password=..., role="manager")
## Testes
    python manage.py test
## Produção
DJANGO_DEBUG=0, DJANGO_SECRET_KEY e ALLOWED_HOSTS obrigatórios (Postgres/HTTPS a configurar).
## Estrutura
- `core/` — API (modelos, serializers, permissões)
- `config/` — Django (settings, rotas)
- `frontend/index.html` — página
- `frontend/static/css/app.css` — componentes visuais
- `frontend/static/js/app.js` — comportamento da página
## Decisões
- Desativar = PATCH {is_active:false}; excluir = DELETE (definitivo). Curso com disciplinas não pode ser excluído (409).
- Tela de Alocação é uma prévia visual (motor real ainda não implementado) e não fixa sala.
- Gestor cadastra coordenadores, professores e horários. Coordenador cadastra cursos, disciplinas e salas.
- A sala é volátil: a mesma turma pode mudar de sala de um dia para o outro, então nenhum perfil aloca sala na grade.
- "Restrições" = disponibilidade semanal (Availability) + carga máxima do professor.
- Token DRF; permissões por perfil no servidor (core/views.py: RolePerm).
