"""
Tests for: multi-source food data (USDA / Open Food Facts importers, custom
foods, search ranking) and the meal-suggestion feature. No network and no
Groq key needed -- HTTP and the LLM are faked.
"""

import csv
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .management.commands.import_openfoodfacts import parse_product
from .management.commands.import_usda import map_category
from .models import DailyEntry, FoodEntry, FoodItem, NutritionProfile
from .services.suggestion_llm import SuggestionExplainer

Account = get_user_model()


def make_food(name, category="viands_meat", calories=200, protein_g=20, carbs_g=5, fat_g=10, **kwargs):
    defaults = dict(
        serving_description="100g",
        serving_size_g=100,
        source="PhilFCT, item X001",
    )
    defaults.update(kwargs)
    return FoodItem.objects.create(
        name=name,
        category=category,
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        **defaults,
    )


def log(user, food, meal_type="lunch", servings=1.0, date=None):
    profile, _ = NutritionProfile.objects.get_or_create(user=user)
    daily, _ = DailyEntry.objects.get_or_create(
        nutrition_profile=profile, date=date or timezone.localdate()
    )
    return FoodEntry.objects.create(
        daily_entry=daily, food_item=food, meal_type=meal_type, servings=servings
    )


# --------------------------------------------------------------------- USDA


