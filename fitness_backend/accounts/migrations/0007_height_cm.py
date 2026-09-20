import django.core.validators
from django.db import migrations, models


def backfill_height_cm(apps, schema_editor):
    """
    Convert every existing height_ft/height_in pair to height_cm before
    those columns are dropped, so no one's saved height silently
    disappears. Mirrors the ftInToCm conversion on the frontend
    (lib/profile.js) -- same formula, just run once here instead of at
    display time.
    """
    Profile = apps.get_model("accounts", "Profile")
    for profile in Profile.objects.exclude(height_ft__isnull=True):
        total_inches = (profile.height_ft * 12) + (profile.height_in or 0)
        profile.height_cm = round(total_inches * 2.54, 1)
        profile.save(update_fields=["height_cm"])


def backfill_height_ft_in(apps, schema_editor):
    """Reverse: convert height_cm back to height_ft/height_in, for `migrate` rollback."""
    Profile = apps.get_model("accounts", "Profile")
    for profile in Profile.objects.exclude(height_cm__isnull=True):
        total_inches = profile.height_cm / 2.54
        profile.height_ft = int(total_inches // 12)
        profile.height_in = round(total_inches - profile.height_ft * 12)
        if profile.height_in == 12:
            profile.height_ft += 1
            profile.height_in = 0
        profile.save(update_fields=["height_ft", "height_in"])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_profile_unit_system'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='height_cm',
            field=models.FloatField(
                blank=True, null=True,
                validators=[django.core.validators.MinValueValidator(50), django.core.validators.MaxValueValidator(250)],
            ),
        ),
        migrations.RunPython(backfill_height_cm, backfill_height_ft_in),
        migrations.RemoveField(
            model_name='profile',
            name='height_ft',
        ),
        migrations.RemoveField(
            model_name='profile',
            name='height_in',
        ),
    ]
