import sys
from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # Garante que ao rodar `python manage.py runserver` após um git pull
        # (mesmo sem rodar migrate ou seed_demo manualmente), o banco contenha
        # exatamente as 21 contas nativas e nenhuma conta extra antiga.
        if "test" in sys.argv or "runserver" not in sys.argv:
            return
        from django.core.management import call_command
        from django.db.utils import OperationalError, ProgrammingError
        from core.models import User, Course
        from core.management.commands.seed_demo import NATIVE_EMAILS, seed_native_data

        try:
            has_exact_native = (
                User.objects.filter(email__in=NATIVE_EMAILS).count() == len(NATIVE_EMAILS)
                and not User.objects.exclude(email__in=NATIVE_EMAILS).exists()
                and Course.objects.filter(code__in=["SI", "CC", "ES"]).count() >= 3
            )
            if not has_exact_native:
                seed_native_data(preserve_schedules=True)
        except (OperationalError, ProgrammingError):
            try:
                call_command("migrate", interactive=False, verbosity=0)
                seed_native_data(preserve_schedules=True)
            except Exception:
                pass