def write_csv(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def make_fdc_folder(root):
    root = Path(root)
    write_csv(
        root / "food_category.csv",
        ["id", "code", "description"],
        [
            [1, "0500", "Poultry Products"],
            [2, "0100", "Dairy and Egg Products"],
            [3, "1100", "Vegetables and Vegetable Products"],
            [4, "0300", "Baby Foods"],
        ],
    )
    write_csv(
        root / "food.csv",
        ["fdc_id", "data_type", "description", "food_category_id", "publication_date"],
        [
            [100, "sr_legacy_food", "Chicken, breast, meat only, cooked, roasted", 1, "2019-04-01"],
            [101, "foundation_food", "Egg, whole, cooked, hard-boiled", 2, "2021-10-28"],
            [102, "sr_legacy_food", "Sweet potato, cooked, baked in skin", 3, "2019-04-01"],
            [103, "sr_legacy_food", "Babyfood, banana puree", 4, "2019-04-01"],  # excluded group
            [104, "branded_food", "Some branded thing", 1, "2020-01-01"],  # wrong data type
            [105, "sr_legacy_food", "Mystery food without energy", 1, "2019-04-01"],  # no energy
            [106, "sr_legacy_food", "Milk, whole", 2, "2019-04-01"],
        ],
    )
    # Foundation egg has no 1008, only Atwater-specific 2048.
    write_csv(
        root / "food_nutrient.csv",
        ["id", "fdc_id", "nutrient_id", "amount"],
        [
            [1, 100, 1008, 165], [2, 100, 1003, 31.0], [3, 100, 1004, 3.6], [4, 100, 1005, 0], [5, 100, 1093, 74],
            [6, 101, 2048, 155], [7, 101, 1003, 12.6], [8, 101, 1004, 10.6], [9, 101, 1005, 1.1],
            [10, 102, 1008, 90], [11, 102, 1003, 2.0], [12, 102, 1004, 0.15], [13, 102, 1005, 20.7], [14, 102, 1079, 3.3],
            [15, 103, 1008, 90], [16, 103, 1003, 1.0],
            [17, 105, 1003, 5.0],
            [18, 106, 1008, 61], [19, 106, 1003, 3.2], [20, 106, 1004, 3.3], [21, 106, 1005, 4.8],
        ],
    )
    return root


class UsdaImportTests(TestCase):
    def run_import(self, folder, **kwargs):
        args = ["--dir", str(folder)]
        if kwargs.get("skip_existing_names"):
            args.append("--skip-existing-names")
        if kwargs.get("dry_run"):
            args.append("--dry-run")
        call_command("import_usda", *args, stdout=mock.MagicMock())

    def test_imports_valid_rows_and_skips_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_import(make_fdc_folder(tmp))
        names = set(FoodItem.objects.values_list("name", flat=True))
        self.assertEqual(
            names,
            {
                "Chicken, breast, meat only, cooked, roasted",
                "Egg, whole, cooked, hard-boiled",
                "Sweet potato, cooked, baked in skin",
                "Milk, whole",
            },
        )

    def test_values_source_and_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_import(make_fdc_folder(tmp))
        chicken = FoodItem.objects.get(external_id="usda:100")
        self.assertEqual((chicken.calories, chicken.protein_g, chicken.fat_g, chicken.carbs_g), (165, 31.0, 3.6, 0))
        self.assertEqual(chicken.sodium_mg, 74)
        self.assertEqual(chicken.serving_description, "100g")
        self.assertEqual(chicken.source_type, "usda")
        self.assertTrue(chicken.source.startswith("USDA FoodData Central (SR Legacy)"))

    def test_foundation_food_falls_back_to_atwater_energy(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_import(make_fdc_folder(tmp))
        self.assertEqual(FoodItem.objects.get(external_id="usda:101").calories, 155)

    def test_categories(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_import(make_fdc_folder(tmp))
        cat = lambda i: FoodItem.objects.get(external_id=f"usda:{i}").category
        self.assertEqual(cat(100), "viands_meat")
        self.assertEqual(cat(101), "eggs")  # dairy-and-egg group, but it's an egg
        self.assertEqual(cat(106), "dairy")
        self.assertEqual(cat(102), "roots_tubers")  # sweet potato, not "vegetables"

    def test_rerun_is_idempotent_and_updates_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = make_fdc_folder(tmp)
            self.run_import(folder)
            FoodItem.objects.filter(external_id="usda:100").update(calories=1)
            self.run_import(folder)
        self.assertEqual(FoodItem.objects.filter(external_id__startswith="usda:").count(), 4)
        self.assertEqual(FoodItem.objects.get(external_id="usda:100").calories, 165)

    def test_philfct_rows_are_never_touched(self):
        phil = make_food("Chicken adobo", external_id="F001", calories=999)
        with tempfile.TemporaryDirectory() as tmp:
            self.run_import(make_fdc_folder(tmp))
        phil.refresh_from_db()
        self.assertEqual(phil.calories, 999)
        self.assertEqual(phil.source_type, "philfct")

    def test_skip_existing_names(self):
        make_food("Milk, whole", category="dairy", external_id="PH9")
        with tempfile.TemporaryDirectory() as tmp:
            self.run_import(make_fdc_folder(tmp), skip_existing_names=True)
        self.assertEqual(FoodItem.objects.filter(name="Milk, whole").count(), 1)

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_import(make_fdc_folder(tmp), dry_run=True)
        self.assertEqual(FoodItem.objects.count(), 0)

    def test_missing_files_give_a_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CommandError):
                self.run_import(tmp)

    def test_map_category_unknown_group_is_other(self):
        self.assertEqual(map_category("Something New", "Whatever"), "other")


# ---------------------------------------------------------- Open Food Facts


def off_product(**overrides):
    product = {
        "code": "4800016644108",
        "product_name": "Pancit Canton Original",
        "brands": "Lucky Me!,Monde",
        "serving_quantity": "60",
        "serving_size": "1 pack (60 g)",
        "categories_tags": ["en:snacks", "en:instant-noodles"],
        "nutriments": {
            "energy-kcal_100g": 450,
            "proteins_100g": 9,
            "carbohydrates_100g": 60,
            "fat_100g": 18,
            "fiber_100g": 2,
            "sodium_100g": 1.5,
        },
    }
    product.update(overrides)
    return product


class OpenFoodFactsParseTests(TestCase):
    def test_per_serving_scaling(self):
        p = parse_product(off_product())
        self.assertEqual(p["serving_size_g"], 60)
        self.assertEqual(p["serving_description"], "1 pack (60 g)")
        self.assertAlmostEqual(p["calories"], 270)
        self.assertAlmostEqual(p["protein_g"], 5.4)
        self.assertAlmostEqual(p["sodium_mg"], 900)  # 1.5 g sodium /100g -> mg, scaled to 60 g
        self.assertEqual(p["external_id"], "off:4800016644108")
        self.assertTrue(p["source"].startswith("Open Food Facts"))
        self.assertEqual(p["name"], "Pancit Canton Original (Lucky Me!)")
        self.assertEqual(p["category"], "rice_grains")  # "instant-noodles" matches before "snacks"

    def test_falls_back_to_per_100g_without_serving(self):
        p = parse_product(off_product(serving_quantity=None, serving_size=None))
        self.assertEqual((p["serving_description"], p["serving_size_g"], p["calories"]), ("100g", 100, 450))

    def test_rejects_unusable_products(self):
        bad_nutrients = lambda **n: {"nutriments": {**off_product()["nutriments"], **n}}
        self.assertIsNone(parse_product(off_product(product_name="")))
        self.assertIsNone(parse_product(off_product(code="")))
        self.assertIsNone(parse_product(off_product(code="12345678901234567")))  # won't fit external_id
        self.assertIsNone(parse_product(off_product(nutriments={})))
        self.assertIsNone(parse_product(off_product(**bad_nutrients(**{"energy-kcal_100g": 5000}))))
        self.assertIsNone(parse_product(off_product(**bad_nutrients(proteins_100g=80, carbohydrates_100g=60))))


class OpenFoodFactsCommandTests(TestCase):
    def test_imports_pages_until_empty_and_is_idempotent(self):
        pages = [
            {"products": [off_product(), off_product(code="1", product_name="")]},
            {"products": []},
        ]
        fake = mock.MagicMock()
        fake.json.side_effect = pages + pages
        with mock.patch("nutrition.management.commands.import_openfoodfacts.requests.get", return_value=fake), \
                mock.patch("nutrition.management.commands.import_openfoodfacts.time.sleep"):
            call_command("import_openfoodfacts", max_pages=5, stdout=mock.MagicMock())
            call_command("import_openfoodfacts", max_pages=5, stdout=mock.MagicMock())
        self.assertEqual(FoodItem.objects.filter(external_id__startswith="off:").count(), 1)

    def test_connection_failure_retries_then_raises_clear_error(self):
        import requests

        with mock.patch(
            "nutrition.management.commands.import_openfoodfacts.requests.get",
            side_effect=requests.ConnectionError("boom"),
        ) as get, mock.patch("nutrition.management.commands.import_openfoodfacts.time.sleep"):
            with self.assertRaises(CommandError):
                call_command("import_openfoodfacts", "--max-pages", "1", "--retries", "2", stdout=mock.MagicMock())
        self.assertEqual(get.call_count, 3)  # 1 try + 2 retries


def off_response(status=200, products=None, headers=None):
    import requests

    r = mock.MagicMock()
    r.status_code = status
    r.headers = headers or {}
    r.json.return_value = {"products": products or []}
    if status >= 400:
        r.raise_for_status.side_effect = requests.HTTPError(f"{status} error")
    return r


class OpenFoodFactsRetryTests(TestCase):
    """503s/429s from a busy Open Food Facts are retried, not fatal."""

    GET = "nutrition.management.commands.import_openfoodfacts.requests.get"
    SLEEP = "nutrition.management.commands.import_openfoodfacts.time.sleep"

    def run_cmd(self, *args):
        call_command("import_openfoodfacts", *args, stdout=mock.MagicMock())

    def test_503_then_success_is_retried_with_backoff(self):
        responses = [off_response(503), off_response(200, [off_product()])]
        with mock.patch(self.GET, side_effect=responses), mock.patch(self.SLEEP) as sleep:
            self.run_cmd("--max-pages", "1")
        self.assertEqual(FoodItem.objects.filter(external_id__startswith="off:").count(), 1)
        sleep.assert_called_once_with(10.0)  # first backoff

    def test_backoff_doubles_each_attempt(self):
        responses = [off_response(503), off_response(503), off_response(200, [off_product()])]
        with mock.patch(self.GET, side_effect=responses), mock.patch(self.SLEEP) as sleep:
            self.run_cmd("--max-pages", "1")
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [10.0, 20.0])

    def test_retry_after_header_is_honoured(self):
        responses = [off_response(429, headers={"Retry-After": "30"}), off_response(200, [off_product()])]
        with mock.patch(self.GET, side_effect=responses), mock.patch(self.SLEEP) as sleep:
            self.run_cmd("--max-pages", "1")
        sleep.assert_called_once_with(30)

    def test_persistent_503_raises_with_resume_hint(self):
        with mock.patch(self.GET, return_value=off_response(503)) as get, mock.patch(self.SLEEP):
            with self.assertRaises(CommandError) as ctx:
                self.run_cmd("--max-pages", "1", "--retries", "2")
        self.assertEqual(get.call_count, 3)
        self.assertIn("--start-page 1", str(ctx.exception))

    def test_non_retryable_error_fails_immediately(self):
        with mock.patch(self.GET, return_value=off_response(404)) as get, mock.patch(self.SLEEP) as sleep:
            with self.assertRaises(CommandError):
                self.run_cmd("--max-pages", "1")
        self.assertEqual(get.call_count, 1)
        sleep.assert_not_called()

    def test_earlier_pages_are_kept_when_a_later_page_fails(self):
        responses = [off_response(200, [off_product()])] + [off_response(503)] * 3
        with mock.patch(self.GET, side_effect=responses), mock.patch(self.SLEEP):
            with self.assertRaises(CommandError) as ctx:
                self.run_cmd("--max-pages", "3", "--retries", "2")
        self.assertEqual(FoodItem.objects.filter(external_id__startswith="off:").count(), 1)
        self.assertIn("--start-page 2", str(ctx.exception))

    def test_start_page_and_page_size_are_sent(self):
        with mock.patch(self.GET, return_value=off_response(200, [])) as get, mock.patch(self.SLEEP):
            self.run_cmd("--start-page", "3", "--max-pages", "2", "--page-size", "50")
        sent = get.call_args.kwargs["params"]
        self.assertEqual((sent["page"], sent["page_size"]), (3, 50))


# ------------------------------------------------------- search + custom food


class SearchAndCustomFoodTests(APITestCase):
    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        self.other = Account.objects.create_user(email="b@test.com", password="pass12345")
        self.client.force_authenticate(user=self.user)

    def names(self, query):
        data = self.client.get(f"/nutrition/foods/search/?q={query}").data
        return [f["name"] for f in data["results"]]

    def test_all_words_match_in_any_order(self):
        make_food(
            "Chicken, broilers or fryers, breast, meat only, cooked",
            source="USDA FoodData Central (SR Legacy), FDC 1",
            external_id="usda:1",
        )
        self.assertEqual(len(self.names("chicken breast")), 1)
        self.assertEqual(len(self.names("breast chicken")), 1)
        self.assertEqual(self.names("chicken pork"), [])

    def test_philfct_ranks_before_usda_for_same_match(self):
        make_food("Aaa Rice, white, cooked", category="rice_grains", source="USDA FoodData Central (SR Legacy), FDC 2")
        make_food("Zzz Rice, milled, cooked", category="rice_grains", source="PhilFCT, item A1")
        self.assertEqual(self.names("rice")[0], "Zzz Rice, milled, cooked")

    def test_name_prefix_match_ranks_first(self):
        make_food("Fried rice", category="rice_grains")
        make_food("Rice, white", category="rice_grains", source="USDA FoodData Central (SR Legacy), FDC 3")
        self.assertEqual(self.names("rice")[0], "Rice, white")

    def test_serializer_exposes_source_fields(self):
        make_food("Tinola", source="PhilFCT, item B2")
        make_food("Oats", source="USDA FoodData Central (SR Legacy), FDC 4")
        make_food("Lucky Me", source="Open Food Facts, barcode 123")
        make_food("Home dish", source="estimated")
        data = {f["name"]: f for f in self.client.get("/nutrition/foods/search/").data["results"]}
        self.assertEqual(data["Tinola"]["source_label"], "PhilFCT")
        self.assertTrue(data["Tinola"]["is_verified"])
        self.assertEqual(data["Oats"]["source_label"], "USDA")
        self.assertFalse(data["Oats"]["is_verified"])  # legacy flag: PhilFCT only
        self.assertEqual(data["Lucky Me"]["source_type"], "openfoodfacts")
        self.assertEqual(data["Home dish"]["source_label"], "Estimated")

    VALID = {
        "name": "Mom's Tinola",
        "category": "soups",
        "serving_description": "1 bowl",
        "serving_size_g": 300,
        "calories": 250,
        "protein_g": 25,
        "carbs_g": 10,
        "fat_g": 12,
    }

    def test_create_custom_food_is_private_to_creator(self):
        r = self.client.post("/nutrition/foods/custom/", self.VALID, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertTrue(r.data["is_custom"])
        self.assertEqual(r.data["source_label"], "My food")
        self.assertEqual(len(self.names("tinola")), 1)

        self.client.force_authenticate(user=self.other)
        self.assertEqual(self.names("tinola"), [])

    def test_calorie_macro_mismatch_is_rejected(self):
        r = self.client.post("/nutrition/foods/custom/", {**self.VALID, "calories": 900}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_negative_and_absurd_values_rejected(self):
        for bad in ({"protein_g": -1}, {"serving_size_g": 0}, {"calories": 99999}):
            r = self.client.post("/nutrition/foods/custom/", {**self.VALID, **bad}, format="json")
            self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, bad)

    def test_cannot_edit_or_delete_someone_elses_food(self):
        food_id = self.client.post("/nutrition/foods/custom/", self.VALID, format="json").data["id"]
        self.client.force_authenticate(user=self.other)
        self.assertEqual(self.client.patch(f"/nutrition/foods/custom/{food_id}/", {"name": "x"}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(f"/nutrition/foods/custom/{food_id}/").status_code, 404)

    def test_edit_and_delete_unused_custom_food(self):
        food_id = self.client.post("/nutrition/foods/custom/", self.VALID, format="json").data["id"]
        r = self.client.patch(f"/nutrition/foods/custom/{food_id}/", {"name": "Tinola v2"}, format="json")
        self.assertEqual(r.data["name"], "Tinola v2")
        self.assertEqual(self.client.delete(f"/nutrition/foods/custom/{food_id}/").status_code, 204)

    def test_cannot_delete_custom_food_already_logged(self):
        food_id = self.client.post("/nutrition/foods/custom/", self.VALID, format="json").data["id"]
        log(self.user, FoodItem.objects.get(pk=food_id))
        self.assertEqual(self.client.delete(f"/nutrition/foods/custom/{food_id}/").status_code, 409)

    def test_endpoints_require_auth(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.post("/nutrition/foods/custom/", self.VALID, format="json").status_code, 401)
        self.assertEqual(self.client.get("/nutrition/suggestions/?meal_type=lunch").status_code, 401)


# ------------------------------------------------------------ suggestions


class SuggestionTests(APITestCase):
    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        self.other = Account.objects.create_user(email="b@test.com", password="pass12345")
        self.client.force_authenticate(user=self.user)
        # Defaults: 2000 kcal / 100 g protein / 250 g carbs / 65 g fat
        self.profile, _ = NutritionProfile.objects.get_or_create(user=self.user)
        self.chicken = make_food("Chicken breast, cooked", calories=165, protein_g=31, carbs_g=0, fat_g=3.6)
        self.rice = make_food("Rice, cooked", category="rice_grains", calories=130, protein_g=2.7, carbs_g=28, fat_g=0.3)
        self.egg = make_food("Egg, boiled", category="eggs", calories=155, protein_g=12.6, carbs_g=1.1, fat_g=10.6)
        self.raw_pork = make_food("Pork belly, raw", calories=518, protein_g=9, carbs_g=0, fat_g=53)
        self.rice_flour = make_food("Rice flour", category="rice_grains", calories=366, protein_g=6, carbs_g=80, fat_g=1.4)
        self.raw_veg = make_food("Cabbage, raw", category="vegetables", calories=45, protein_g=1.5, carbs_g=9, fat_g=0.1)

    def get(self, **params):
        params.setdefault("meal_type", "lunch")
        params.setdefault("explain", "false")
        return self.client.get("/nutrition/suggestions/", params)

    def food_names(self, response):
        return [s["food"]["name"] for s in response.data["suggestions"]]

    def test_rule_based_suggestions_are_real_foods_with_amounts(self):
        r = self.get()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["suggestions"])
        for s in r.data["suggestions"]:
            food = FoodItem.objects.get(pk=s["food"]["id"])
            self.assertAlmostEqual(s["calories"], food.calories * s["servings"], delta=0.1)
            self.assertEqual(s["reason_source"], "rule")
            self.assertTrue(s["reason"])
            self.assertIn("g", s["amount_label"])
        self.assertEqual(r.data["remaining"]["calories"], 2000.0)

    def test_high_protein_food_ranks_above_pure_carbs_when_protein_is_needed(self):
        names = self.food_names(self.get())
        self.assertLess(names.index("Chicken breast, cooked"), names.index("Rice, cooked"))

    def test_raw_and_flour_items_excluded_but_raw_veg_allowed(self):
        names = self.food_names(self.get(limit=8))
        self.assertNotIn("Pork belly, raw", names)
        self.assertNotIn("Rice flour", names)
        self.assertIn("Cabbage, raw", names)

    def test_foods_already_logged_today_are_not_suggested(self):
        log(self.user, self.chicken)
        self.assertNotIn("Chicken breast, cooked", self.food_names(self.get()))

    def test_never_exceeds_remaining_calories(self):
        # 150 kcal left. A calorie-dense food (700 kcal/100 g) can't be
        # portioned below 0.5 servings = 350 kcal, so it must be dropped
        # rather than pushing the user over their goal.
        make_food("Dense nuts", category="nuts_legumes", calories=700, protein_g=20, carbs_g=20, fat_g=60)
        log(self.user, make_food("Big meal", calories=1850, protein_g=50, carbs_g=100, fat_g=40))
        r = self.get(limit=8)
        self.assertEqual(r.data["remaining"]["calories"], 150.0)
        self.assertTrue(r.data["suggestions"])  # lighter foods still fit
        self.assertNotIn("Dense nuts", self.food_names(r))
        for s in r.data["suggestions"]:
            self.assertLessEqual(s["calories"], 150.0)

    def test_full_day_returns_empty_with_message(self):
        log(self.user, make_food("Huge", calories=2000, protein_g=100, carbs_g=250, fat_g=65))
        r = self.get()
        self.assertEqual(r.data["suggestions"], [])
        self.assertIn("goal", r.data["message"])

    def test_meal_type_filters_categories(self):
        r = self.get(meal_type="breakfast")
        self.assertNotIn("Cabbage, raw", self.food_names(r))  # vegetables aren't breakfast candidates

    def test_other_users_custom_foods_never_suggested(self):
        make_food("Secret dish", calories=200, protein_g=40, carbs_g=0, fat_g=4, created_by=self.other, source="User-submitted")
        make_food("My dish", calories=200, protein_g=40, carbs_g=0, fat_g=4, created_by=self.user, source="User-submitted")
        names = self.food_names(self.get(limit=8))
        self.assertNotIn("Secret dish", names)
        self.assertIn("My dish", names)

    def test_familiar_foods_get_a_boost(self):
        a = make_food("Tilapia A, cooked", category="viands_fish", calories=130, protein_g=26, carbs_g=0, fat_g=2.7)
        b = make_food("Tilapia B, cooked", category="viands_fish", calories=130, protein_g=26, carbs_g=0, fat_g=2.7)
        yesterday = timezone.localdate() - timezone.timedelta(days=1)
        for _ in range(3):
            log(self.user, b, date=yesterday)
        names = self.food_names(self.get(limit=8))
        self.assertLess(names.index("Tilapia B, cooked"), names.index("Tilapia A, cooked"))

    def test_exclude_skips_already_shown_foods(self):
        first = self.food_names(self.get(limit=2))
        shown_ids = [s["food"]["id"] for s in self.get(limit=2).data["suggestions"]]
        r = self.get(limit=8, exclude=",".join(str(i) for i in shown_ids))
        for name in first:
            self.assertNotIn(name, self.food_names(r))
        self.assertTrue(r.data["suggestions"])

    def test_exclude_ignores_junk_and_empties_out_with_message(self):
        every_id = ",".join(str(f.id) for f in FoodItem.objects.all())
        r = self.get(exclude=every_id + ",abc,,-5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["suggestions"], [])
        self.assertEqual(r.data["message"], "That's all the ideas for now.")
        self.assertEqual(self.get(exclude="abc,,x").status_code, 200)

    def test_portions_are_capped_to_something_realistic(self):
        # A big calorie goal makes the per-item target 450 kcal, which for
        # lean chicken (165 kcal/100 g) used to mean 250 g in one serving.
        self.profile.daily_calories_goal = 4000
        self.profile.save()
        r = self.get(limit=8)
        chicken = next(s for s in r.data["suggestions"] if s["food"]["name"] == "Chicken breast, cooked")
        self.assertLessEqual(chicken["servings"] * 100, 150)
        self.assertEqual(chicken["amount_label"], "150 g")

    def test_one_serving_label_has_no_multiplier(self):
        make_food(
            "Garlic rice", category="rice_grains", calories=280, protein_g=6, carbs_g=50, fat_g=6,
            serving_description="1 cup cooked", serving_size_g=150,
        )
        make_food(
            "Fried tilapia", category="viands_fish", calories=190, protein_g=30, carbs_g=2, fat_g=7,
            serving_description="1 piece (medium)", serving_size_g=120,
        )
        r = self.get(limit=8)
        labels = {s["food"]["name"]: s["amount_label"] for s in r.data["suggestions"]}
        self.assertEqual(labels["Garlic rice"], "1 cup cooked")
        for name, label in labels.items():
            self.assertNotIn("1 x", label, name)

    def test_variety_cap_per_category(self):
        for i in range(6):
            make_food(f"Egg dish {i}", category="eggs", calories=150, protein_g=13, carbs_g=1, fat_g=10)
        r = self.get(limit=8)
        eggs = [s for s in r.data["suggestions"] if s["food"]["category"] == "eggs"]
        self.assertLessEqual(len(eggs), 3)

    def test_validation(self):
        self.assertEqual(self.client.get("/nutrition/suggestions/").status_code, 400)
        self.assertEqual(self.client.get("/nutrition/suggestions/?meal_type=brunch").status_code, 400)
        self.assertEqual(self.get(date="not-a-date").status_code, 400)

    def test_does_not_create_daily_entry_rows(self):
        self.get()
        self.assertFalse(DailyEntry.objects.exists())

    def test_llm_failure_falls_back_to_rule_based(self):
        with mock.patch("nutrition.views.SuggestionExplainer", side_effect=ValueError("no key")):
            r = self.client.get("/nutrition/suggestions/", {"meal_type": "lunch"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["suggestions"])
        self.assertTrue(all(s["reason_source"] == "rule" for s in r.data["suggestions"]))

    def test_llm_picks_are_used_in_its_order(self):
        def fake_pick(self_, meal_type, remaining, candidates, limit):
            by_name = {c.food.name: c for c in candidates}
            return [(by_name["Rice, cooked"], "Easy carbs for energy."), (by_name["Egg, boiled"], "Quick protein.")]

        with mock.patch.object(SuggestionExplainer, "__init__", lambda s: None), \
                mock.patch.object(SuggestionExplainer, "pick_and_explain", fake_pick):
            r = self.client.get("/nutrition/suggestions/", {"meal_type": "lunch"})
        self.assertEqual(self.food_names(r), ["Rice, cooked", "Egg, boiled"])
        self.assertEqual([s["reason_source"] for s in r.data["suggestions"]], ["ai", "ai"])
        self.assertEqual(r.data["suggestions"][0]["reason"], "Easy carbs for energy.")


class SuggestionExplainerTests(TestCase):
    """The LLM can only choose among real candidates; everything else is dropped."""

    def setUp(self):
        from .services.food_suggester import Remaining, Suggestion

        self.remaining = Remaining(2000, 1500, 80, 200, 50)
        self.foods = [make_food(f"Food {i}") for i in range(4)]
        self.cands = [
            Suggestion(food=f, servings=1, calories=200, protein_g=20, carbs_g=5, fat_g=10, amount_label="100 g", score=1)
            for f in self.foods
        ]

    def explainer(self, content, finish_reason="stop"):
        completion = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)]
        )
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: completion)))
        return SuggestionExplainer(client=client, model="m")

    def ids(self):
        return [f.id for f in self.foods]

    def run_pick(self, content, **kw):
        return self.explainer(content, **kw).pick_and_explain("lunch", self.remaining, self.cands, 3)

    def test_valid_picks(self):
        a, b, *_ = self.ids()
        picks = self.run_pick(f'{{"suggestions":[{{"food_id":{b},"reason":"Good."}},{{"food_id":{a},"reason":"Also good."}}]}}')
        self.assertEqual([c.food.id for c, _ in picks], [b, a])

    def test_hallucinated_and_duplicate_ids_dropped(self):
        a, b, c, _ = self.ids()
        picks = self.run_pick(
            f'{{"suggestions":[{{"food_id":999999,"reason":"Fake."}},'
            f'{{"food_id":{a},"reason":"One."}},{{"food_id":{a},"reason":"Dup."}},{{"food_id":{b},"reason":"Two."}}]}}'
        )
        self.assertEqual([c.food.id for c, _ in picks], [a, b])

    def test_too_few_valid_picks_returns_none(self):
        self.assertIsNone(self.run_pick(f'{{"suggestions":[{{"food_id":{self.ids()[0]},"reason":"Only one."}}]}}'))

    def test_bad_json_or_shape_returns_none(self):
        for content in ("not json", "{}", '{"suggestions": "nope"}', None):
            self.assertIsNone(self.run_pick(content), content)

    def test_truncated_response_returns_none(self):
        a, b, *_ = self.ids()
        content = f'{{"suggestions":[{{"food_id":{a},"reason":"x"}},{{"food_id":{b},"reason":"y"}}]}}'
        self.assertIsNone(self.run_pick(content, finish_reason="length"))

    def test_boolean_ids_and_blank_reasons_rejected(self):
        a, b, *_ = self.ids()
        # json true == 1 in Python; must not be accepted as food id 1
        picks = self.run_pick(
            f'{{"suggestions":[{{"food_id":true,"reason":"x"}},{{"food_id":{a},"reason":"  "}},'
            f'{{"food_id":{b},"reason":"ok"}}]}}'
        )
        self.assertIsNone(picks)

    def test_reason_length_is_capped(self):
        a, b, *_ = self.ids()
        long = "x" * 500
        picks = self.run_pick(f'{{"suggestions":[{{"food_id":{a},"reason":"{long}"}},{{"food_id":{b},"reason":"ok"}}]}}')
        self.assertLessEqual(len(picks[0][1]), 160)
