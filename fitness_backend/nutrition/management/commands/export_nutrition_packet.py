"""
Writes the review packet for dietitian validation of the calorie and macro goal calculator,
the food database and the coach's rules.

    python manage.py export_nutrition_packet
    python manage.py export_nutrition_packet --out nutrition_packet

Produces rules.md, sample_goals.csv, foods_to_check.csv, coach_rules.md, review_form.md and summary.md
(see nutrition/services/goals_packet.py). Read-only.
"""

from pathlib import Path

from django.core.management.base import BaseCommand

from nutrition.services.goals_packet import build_packet, write_packet


class Command(BaseCommand):
    help = "Write the nutrition validation packet (goal calculator rules, sample goals, foods to check, review form)."

    def add_arguments(self, parser):
        parser.add_argument("--out", default="nutrition_packet", help="Output folder (default: nutrition_packet)")

    def handle(self, *args, **options):
        packet = build_packet()
        out = write_packet(packet, Path(options["out"]))
        self.stdout.write(self.style.SUCCESS(f"Wrote the packet to {out.resolve()}"))
        self.stdout.write(f"  rules fingerprint: {packet.fingerprint}")
        self.stdout.write(f"  sample goals: {packet.stats['scenarios']} (flagged: {packet.stats['flagged']})")
        self.stdout.write(f"  foods to check: {packet.stats['foods_to_check']}")
