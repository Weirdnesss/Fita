"""
One-off cleanup of food rows that were imported before the importers were fixed.

    python manage.py clean_food_data                      # report only, changes nothing
    python manage.py clean_food_data --apply              # fix negative values and USDA names
    python manage.py clean_food_data --apply --delete-bad-off
                                                          # also delete suspicious Open Food Facts rows
                                                          # (only ones nobody has logged or used)

Back up the database before using --apply.
"""

import re

from django.core.management.base import BaseCommand

from nutrition.models import FoodItem

PROGRAM_NOTE = re.compile(r"\s*\(Includes foods for USDA'?s? [^)]*\)", re.I)
ATWATER_TOLERANCE = 0.3  # same rule as import_openfoodfacts


def energy_mismatch(food):
    """True when the calories disagree with the macros (4 kcal/g protein and carbs, 9 kcal/g fat)."""
    atwater = 4 * food.protein_g + 4 * food.carbs_g + 9 * food.fat_g
    allowed = max(30 * food.serving_size_g / 100, ATWATER_TOLERANCE * atwater)
    return abs(food.calories - atwater) > allowed


def times_used(food):
    """How many rows in other tables (food log entries and so on) point at this food."""
    total = 0
    for rel in FoodItem._meta.related_objects:
        if rel.one_to_many or rel.one_to_one:
            total += rel.related_model._base_manager.filter(**{rel.field.name: food}).count()
    return total


class Command(BaseCommand):
    help = "Fix negative macros, strip the USDA program note from names, and find bad Open Food Facts rows"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Make the fixes (default: report only)")
        parser.add_argument(
            "--delete-bad-off", action="store_true", help="With --apply: delete bad Open Food Facts rows that are not in use"
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        say = self.stdout.write

        # 1) Negative macros
        for field in ("protein_g", "carbs_g", "fat_g"):
            rows = FoodItem.objects.filter(**{field + "__lt": 0})
            say(f"Negative {field}: {rows.count()}")
            for food in rows[:10]:
                say(f"    {food.name}: {getattr(food, field)}")
            if apply:
                rows.update(**{field: 0})

        # 2) USDA names
        named = [f for f in FoodItem.objects.filter(external_id__startswith="usda:", name__contains="Includes foods for USDA")]
        say(f"USDA names with the program note: {len(named)}")
        for food in named[:10]:
            say(f"    {food.name}  ->  {PROGRAM_NOTE.sub('', food.name).strip()}")
        if apply:
            for food in named:
                food.name = PROGRAM_NOTE.sub("", food.name).strip()
                food.save(update_fields=["name"])

        # 3) Open Food Facts rows whose calories do not match their macros
        bad = [f for f in FoodItem.objects.filter(external_id__startswith="off:") if energy_mismatch(f)]
        say(f"Open Food Facts rows whose calories do not match their macros: {len(bad)}")
        deleted = kept = 0
        for food in bad:
            uses = times_used(food)
            say(f"    id {food.id}: {food.name} | {food.calories:g} kcal, P {food.protein_g:g} C {food.carbs_g:g} F {food.fat_g:g} "
                f"(serving {food.serving_size_g:g} g) | used {uses}x")
            if apply and options["delete_bad_off"]:
                if uses == 0:
                    food.delete()
                    deleted += 1
                else:
                    kept += 1
        if apply and options["delete_bad_off"]:
            say(f"Deleted {deleted}; kept {kept} that are in use.")

        say(self.style.SUCCESS("Done." if apply else "Report only. Nothing was changed. Add --apply to fix."))
