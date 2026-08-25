"""
Bulk-imports real PhilFCT (Philippine Food Composition Table) proximate
data into the local FoodItem table.

Source file: nutrition/data/philfct_proximates_enriched.csv
This file is NOT committed to the repo (it's covered by the existing
`*.csv` rule in .gitignore) -- keep your own local copy in
nutrition/data/ and re-run this command after a fresh clone or when the
data folder is missing. Each teammate/environment needs to place the
CSV there themselves.

Expected columns (from PhilFCT's "Proximates - Amount per 100 g E.P."
table, with a few derived columns already added):
    Food_ID, Food Name, Scientific Name, Alternate Name, Edible Portion,
    Water (g), Energy (kcal), Protein (g), Total Fat (g),
    Carbohydrate, total (g), Ash, total (g), Edible_Portion_Pct,
    Category_Code, Search_Text, Protein_kcal, Carb_kcal, Fat_kcal

All values are per 100 g edible portion, so every imported FoodItem is
seeded with serving_description="100g" and serving_size_g=100 -- values
map across 1:1 with no scaling needed at import time.

Category_Code -> FoodCategory mapping was derived empirically (by
sampling food names per code, since PhilFCT documentation on the code
letters is inconsistent across sources) and reflects the classic
17-group PhilFCT taxonomy (letters I, O, L skipped to avoid confusion
with 0/1). Group "S" (infant/strained foods) is intentionally skipped --
not relevant to a gym-goer's food log.

PhilFCT's proximates table does not include fiber or sodium, so those
fields are left null, same as for any other estimated entry.

Re-running this command is safe: rows are matched and updated by their
PhilFCT Food_ID (stored in `external_id`), so it will not create
duplicates.

Run with: python manage.py import_philfct
"""

import csv
from pathlib import Path

from django.core.management.base import BaseCommand

from nutrition.models import FoodCategory, FoodItem

CSV_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "philfct_proximates_enriched.csv"

CATEGORY_MAP = {
    "A": FoodCategory.RICE_GRAINS,    # Cereals & Products
    "B": FoodCategory.ROOTS_TUBERS,   # Starchy Roots & Tubers
    "C": FoodCategory.NUTS_LEGUMES,   # Nuts, Legumes & Seeds
    "D": FoodCategory.VEGETABLES,
    "E": FoodCategory.FRUITS,
    "F": FoodCategory.VIANDS_MEAT,    # Meat & Meat Products
    "G": FoodCategory.VIANDS_FISH,    # Fish & Aquatic Products
    "H": FoodCategory.EGGS,
    "J": FoodCategory.DAIRY,          # Milk & Milk Products
    "K": FoodCategory.FATS_OILS,
    "M": FoodCategory.DESSERTS,       # Sugars / Candies / Confectionery
    "N": FoodCategory.CONDIMENTS,     # Misc. condiments & sauces
    "P": FoodCategory.BEVERAGES,      # Alcoholic beverages
    "Q": FoodCategory.BEVERAGES,      # Non-alcoholic beverages
    "R": FoodCategory.SNACKS,         # Mixed / composite dishes
    # "S": Infant/strained foods -- intentionally skipped
    "T": FoodCategory.OTHER,          # Miscellaneous (baking powder, gelatin, etc.)
}

SKIPPED_CODES = {"S"}


def _to_float(value, default=0.0):
    value = (value or "").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


class Command(BaseCommand):
    help = "Bulk-import PhilFCT proximate data (nutrition/data/philfct_proximates_enriched.csv) into FoodItem"

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            dest="csv_path",
            default=str(CSV_PATH),
            help="Path to the PhilFCT CSV file (defaults to nutrition/data/philfct_proximates_enriched.csv)",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"])
        if not csv_path.exists():
            self.stderr.write(
                self.style.ERROR(
                    f"CSV not found at {csv_path}\n"
                    "This file isn't committed to the repo -- place your own copy of "
                    "philfct_proximates_enriched.csv in nutrition/data/, or pass --csv <path>."
                )
            )
            return

        created_count = 0
        updated_count = 0
        skipped_count = 0
        unmapped_codes = set()

        with csv_path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = (row.get("Category_Code") or "").strip()

                if code in SKIPPED_CODES:
                    skipped_count += 1
                    continue

                category = CATEGORY_MAP.get(code)
                if category is None:
                    unmapped_codes.add(code)
                    category = FoodCategory.OTHER

                food_id = (row.get("Food_ID") or "").strip()
                name = (row.get("Food Name") or "").strip()
                if not name:
                    skipped_count += 1
                    continue

                local_name = (row.get("Alternate Name") or "").strip()
                ep_pct = (row.get("Edible_Portion_Pct") or "").strip()

                defaults = {
                    "name": name,
                    "local_name": local_name,
                    "category": category,
                    "serving_description": "100g",
                    "serving_size_g": 100,
                    "calories": _to_float(row.get("Energy (kcal)")),
                    "protein_g": _to_float(row.get("Protein (g)")),
                    "carbs_g": _to_float(row.get("Carbohydrate, total (g)")),
                    "fat_g": _to_float(row.get("Total Fat (g)")),
                    "source": (
                        f"PhilFCT, item {food_id}"
                        + (f" (EP {ep_pct}%)" if ep_pct else "")
                    ),
                }

                obj, created = FoodItem.objects.update_or_create(
                    external_id=food_id,
                    defaults=defaults,
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported PhilFCT data: {created_count} created, {updated_count} updated, "
                f"{skipped_count} skipped (infant foods / blank rows)."
            )
        )
        if unmapped_codes:
            self.stdout.write(
                self.style.WARNING(
                    f"Unmapped category codes fell back to OTHER: {sorted(unmapped_codes)}"
                )
            )
