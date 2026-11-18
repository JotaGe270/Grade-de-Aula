from datetime import time
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from core.models import *

DEMO_PASSWORD = "Demo@12345"  # somente demonstração


class Command(BaseCommand):
    help = (
        "Cria dados de demonstração com 2 cursos (SI e CC) sob a mesma Coordenadora (que também leciona), "
        "professores com horários sobrepostos e casos de conflito/gargalo intencionais."
    )

    def add_arguments(self, p):
        p.add_argument("--force", action="store_true")

    def handle(self, *a, **o):
        if not settings.DEBUG and not o["force"]:
            raise CommandError("Recusado fora de desenvolvimento.")

        def mk(email, name, role):
            u, _ = User.objects.update_or_create(
                email=email,
                defaults=dict(username=email, first_name=name, role=role, is_active=True),
            )
            u.set_password(DEMO_PASSWORD)
            u.save()
            return u

        mk("gestor@demo.com", "Gestor Demo", "manager")
        coord = mk("coord@demo.com", "Coordenadora Demo", "coordinator")

        # Coordenadora também pode dar aulas (possui perfil Professor)
        coord_prof, _ = Professor.objects.update_or_create(
            user=coord,
            defaults=dict(institutional_id="COORD-001", max_weekly_hours=10, is_active=True),
        )

        prof_specs = [
            ("prof1@demo.com", "Carlos Silva", 12),
            ("prof2@demo.com", "Ana Lima", 12),
            ("prof3@demo.com", "Bruno Costa", 12),
            ("prof4@demo.com", "Carla Souza", 12),
            ("prof5@demo.com", "Diego Martins", 12),
            ("prof6@demo.com", "Eduardo Rocha", 10),
            ("prof7@demo.com", "Fernanda Alves", 2),
            ("prof8@demo.com", "Gabriel Mendes", 12),
        ]
        profs = []
        for idx, (email, name, max_h) in enumerate(prof_specs, start=1):
            u = mk(email, name, "professor")
            p, _ = Professor.objects.update_or_create(
                user=u,
                defaults=dict(institutional_id=f"DOC-00{idx}", max_weekly_hours=max_h, is_active=True),
            )
            profs.append(p)

        # 1 Coordenadora responsável por 2 cursos (SI e CC)
        c_si, _ = Course.objects.update_or_create(
            code="SI",
            defaults=dict(name="Sistemas de Informação", coordinator=coord, is_active=True),
        )
        c_cc, _ = Course.objects.update_or_create(
            code="CC",
            defaults=dict(name="Ciência da Computação", coordinator=coord, is_active=True),
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

        subj_map = {}
        for code, name, lessons, pref_days in si_subjects_spec:
            s, _ = Subject.objects.update_or_create(
                code=code,
                defaults=dict(
                    name=name,
                    course=c_si,
                    weekly_lessons=lessons,
                    lesson_minutes=60,
                    student_count=35,
                    preferred_days=pref_days,
                    is_active=True,
                ),
            )
            subj_map[code] = s

        for code, name, lessons, pref_days in cc_subjects_spec:
            s, _ = Subject.objects.update_or_create(
                code=code,
                defaults=dict(
                    name=name,
                    course=c_cc,
                    weekly_lessons=lessons,
                    lesson_minutes=60,
                    student_count=30,
                    preferred_days=pref_days,
                    is_active=True,
                ),
            )
            subj_map[code] = s

        # Coordenadora leciona CC-GPS (Gestão de Projetos de Software)
        coord_prof.subjects.set([subj_map["CC-GPS"]])

        prof_subjects = [
            ["BD1", "TCC", "CC-BDA"],          # Prof 1 (Carlos Silva - atua em SI incluindo Sábado e CC)
            ["ES1", "WEB", "BD1"],             # Prof 2 (Ana Lima - SI)
            ["RED", "SO1", "ARQ", "CC-RAV"],   # Prof 3 (Bruno Costa - atua em SI e CC)
            ["IA1", "SEG", "AED"],             # Prof 4 (Carla Souza - SI)
            ["ARQ", "MAT", "EMP"],             # Prof 5 (Diego Martins - SI incluindo Sábado)
            ["CC-CMP", "CC-CAL"],              # Prof 6 (Eduardo Rocha - CC: gargalo de horário único!)
            ["CC-CG", "CC-PIM"],               # Prof 7 (Fernanda Alves - CC: gargalo de carga máxima 2h!)
            ["CC-TC", "CC-LOG"],               # Prof 8 (Gabriel Mendes - CC: disputa horários mas tem saída!)
        ]
        for prof, codes in zip(profs, prof_subjects):
            prof.subjects.set([subj_map[c_code] for c_code in codes])

        # 60 min (1 hora exata por aula): 08:00–09:00, 09:00–10:00, 10:00–11:00, 11:00–12:00
        Slot.objects.all().delete()
        times = (
            (time(8, 0), time(9, 0)),
            (time(9, 0), time(10, 0)),
            (time(10, 0), time(11, 0)),
            (time(11, 0), time(12, 0)),
        )
        days = [
            [Slot.objects.get_or_create(weekday=d, start=a, end=b, defaults=dict(is_active=True))[0] for a, b in times]
            for d in range(6)
        ]

        all_profs = profs + [coord_prof]
        Availability.objects.filter(professor__in=all_profs).delete()

        common_base = {(d, t) for d in range(4) for t in (0, 1, 2)}
        prof_patterns = [
            common_base | {(0, 3), (2, 3), (4, 0), (4, 1), (5, 0), (5, 1)},
            common_base | {(1, 3), (3, 3), (4, 0), (4, 2), (5, 0), (5, 1)},
            common_base | {(0, 3), (1, 3), (4, 1), (4, 2), (4, 3), (5, 2), (5, 3)},
            common_base | {(2, 3), (3, 3), (4, 0), (4, 1), (4, 3), (5, 0), (5, 1)},
            common_base | {(0, 3), (3, 3), (4, 1), (4, 2), (4, 3), (5, 2), (5, 3)},
            {(0, 0), (0, 1), (5, 0), (5, 1)},                                          # Prof 6 (Eduardo): disputa Sábado 08:10 com a Coordenadora!
            {(2, 0), (2, 1), (2, 2), (3, 0), (3, 1), (3, 2)},                          # Prof 7 (Fernanda): carga máx 2h!
            {(0, 0), (0, 1), (1, 0), (1, 1), (1, 2), (1, 3), (2, 0), (2, 1), (3, 2), (3, 3), (4, 0), (4, 1), (4, 2), (4, 3), (5, 0), (5, 1)},  # Prof 8 (Gabriel)
            {(5, 0), (5, 1)},                                                          # Coordenadora: disponível no Sábado 08:10 e 09:00!
        ]

        avail_objs = []
        for prof, coords in zip(all_profs, prof_patterns):
            for d, t in sorted(coords):
                avail_objs.append(Availability(professor=prof, slot=days[d][t]))

        Availability.objects.bulk_create(avail_objs)
        ScheduleProposal.objects.all().delete()

        self.stdout.write(
            f"OK. 2 cursos (SI e CC), Coordenadora docente + 8 professores criados.\n"
            f"Logins: gestor@demo.com / coord@demo.com / prof1@demo.com .. prof8@demo.com — senha {DEMO_PASSWORD}"
        )
