"""
Imports Philippine packaged products (instant noodles, biscuits, canned goods,
drinks...) from Open Food Facts into FoodItem. PhilFCT and USDA are weak here;
Open Food Facts is crowd-sourced from product labels, so it's the best free
source for barcoded Filipino brands.

    python manage.py import_openfoodfacts --max-pages 10

Most popular products first (sorted by scan count), 100 per page. Open Food
Facts asks API users to identify themselves and to stay under its rate limits
(search is limited to roughly 10 requests/minute), so this waits between pages
and sends a User-Agent. Set your own with --user-agent or OFF_USER_AGENT
(Open Food Facts recommends including a contact address).

Stored per serving when the product lists a serving size in grams (e.g. "1 pack
(60 g)"), otherwise per 100 g. source="Open Food Facts, barcode <code>",
external_id="off:<barcode>", so re-running updates instead of duplicating.

Data licence: Open Database License (ODbL). Keep attribution ("Open Food Facts
contributors", https://world.openfoodfacts.org) in the app/thesis; the data is
crowd-sourced, so values can contain errors -- this command filters implausible
rows but it is not a substitute for verification.
"""

import os
import re
import time

import requests
from django.core.management.base import BaseCommand, CommandError

from nutrition.models import FoodCategory, FoodItem

API_URL = "https://world.openfoodfacts.org/api/v2/search"
DEFAULT_USER_AGENT = "Fita-thesis-importer/1.0 (+https://github.com/Weirdnesss/fita)"
FIELDS = "code,product_name,brands,serving_quantity,serving_size,categories_tags,nutriments"

ATWATER_TOLERANCE = 0.3  # largest share of the macro-based energy that the label's kcal may differ by

# Temporary-failure statuses worth retrying (overloaded / rate limited).
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_BACKOFF_SECONDS = 120

# First match wins, so more specific keywords come first.
CATEGORY_KEYWORDS = [
    (("beverages", "drinks", "juices", "sodas", "waters", "coffees", "teas"), FoodCategory.BEVERAGES),
    (("instant-noodles", "noodles", "pastas", "rices", "cereals", "breads", "breakfast-cereals"), FoodCategory.RICE_GRAINS),
    (("canned-fishes", "fishes", "seafood", "tunas", "sardines"), FoodCategory.VIANDS_FISH),
    (("canned-meats", "meats", "sausages", "hams", "chicken", "pork", "beef", "corned-beef"), FoodCategory.VIANDS_MEAT),
    (("soups",), FoodCategory.SOUPS),
    (("sauces", "condiments", "vinegars", "soy-sauces", "seasonings"), FoodCategory.CONDIMENTS),
    (("dairies", "milks", "yogurts", "cheeses"), FoodCategory.DAIRY),
    (("eggs",), FoodCategory.EGGS),
    (("oils", "fats", "margarines"), FoodCategory.FATS_OILS),
    (("fruits", "fruits-and-vegetables-based-foods"), FoodCategory.FRUITS),
    (("vegetables",), FoodCategory.VEGETABLES),
    (("legumes", "nuts", "peanuts", "seeds"), FoodCategory.NUTS_LEGUMES),
    (("biscuits", "crackers", "chips", "snacks", "salty-snacks", "cookies", "wafers"), FoodCategory.SNACKS),
    (("chocolates", "candies", "confectioneries", "sweet-snacks", "desserts", "sugars"), FoodCategory.DESSERTS),
]


def map_category(categories_tags):
    """OFF categories_tags like ['en:snacks', 'en:biscuits'] -> FoodCategory."""
    words = {t.split(":", 1)[-1] for t in (categories_tags or [])}
    for keywords, category in CATEGORY_KEYWORDS:
        if words & set(keywords):
            return category
    return FoodCategory.OTHER


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_product(product):
    """
    One OFF API product -> dict of FoodItem fields, or None if the product is
    unusable (no name/energy/macros, or physically implausible values).
    """
    code = str(product.get("code") or "").strip()
    name = (product.get("product_name") or "").strip()
    nutriments = product.get("nutriments") or {}
    # external_id is "off:<code>" in a 20-char column: skip oddly long codes
    # rather than crash a Postgres import (SQLite wouldn't notice).
    if not code or not name or not code.isdigit() or len(code) > 16:
        return None

    kcal = _num(nutriments.get("energy-kcal_100g"))
    protein = _num(nutriments.get("proteins_100g"))
    carbs = _num(nutriments.get("carbohydrates_100g"))
    fat = _num(nutriments.get("fat_100g"))
    if kcal is None or protein is None or carbs is None or fat is None:
        return None

    # Per-100g sanity: fat is 9 kcal/g so nothing is above ~900 kcal, and the
    # three macros can't outweigh the 100 g they came from (small tolerance).
    if not (0 <= kcal <= 900) or min(protein, carbs, fat) < 0:
        return None
    if protein + carbs + fat > 105:
        return None
    # Calories must roughly match the macros (4 kcal per g of protein and carbs, 9 per g of fat). Contributors sometimes
    # type a per-serving or per-slice energy next to per-100 g macros (bread at 121-161 kcal instead of ~260).
    atwater = 4 * protein + 4 * carbs + 9 * fat
    if abs(kcal - atwater) > max(30, ATWATER_TOLERANCE * atwater):
        return None

    fiber = _num(nutriments.get("fiber_100g"))
    sodium_g = _num(nutriments.get("sodium_100g"))  # OFF stores sodium in grams

    serving_g = _num(product.get("serving_quantity"))
    if serving_g and 5 <= serving_g <= 1000:
        factor = serving_g / 100
        serving_size_g = serving_g
        serving_description = (product.get("serving_size") or f"{serving_g:g} g").strip()[:100]
    else:
        factor, serving_size_g, serving_description = 1.0, 100.0, "100g"

    brand = (product.get("brands") or "").split(",")[0].strip()
    display_name = name if not brand or brand.lower() in name.lower() else f"{name} ({brand})"

    def scaled(value):
        return None if value is None else round(value * factor, 2)

    return {
        "external_id": f"off:{code}",
        "name": display_name[:200],
        "category": map_category(product.get("categories_tags")),
        "serving_description": serving_description,
        "serving_size_g": serving_size_g,
        "calories": round(kcal * factor, 1),
        "protein_g": round(protein * factor, 2),
        "carbs_g": round(carbs * factor, 2),
        "fat_g": round(fat * factor, 2),
        "fiber_g": scaled(fiber),
        "sodium_mg": None if sodium_g is None else round(sodium_g * 1000 * factor, 1),
        "source": f"Open Food Facts, barcode {code}",
        "search_text": re.sub(r"\s+", " ", f"{brand} {name}".lower()).strip(),
    }


