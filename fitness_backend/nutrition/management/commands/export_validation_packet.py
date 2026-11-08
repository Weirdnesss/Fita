"""
Writes the review packet for expert validation of the meal suggestions.

    python manage.py export_validation_packet
    python manage.py export_validation_packet --out validation_packet

Produces rules.md, summary.md, sample_plates.csv and estimated_foods.csv (see
nutrition/services/validation_packet.py). Read-only: sample plates are built for a
throwaway user inside a transaction that is rolled back.
"""

from pathlib import Path

from django.core.management.base import BaseCommand

from nutrition.models import FoodItem
from nutrition.services.validation_packet import build_packet, write_packet


class Command(BaseCommand):
    help = "Write the validation packet (rules, sample plates, foods to cross-check) for expert review."

    def add_arguments(self, parser):
        parser.add_argument("--out", default="validation_packet", help="Output folder (default: validation_packet)")

    def handle(self, *args, **options):
        if not FoodItem.objects.filter(created_by__isnull=True).exists():
            self.stderr.write("The food database is empty. Import foods first (import_philfct, import_usda, seed_foods).")
            return
        packet = build_packet()
        out = write_packet(packet, Path(options["out"]))
        self.stdout.write(self.style.SUCCESS(f"Wrote the packet to {out.resolve()}"))
        self.stdout.write(f"  rules fingerprint: {packet.fingerprint}")
        self.stdout.write(f"  sample plates: {packet.stats['plates']}")
        self.stdout.write(f"  estimated foods to cross-check: {packet.stats['estimated_foods']}")
        self.stdout.write(f"  foods left out as raw-looking: {packet.stats['raw_looking_foods']}")
        self.stdout.write(f"  foods left out as labelled raw (not listed): {packet.stats['labelled_raw_foods']}")
