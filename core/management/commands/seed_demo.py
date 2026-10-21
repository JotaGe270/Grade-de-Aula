import random
from datetime import time
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from core.models import *

DEMO_PASSWORD = "Demo@12345"  # somente demonstração


class Command(BaseCommand):
    help = "Cria dados de demonstração (bloqueado com DEBUG=0 sem --force)."
    def add_arguments(self, p): p.add_argument("--force", action="store_true")
    def handle(self, *a, **o):
        if not settings.DEBUG and not o["force"]: raise CommandError("Recusado fora de desenvolvimento.")
        mk = lambda email, name, role: User.objects.get_or_create(email=email, defaults=dict(
            username=email, first_name=name, role=role))[0]
        for u in (mk("gestor@demo.com", "Gestor Demo", "manager"), mk("coord@demo.com", "Coordenadora Demo", "coordinator"),
                  mk("prof1@demo.com", "Professor Demo", "professor"), mk("prof2@demo.com", "Ana Lima", "professor"),
                  mk("prof3@demo.com", "Bruno Costa", "professor"), mk("prof4@demo.com", "Carla Souza", "professor")):
            u.set_password(DEMO_PASSWORD); u.save()
        c, _ = Course.objects.get_or_create(code="SI", defaults=dict(name="Sistemas de Informação", coordinator=User.objects.get(email="coord@demo.com")))
        s1, _ = Subject.objects.get_or_create(code="BD1", defaults=dict(name="Banco de Dados", course=c, weekly_lessons=2))
        Subject.objects.get_or_create(code="ES1", defaults=dict(name="Engenharia de Software", course=c, weekly_lessons=2))
        emails = ("prof1@demo.com", "prof2@demo.com", "prof3@demo.com", "prof4@demo.com")
        profs = [Professor.objects.get_or_create(user=User.objects.get(email=e), defaults=dict(max_weekly_hours=16))[0] for e in emails]
        profs[0].subjects.add(s1)
        # 50 min, uma começa quando a outra acaba; primeira 8:10, última termina 11:30 (teto 11:50)
        times = ((time(8, 10), time(9)), (time(9), time(9, 50)), (time(9, 50), time(10, 40)), (time(10, 40), time(11, 30)))
        days = [[Slot.objects.get_or_create(weekday=d, start=a, end=b)[0] for a, b in times] for d in range(5)]
        # mínimo 2 por dia, em geral mais; o mesmo slot pode ter vários; nenhum slot fica vazio
        rng = random.Random(1)
        Availability.objects.filter(professor__in=profs).delete()
        chosen = {}
        for prof in profs:
            for day in days:
                for slot in rng.sample(day, rng.choice((3, 3, 4, 2))):
                    chosen.setdefault(slot.id, []).append(prof)
        for slot in (s for day in days for s in day):
            chosen.setdefault(slot.id, [rng.choice(profs)])
        Availability.objects.bulk_create(
            Availability(professor=p, slot_id=sid) for sid, ps in chosen.items() for p in ps)
        self.stdout.write(f"OK. Logins: gestor@demo.com / coord@demo.com / prof1@demo.com / prof2@demo.com / prof3@demo.com / prof4@demo.com — senha {DEMO_PASSWORD}")