def fetch_page(params, headers, retries, backoff):
    """
    GET one search page, retrying temporary failures (429/5xx, timeouts,
    dropped connections) with exponential backoff, honouring Retry-After when
    the server sends it. Returns the parsed JSON, or raises CommandError once
    retries run out.
    """
    last_error = None
    for attempt in range(retries + 1):
        wait = min(backoff * 2**attempt, MAX_BACKOFF_SECONDS)
        try:
            response = requests.get(API_URL, params=params, headers=headers, timeout=60)
            if response.status_code in RETRY_STATUSES:
                last_error = f"{response.status_code} from Open Food Facts"
                retry_after = str(response.headers.get("Retry-After", ""))
                if retry_after.isdigit():
                    wait = min(int(retry_after), MAX_BACKOFF_SECONDS)
            else:
                response.raise_for_status()  # other 4xx: not worth retrying
                return response.json()
        except requests.HTTPError as exc:
            raise CommandError(f"Open Food Facts rejected the request: {exc}")
        except (requests.RequestException, ValueError) as exc:
            last_error = str(exc)

        if attempt < retries:
            time.sleep(wait)

    raise CommandError(
        f"Open Food Facts failed on page {params['page']} after {retries + 1} attempts "
        f"({last_error}). The service is probably busy -- wait a few minutes and "
        f"resume with --start-page {params['page']}."
    )


class Command(BaseCommand):
    help = "Import Philippine packaged products from Open Food Facts into FoodItem"

    def add_arguments(self, parser):
        parser.add_argument("--country", default="philippines", help="OFF country tag (default: philippines)")
        parser.add_argument("--max-pages", type=int, default=10, help="Number of pages to fetch (default 10)")
        parser.add_argument("--start-page", type=int, default=1, help="First page to fetch, to resume after a failure (default 1)")
        parser.add_argument("--page-size", type=int, default=100, help="Products per page, 1-100 (default 100; try 50 if the server is struggling)")
        parser.add_argument("--delay", type=float, default=7.0, help="Seconds between pages (default 7)")
        parser.add_argument("--retries", type=int, default=5, help="Retries per page on 429/5xx errors (default 5)")
        parser.add_argument("--retry-backoff", type=float, default=10.0, help="First retry wait in seconds, doubling each time (default 10)")
        parser.add_argument(
            "--user-agent",
            default=os.getenv("OFF_USER_AGENT", DEFAULT_USER_AGENT),
            help="User-Agent sent to Open Food Facts (or set OFF_USER_AGENT)",
        )

    def handle(self, *args, **options):
        headers = {"User-Agent": options["user_agent"]}
        created = updated = skipped = 0

        page_size = min(max(options["page_size"], 1), 100)
        first = max(options["start_page"], 1)
        last = first + options["max_pages"] - 1

        for page in range(first, last + 1):
            data = fetch_page(
                {
                    "countries_tags_en": options["country"],
                    "fields": FIELDS,
                    "page_size": page_size,
                    "page": page,
                    "sort_by": "unique_scans_n",
                },
                headers,
                options["retries"],
                options["retry_backoff"],
            )
            products = data.get("products", [])

            if not products:
                break

            for product in products:
                fields = parse_product(product)
                if fields is None:
                    skipped += 1
                    continue
                _, was_created = FoodItem.objects.update_or_create(
                    external_id=fields["external_id"], defaults=fields
                )
                created += was_created
                updated += not was_created

            self.stdout.write(f"page {page}: {len(products)} products fetched")
            if page < last:
                time.sleep(options["delay"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported Open Food Facts data: {created} created, {updated} updated, "
                f"{skipped} skipped (missing/implausible nutrition data)."
            )
        )
