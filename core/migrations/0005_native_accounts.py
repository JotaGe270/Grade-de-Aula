import sys
from django.db import migrations


def apply_native_accounts(apps, schema_editor):
    if "test" in sys.argv:
        return
    from core.management.commands.seed_demo import seed_native_data
    seed_native_data(preserve_schedules=True)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_scheduleproposal_course"),
        ("authtoken", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(apply_native_accounts, migrations.RunPython.noop),
    ]
