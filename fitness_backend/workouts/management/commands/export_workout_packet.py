"""
Writes the review packet for trainer validation of the workout generator.

    python manage.py export_workout_packet
    python manage.py export_workout_packet --out workout_packet

Produces rules.md, exercise_pool.csv, sample_routines.csv, coach_rules.md, review_form.md and
summary.md (see workouts/services/validation_packet.py). Read-only: sample routines are built
for throwaway users inside transactions that are rolled back.
"""

from pathlib import Path

from django.core.management.base import BaseCommand

from workouts.models import WgerExercise
from workouts.services.validation_packet import build_packet, write_packet


class Command(BaseCommand):
    help = "Write the workout validation packet (rules, exercise pool, sample routines, review form) for trainer review."

    def add_arguments(self, parser):
        parser.add_argument("--out", default="workout_packet", help="Output folder (default: workout_packet)")

    def handle(self, *args, **options):
        if not WgerExercise.objects.exists():
            self.stderr.write("The exercise database is empty. Run 'python manage.py sync_wger_exercises' first.")
            return
        packet = build_packet()
        out = write_packet(packet, Path(options["out"]))
        self.stdout.write(self.style.SUCCESS(f"Wrote the packet to {out.resolve()}"))
        self.stdout.write(f"  rules fingerprint: {packet.fingerprint}")
        for key, value in packet.stats.items():
            self.stdout.write(f"  {key}: {value}")
