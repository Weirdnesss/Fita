import csv

from django.core.management.base import BaseCommand, CommandError

from workouts.models import ExerciseVideo


class Command(BaseCommand):
    help = "Load curated exercise form videos from a CSV with columns: name,url"

    def add_arguments(self, parser):
        parser.add_argument("csv_path")

    def handle(self, *args, **options):
        try:
            f = open(options["csv_path"], newline="", encoding="utf-8-sig")
        except OSError as e:
            raise CommandError(str(e))

        created = updated = skipped = 0
        with f:
            for row in csv.DictReader(f):
                name = (row.get("name") or "").strip().lower()
                url = (row.get("url") or "").strip()
                if not name or not url:
                    skipped += 1
                    continue
                _, was_created = ExerciseVideo.objects.update_or_create(
                    name=name, defaults={"url": url}
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Created {created}, updated {updated}, skipped {skipped}."
        ))