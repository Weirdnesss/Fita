"""
Bulk-imports USDA FoodData Central (FDC) basic foods into FoodItem, to fill
the gaps PhilFCT doesn't cover (common raw/cooked basics like chicken breast,
oats, broccoli, Greek yogurt).

Data: public domain (CC0), free, no API key needed for the CSV downloads.
Download from https://fdc.nal.usda.gov/download-datasets :
  - "Foundation Foods" CSV  (modern, lab-analysed, ~few hundred foods)
  - "SR Legacy" CSV         (~7,800 everyday foods; the best coverage)
Unzip each into its own folder and pass them with --dir (repeatable):

    python manage.py import_usda --dir ~/data/FoodData_Central_sr_legacy_food_csv_2018-04 \\
                                 --dir ~/data/FoodData_Central_foundation_food_csv_<date>

Folders must contain food.csv and food_nutrient.csv (food_category.csv is used
when present). Like the PhilFCT import, the CSVs are NOT committed to the repo.

All values are per 100 g, so rows are stored as serving_description="100g",
serving_size_g=100, same as PhilFCT. Rows get source="USDA FoodData Central
(<dataset>), FDC <id>" and external_id="usda:<fdc_id>", so re-running updates
in place instead of duplicating. PhilFCT rows are never touched.

Nutrient ids (FDC): energy 1008 kcal (Foundation Foods often only has the
Atwater values 2047/2048 instead), protein 1003, fat 1004, carbohydrate by
difference 1005, fiber 1079, sodium 1093 (mg).

Cite in the thesis: U.S. Department of Agriculture, Agricultural Research
Service. FoodData Central. https://fdc.nal.usda.gov
"""

import csv
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from nutrition.models import FoodCategory, FoodItem

DATA_TYPES = {
    "sr_legacy_food": "SR Legacy",
    "foundation_food": "Foundation",
}

ENERGY_IDS = ["1008", "2047", "2048"]  # in order of preference
NUTRIENT_FIELDS = {
    "protein_g": ["1003"],
    "fat_g": ["1004"],
    "carbs_g": ["1005"],
    "fiber_g": ["1079"],
    "sodium_mg": ["1093"],
}
WANTED_NUTRIENT_IDS = set(ENERGY_IDS) | {i for ids in NUTRIENT_FIELDS.values() for i in ids}

# USDA food-group descriptions that aren't useful for a gym-goer's log.
EXCLUDED_GROUPS = (
    "baby foods",
    "fast foods",
    "restaurant foods",
    "american indian",
)

# "(Includes foods for USDA's Food Distribution Program)" is a database note, not part of the food's name.
_PROGRAM_NOTE = re.compile(r"\s*\(Includes foods for USDA'?s? [^)]*\)", re.I)

_ROOTS = re.compile(r"\b(potato|potatoes|sweet potato|cassava|yam|taro|tapioca|jicama)\b", re.I)


def map_category(group_description, name):
    """USDA food-group description (+ food name) -> FoodCategory."""
    group = (group_description or "").lower()
    lower_name = name.lower()

    if group.startswith("dairy and egg"):
        return FoodCategory.EGGS if lower_name.startswith("egg") else FoodCategory.DAIRY
    if group.startswith("vegetables"):
        return FoodCategory.ROOTS_TUBERS if _ROOTS.search(lower_name) else FoodCategory.VEGETABLES
    if group.startswith("soups, sauces"):
        return FoodCategory.SOUPS if lower_name.startswith("soup") else FoodCategory.CONDIMENTS

    simple = [
        (("poultry", "beef", "pork", "lamb", "sausages and luncheon"), FoodCategory.VIANDS_MEAT),
        (("finfish", "shellfish"), FoodCategory.VIANDS_FISH),
        (("fruits",), FoodCategory.FRUITS),
        (("cereal grains", "breakfast cereals"), FoodCategory.RICE_GRAINS),
        (("legumes", "nut and seed"), FoodCategory.NUTS_LEGUMES),
        (("fats and oils",), FoodCategory.FATS_OILS),
        (("beverages",), FoodCategory.BEVERAGES),
        (("sweets",), FoodCategory.DESSERTS),
        (("snacks", "baked products"), FoodCategory.SNACKS),
        (("spices and herbs",), FoodCategory.CONDIMENTS),
    ]
    for prefixes, category in simple:
        if group.startswith(prefixes):
            return category
    return FoodCategory.OTHER


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _non_negative(value):
    """Carbohydrate \"by difference\" can come out slightly below zero in lab data (ahi tuna -0.10); a food cannot hold less than none."""
    return max(value or 0, 0)


