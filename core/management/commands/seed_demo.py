from datetime import time
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from core.models import *

DEMO_PASSWORD = "Demo@12345"  # senha padrão das contas nativas

NATIVE_EMAILS = (
    "gestor@demo.com",
    "coord@demo.com",
    "coord2@demo.com",
    *(f"prof{i}@demo.com" for i in range(1, 19)),
)


def seed_native_data(preserve_schedules=False):
    # Remove quaisquer outras contas que não sejam as 21 contas nativas (1 gestor, 2 coordenadores, 18 professores)
    User.objects.exclude(email__in=NATIVE_EMAILS).delete()
    Professor.objects.exclude(user__email__in=NATIVE_EMAILS).delete()

    def mk(email, name, role):
        u, created = User.objects.update_or_create(
            email=email,
            defaults=dict(username=email, first_name=name, role=role, is_active=True),
        )
        if created or not preserve_schedules or not u.has_usable_password():
            u.set_password(DEMO_PASSWORD)
            u.save()
        return u

    # 1 Conta de Gestor
    mk("gestor@demo.com", "Gestor Demo", "manager")

    # 2 Contas de Coordenador:
    # - coord@demo.com: 2 cursos (SI e CC)
    # - coord2@demo.com: 1 só curso (ES)
    coord = mk("coord@demo.com", "Coordenadora Demo", "coordinator")
    coord2 = mk("coord2@demo.com", "Roberto Almeida", "coordinator")

    # Coordenadora 1 também pode dar aulas (possui perfil Professor)
    coord_prof, _ = Professor.objects.update_or_create(
        user=coord,
        defaults=dict(institutional_id="COORD-001", max_weekly_hours=10, is_active=True),
    )

    # 18 Contas de Professor (prof1@demo.com .. prof18@demo.com)
    prof_specs = [
        ("prof1@demo.com", "Carlos Silva", 12),
        ("prof2@demo.com", "Ana Lima", 12),
        ("prof3@demo.com", "Bruno Costa", 12),
        ("prof4@demo.com", "Carla Souza", 12),
        ("prof5@demo.com", "Diego Martins", 12),
        ("prof6@demo.com", "Eduardo Rocha", 10),
        ("prof7@demo.com", "Fernanda Alves", 2),
        ("prof8@demo.com", "Gabriel Mendes", 12),
        ("prof9@demo.com", "Helena Castro", 12),
        ("prof10@demo.com", "Igor Ribeiro", 12),
        ("prof11@demo.com", "Juliana Freitas", 12),
        ("prof12@demo.com", "Lucas Barbosa", 12),
        ("prof13@demo.com", "Mariana Teixeira", 12),
        ("prof14@demo.com", "Nicolas Cardoso", 12),
        ("prof15@demo.com", "Olivia Nascimento", 12),
        ("prof16@demo.com", "Paulo Henrique", 12),
        ("prof17@demo.com", "Renata Gomes", 12),
        ("prof18@demo.com", "Thiago Moreira", 12),
    ]
    profs = []
    for idx, (email, name, max_h) in enumerate(prof_specs, start=1):
        u = mk(email, name, "professor")
        p, _ = Professor.objects.update_or_create(
            user=u,
            defaults=dict(institutional_id=f"DOC-{idx:03d}", max_weekly_hours=max_h, is_active=True),
        )
        profs.append(p)

    # Coordenadora 1 (coord@demo.com) responsável por 2 cursos (SI e CC)
    c_si, _ = Course.objects.update_or_create(
        code="SI",
        defaults=dict(name="Sistemas de Informação", coordinator=coord, is_active=True),
    )
    c_cc, _ = Course.objects.update_or_create(
        code="CC",
        defaults=dict(name="Ciência da Computação", coordinator=coord, is_active=True),
    )

    # Coordenador 2 (coord2@demo.com) responsável por 1 só curso (ES)
    c_es, _ = Course.objects.update_or_create(
        code="ES",
        defaults=dict(name="Engenharia de Software", coordinator=coord2, is_active=True),
    )

    si_subjects_spec = [
        ("BD1", "Banco de Dados", 2, [0, 2]),
        ("ES1", "Engenharia de Software", 2, [1, 3]),
        ("AED", "Algoritmos e Estruturas de Dados", 2, [0, 2]),
        ("RED", "Redes de Computadores", 2, [1, 3]),
        ("SO1", "Sistemas Operacionais", 2, [2, 4]),
        ("IA1", "Inteligência Artificial", 2, [0, 4]),
        ("WEB", "Desenvolvimento Web", 2, [1, 4]),
        ("SEG", "Segurança da Informação", 2, [2, 3]),
        ("ARQ", "Arquitetura de Computadores", 2, [0, 1]),
        ("MAT", "Matemática Discreta", 2, [3, 4]),
        ("TCC", "Trabalho de Conclusão de Curso", 2, [5]),
        ("EMP", "Empreendedorismo e Inovação", 2, [5]),
    ]

    cc_subjects_spec = [
        ("CC-BDA", "Banco de Dados Avançado", 2, [1, 2, 3]),
        ("CC-RAV", "Redes de Alta Velocidade", 2, [2, 3, 4, 5]),
        ("CC-TC", "Teoria da Computação", 2, [1, 3]),
        ("CC-LOG", "Lógica para Computação", 2, [3, 4, 5]),
        ("CC-GPS", "Gestão de Projetos de Software", 2, [4, 5]),
        ("CC-CMP", "Compiladores", 2, [0]),
        ("CC-CAL", "Cálculo Numérico", 2, [0]),
        ("CC-CG", "Computação Gráfica", 2, [2, 3]),
        ("CC-PIM", "Processamento de Imagens", 2, [2, 3]),
    ]

    es_subjects_spec = [
        ("ES-REQ", "Engenharia de Requisitos", 2, [0, 2]),
        ("ES-ARQ", "Arquitetura de Software", 2, [1, 3]),
        ("ES-PAD", "Padrões de Projeto", 2, [0, 3]),
        ("ES-TST", "Testes e Qualidade de Software", 2, [1, 4]),
        ("ES-DEV", "DevOps e Integração Contínua", 2, [2, 4]),
        ("ES-AGE", "Metodologias Ágeis", 2, [0, 4]),
        ("ES-MIC", "Microsserviços e Sistemas Distribuídos", 2, [1, 2]),
        ("ES-MOB", "Desenvolvimento Mobile", 2, [2, 3]),
        ("ES-CLD", "Computação em Nuvem", 2, [3, 4]),
        ("ES-IHC", "Interação Humano-Computador", 2, [4, 5]),
    ]

    subj_map = {}
    for course_obj, spec_list, std_cnt in (
        (c_si, si_subjects_spec, 35),
        (c_cc, cc_subjects_spec, 30),
        (c_es, es_subjects_spec, 35),
    ):
        for code, name, lessons, pref_days in spec_list:
            s, _ = Subject.objects.update_or_create(
                code=code,
                defaults=dict(
                    name=name,
                    course=course_obj,
                    weekly_lessons=lessons,
                    lesson_minutes=60,
                    student_count=std_cnt,
                    preferred_days=pref_days,
                    is_active=True,
                ),
            )
            subj_map[code] = s

    # Coordenadora 1 leciona CC-GPS (Gestão de Projetos de Software)
    coord_prof.subjects.set([subj_map["CC-GPS"]])

    prof_subjects = [
        ["BD1", "TCC", "CC-BDA"],          # Prof 1 (Carlos Silva - SI e CC)
        ["ES1", "WEB", "BD1"],             # Prof 2 (Ana Lima - SI)
        ["RED", "SO1", "ARQ", "CC-RAV"],   # Prof 3 (Bruno Costa - SI e CC)
        ["IA1", "SEG", "AED"],             # Prof 4 (Carla Souza - SI)
        ["ARQ", "MAT", "EMP"],             # Prof 5 (Diego Martins - SI)
        ["CC-CMP", "CC-CAL"],              # Prof 6 (Eduardo Rocha - CC: gargalo de horário único)
        ["CC-CG", "CC-PIM"],               # Prof 7 (Fernanda Alves - CC: gargalo de carga máxima 2h)
        ["CC-TC", "CC-LOG"],               # Prof 8 (Gabriel Mendes - CC)
        ["ES-REQ", "ES-IHC"],              # Prof 9 (Helena Castro - ES)
        ["ES-ARQ", "ES-PAD"],              # Prof 10 (Igor Ribeiro - ES)
        ["ES-TST"],                        # Prof 11 (Juliana Freitas - ES)
        ["ES-DEV"],                        # Prof 12 (Lucas Barbosa - ES)
        ["ES-AGE"],                        # Prof 13 (Mariana Teixeira - ES)
        ["ES-MIC"],                        # Prof 14 (Nicolas Cardoso - ES)
        ["ES-MOB"],                        # Prof 15 (Olivia Nascimento - ES)
        ["ES-CLD"],                        # Prof 16 (Paulo Henrique - ES)
        ["ES-TST", "ES-AGE"],              # Prof 17 (Renata Gomes - ES)
        ["ES-DEV", "ES-CLD"],              # Prof 18 (Thiago Moreira - ES)
    ]
    for prof, codes in zip(profs, prof_subjects):
        prof.subjects.set([subj_map[c_code] for c_code in codes])

    # 60 min (1 hora exata por aula): 08:00–09:00, 09:00–10:00, 10:00–11:00, 11:00–12:00
    if not preserve_schedules:
        Slot.objects.all().delete()
    times = (
        (time(8, 0), time(9, 0)),
        (time(9, 0), time(10, 0)),
        (time(10, 0), time(11, 0)),
        (time(11, 0), time(12, 0)),
    )
    days = [
        [Slot.objects.update_or_create(weekday=d, start=a, end=b, defaults=dict(is_active=True))[0] for a, b in times]
        for d in range(6)
    ]

    all_profs = profs + [coord_prof]
    Availability.objects.filter(professor__in=all_profs).delete()

    common_base = {(d, t) for d in range(4) for t in (0, 1, 2)}
    prof_patterns = [
        common_base | {(0, 3), (2, 3), (4, 0), (4, 1), (5, 0), (5, 1)},  # Prof 1
        common_base | {(1, 3), (3, 3), (4, 0), (4, 2), (5, 0), (5, 1)},  # Prof 2
        common_base | {(0, 3), (1, 3), (4, 1), (4, 2), (4, 3), (5, 2), (5, 3)},  # Prof 3
        common_base | {(2, 3), (3, 3), (4, 0), (4, 1), (4, 3), (5, 0), (5, 1)},  # Prof 4
        common_base | {(0, 3), (3, 3), (4, 1), (4, 2), (4, 3), (5, 2), (5, 3)},  # Prof 5
        {(0, 0), (0, 1), (5, 0), (5, 1)},                                          # Prof 6 (Eduardo)
        {(2, 0), (2, 1), (2, 2), (3, 0), (3, 1), (3, 2)},                          # Prof 7 (Fernanda)
        {(0, 0), (0, 1), (1, 0), (1, 1), (1, 2), (1, 3), (2, 0), (2, 1), (3, 2), (3, 3), (4, 0), (4, 1), (4, 2), (4, 3), (5, 0), (5, 1)},  # Prof 8 (Gabriel)
        common_base | {(0, 3), (2, 3), (4, 0), (4, 1), (5, 0), (5, 1)},            # Prof 9 (Helena)
        common_base | {(1, 3), (3, 3), (4, 2), (4, 3)},                            # Prof 10 (Igor)
        common_base | {(1, 3), (4, 0), (4, 1), (4, 2)},                            # Prof 11 (Juliana)
        common_base | {(2, 3), (4, 1), (4, 2), (4, 3)},                            # Prof 12 (Lucas)
        common_base | {(0, 3), (4, 0), (4, 1), (4, 2)},                            # Prof 13 (Mariana)
        common_base | {(1, 3), (2, 3), (3, 3)},                                    # Prof 14 (Nicolas)
        common_base | {(2, 3), (3, 3), (4, 0), (4, 1)},                            # Prof 15 (Olivia)
        common_base | {(3, 3), (4, 0), (4, 1), (4, 2), (4, 3)},                    # Prof 16 (Paulo)
        common_base | {(1, 3), (4, 0), (4, 1), (5, 0), (5, 1)},                    # Prof 17 (Renata)
        common_base | {(2, 3), (3, 3), (4, 2), (4, 3), (5, 2), (5, 3)},            # Prof 18 (Thiago)
        {(5, 0), (5, 1)},                                                          # Coordenadora 1
    ]

    avail_objs = []
    for prof, coords in zip(all_profs, prof_patterns):
        for d, t in sorted(coords):
            avail_objs.append(Availability(professor=prof, slot=days[d][t]))

    Availability.objects.bulk_create(avail_objs)
    if not preserve_schedules:
        ScheduleProposal.objects.all().delete()


class Command(BaseCommand):
    help = (
        "Garante os dados nativos do sistema: 1 gestor, 2 coordenadores (1 com 2 cursos: SI e CC; "
        "1 com 1 curso: ES) e 18 professores com horários e disponibilidades."
    )

    def add_arguments(self, p):
        p.add_argument("--force", action="store_true")
        p.add_argument("--preserve-schedules", action="store_true")

    def handle(self, *a, **o):
        if not settings.DEBUG and not o["force"]:
            raise CommandError("Recusado fora de desenvolvimento.")

        seed_native_data(preserve_schedules=bool(o.get("preserve_schedules")))

        self.stdout.write(
            f"OK. Contas nativas prontas: 1 gestor, 2 coordenadores (SI+CC e ES) e 18 professores.\n"
            f"Logins: gestor@demo.com / coord@demo.com / coord2@demo.com / prof1@demo.com .. prof18@demo.com — senha {DEMO_PASSWORD}"
        )