class Command(BaseCommand):
    help = "Bulk-import USDA FoodData Central (SR Legacy / Foundation Foods CSV) into FoodItem"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dir",
            dest="dirs",
            action="append",
            required=True,
            help="Folder with an unzipped FDC CSV download (food.csv, food_nutrient.csv). Repeatable.",
        )
        parser.add_argument(
            "--skip-existing-names",
            action="store_true",
            help="Skip USDA foods whose name exactly matches a food already in the database "
            "(e.g. a PhilFCT item), instead of adding a second entry.",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Parse and report counts without writing to the database."
        )

    def handle(self, *args, **options):
        existing_names = set()
        if options["skip_existing_names"]:
            existing_names = {n.lower() for n in FoodItem.objects.values_list("name", flat=True)}

        totals = {"created": 0, "updated": 0, "skipped": 0}
        for folder in options["dirs"]:
            self._import_folder(Path(folder), existing_names, options["dry_run"], totals)

        verb = "Would import" if options["dry_run"] else "Imported"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} USDA data: {totals['created']} created, {totals['updated']} updated, "
                f"{totals['skipped']} skipped."
            )
        )

    def _import_folder(self, folder, existing_names, dry_run, totals):
        food_csv = folder / "food.csv"
        nutrient_csv = folder / "food_nutrient.csv"
        for required in (food_csv, nutrient_csv):
            if not required.exists():
                raise CommandError(f"{required} not found. Pass the unzipped FDC folder with --dir.")

        groups = {}
        category_csv = folder / "food_category.csv"
        if category_csv.exists():
            with category_csv.open(encoding="utf-8-sig", newline="") as f:
                groups = {row["id"]: row.get("description", "") for row in csv.DictReader(f)}

        # 1) Which foods to import, with their name/group/dataset.
        foods = {}
        with food_csv.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                data_type = row.get("data_type", "")
                if data_type not in DATA_TYPES:
                    continue  # branded/survey/sub-sample rows etc.
                group = groups.get(row.get("food_category_id", ""), "")
                name = _PROGRAM_NOTE.sub("", row.get("description") or "").strip()
                if not name or any(group.lower().startswith(g) for g in EXCLUDED_GROUPS):
                    totals["skipped"] += 1
                    continue
                foods[row["fdc_id"]] = {"name": name[:200], "group": group, "dataset": DATA_TYPES[data_type]}

        # 2) Stream the (large) nutrient file once, keeping only what we need.
        nutrients = {}
        with nutrient_csv.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                fdc_id = row["fdc_id"]
                nutrient_id = row["nutrient_id"]
                if fdc_id in foods and nutrient_id in WANTED_NUTRIENT_IDS:
                    amount = _num(row.get("amount"))
                    if amount is not None:
                        nutrients.setdefault(fdc_id, {})[nutrient_id] = amount

        # 3) Build rows.
        existing_ids = dict(
            FoodItem.objects.filter(external_id__startswith="usda:").values_list("external_id", "pk")
        )
        to_create, to_update = [], []
        for fdc_id, info in foods.items():
            values = nutrients.get(fdc_id, {})
            calories = next((values[i] for i in ENERGY_IDS if i in values), None)
            macros = {
                field: next((values[i] for i in ids if i in values), None)
                for field, ids in NUTRIENT_FIELDS.items()
            }
            macro_values = [macros["protein_g"], macros["fat_g"], macros["carbs_g"]]
            if calories is None or all(v is None for v in macro_values):
                totals["skipped"] += 1
                continue
            if info["name"].lower() in existing_names:
                totals["skipped"] += 1
                continue

            external_id = f"usda:{fdc_id}"
            fields = {
                "name": info["name"],
                "category": map_category(info["group"], info["name"]),
                "serving_description": "100g",
                "serving_size_g": 100,
                "calories": calories,
                "protein_g": _non_negative(macros["protein_g"]),
                "carbs_g": _non_negative(macros["carbs_g"]),
                "fat_g": _non_negative(macros["fat_g"]),
                "fiber_g": macros["fiber_g"],
                "sodium_mg": macros["sodium_mg"],
                "source": f"USDA FoodData Central ({info['dataset']}), FDC {fdc_id}",
                "search_text": info["group"].lower(),
                "external_id": external_id,
            }
            if external_id in existing_ids:
                to_update.append(FoodItem(pk=existing_ids[external_id], **fields))
            else:
                to_create.append(FoodItem(**fields))

        totals["created"] += len(to_create)
        totals["updated"] += len(to_update)
        if dry_run:
            return

        FoodItem.objects.bulk_create(to_create, batch_size=500)
        if to_update:
            FoodItem.objects.bulk_update(
                to_update,
                [
                    "name",
                    "category",
                    "serving_description",
                    "serving_size_g",
                    "calories",
                    "protein_g",
                    "carbs_g",
                    "fat_g",
                    "fiber_g",
                    "sodium_mg",
                    "source",
                    "search_text",
                ],
                batch_size=500,
            )
