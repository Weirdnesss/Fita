"""
Tests for whole-plate suggestions (GET /nutrition/suggestions/meals/), the
atomic "Add all" endpoint (POST /nutrition/entries/bulk/), and the rule that
a user can only log foods they're allowed to see. No network or Groq key
needed -- the LLM is faked.
"""

import datetime
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import DailyEntry, FoodEntry, FoodItem, NutritionProfile
from .services.food_suggester import Remaining
from .services.meal_builder import Plate, PlateItem, build_meal_suggestions
from .services.suggestion_llm import SuggestionExplainer

Account = get_user_model()


def make_food(name, category, calories, protein_g, carbs_g, fat_g, **kwargs):
    defaults = dict(serving_description="100g", serving_size_g=100, source="PhilFCT, item X001")
    defaults.update(kwargs)
    return FoodItem.objects.create(
        name=name, category=category, calories=calories, protein_g=protein_g, carbs_g=carbs_g, fat_g=fat_g, **defaults
    )


def log(user, food, servings=1.0, meal_type="lunch", date=None):
    profile, _ = NutritionProfile.objects.get_or_create(user=user)
    daily, _ = DailyEntry.objects.get_or_create(nutrition_profile=profile, date=date or timezone.localdate())
    return FoodEntry.objects.create(daily_entry=daily, food_item=food, meal_type=meal_type, servings=servings)


@override_settings(FOOD_SUGGESTIONS_ENABLED=True)
class PlateTestBase(APITestCase):
    """A small but complete food database, and an authenticated user with the default 2000 kcal goals."""

    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        self.other = Account.objects.create_user(email="b@test.com", password="pass12345")
        self.client.force_authenticate(user=self.user)
        self.profile, _ = NutritionProfile.objects.get_or_create(user=self.user)

        self.chicken = make_food("Chicken breast, cooked", "viands_meat", 165, 31, 0, 3.6)
        self.tilapia = make_food("Tilapia, cooked", "viands_fish", 128, 26, 0, 2.7)
        self.egg = make_food("Egg, boiled", "eggs", 155, 12.6, 1.1, 10.6)
        self.tofu = make_food("Tofu, firm", "nuts_legumes", 144, 15.8, 3.9, 8.7)
        self.rice = make_food("Rice, cooked", "rice_grains", 130, 2.7, 28, 0.3)
        self.camote = make_food("Camote, baked", "roots_tubers", 90, 2, 20.7, 0.15)
        self.kangkong = make_food("Kangkong, cooked", "vegetables", 19, 2.6, 3.1, 0.2)
        self.cabbage = make_food("Cabbage, cooked", "vegetables", 25, 1.3, 5.8, 0.1)
        self.banana = make_food("Banana", "fruits", 89, 1.1, 22.8, 0.3)
        self.yogurt = make_food("Greek yogurt", "dairy", 97, 9, 3.9, 5)

    def get(self, **params):
        params.setdefault("meal_type", "lunch")
        params.setdefault("explain", "false")
        return self.client.get("/nutrition/suggestions/meals/", params)

    def mains(self, response):
        return [m["items"][0]["food"]["name"] for m in response.data["meals"]]


class PlateBuilderTests(PlateTestBase):
    def test_lunch_plates_have_a_protein_and_a_carb_and_realistic_portions(self):
        r = self.get(limit=6)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["meals"])
        for meal in r.data["meals"]:
            roles = [i["role"] for i in meal["items"]]
            self.assertEqual(roles[:2], ["protein", "carb"])
            for item in meal["items"]:
                grams = item["servings"] * item["food"]["serving_size_g"]
                limit = {"protein": 150, "carb": 250, "veg": 150}[item["role"]]
                self.assertLessEqual(grams, limit, item["food"]["name"])
                self.assertGreaterEqual(grams, 50)
        self.assertTrue(any("veg" in [i["role"] for i in m["items"]] for m in r.data["meals"]))

    def test_totals_and_item_numbers_are_consistent_with_the_database(self):
        for meal in self.get(limit=6).data["meals"]:
            self.assertAlmostEqual(sum(i["calories"] for i in meal["items"]), meal["totals"]["calories"], delta=1)
            self.assertAlmostEqual(sum(i["protein_g"] for i in meal["items"]), meal["totals"]["protein_g"], delta=1)
            for item in meal["items"]:
                food = FoodItem.objects.get(pk=item["food"]["id"])
                self.assertAlmostEqual(item["calories"], food.calories * item["servings"], delta=0.1)

    def test_a_plate_never_exceeds_the_calories_left_today(self):
        log(self.user, make_food("Big", "viands_meat", 1650, 80, 100, 60))  # leaves 350 kcal
        r = self.get(limit=6)
        self.assertEqual(r.data["remaining"]["calories"], 350.0)
        self.assertTrue(r.data["meals"])
        for meal in r.data["meals"]:
            self.assertLessEqual(meal["totals"]["calories"], 350.0)

    def test_plate_reaches_a_meaningful_share_of_the_meal_target(self):
        # lunch target = 35% of 2000 = 700; a plate must reach at least 45% of it
        for meal in self.get(limit=6).data["meals"]:
            self.assertGreaterEqual(meal["totals"]["calories"], 0.45 * 700 - 1)

    def test_breakfast_uses_fruit_not_veg_and_snack_has_no_carb(self):
        breakfast_roles = {i["role"] for m in self.get(meal_type="breakfast", limit=6).data["meals"] for i in m["items"]}
        self.assertNotIn("veg", breakfast_roles)
        self.assertIn("fruit", breakfast_roles)
        snack = self.get(meal_type="snack", limit=6).data["meals"]
        self.assertTrue(snack)
        for meal in snack:
            self.assertNotIn("carb", [i["role"] for i in meal["items"]])
            self.assertLessEqual(len(meal["items"]), 2)

    def test_each_plate_has_a_different_main_item(self):
        mains = self.mains(self.get(limit=6))
        self.assertEqual(len(mains), len(set(mains)))

    def test_a_plate_too_small_to_be_a_meal_is_not_suggested(self):
        # Only very light foods exist, so the biggest realistic plate is ~230 kcal,
        # well under half of a 700 kcal lunch. That's a snack, not a meal.
        FoodItem.objects.all().delete()
        make_food("Egg white, cooked", "eggs", 52, 11, 0.7, 0.2)
        make_food("Lugaw", "rice_grains", 50, 1.5, 12, 0.2)
        make_food("Kangkong, cooked", "vegetables", 19, 2.6, 3.1, 0.2)
        r = self.get()
        self.assertEqual(r.data["meals"], [])
        self.assertIn("Couldn't put together", r.data["message"])

    def test_not_enough_calories_left_gives_a_message_not_tiny_plates(self):
        log(self.user, make_food("Huge", "viands_meat", 1900, 90, 100, 60))  # leaves 100 kcal
        r = self.get()
        self.assertEqual(r.data["meals"], [])
        self.assertIn("enough calories", r.data["message"])

    def test_no_carb_foods_means_no_plate(self):
        FoodItem.objects.filter(category__in=["rice_grains", "roots_tubers"]).delete()
        r = self.get()
        self.assertEqual(r.data["meals"], [])
        self.assertIn("Couldn't put together", r.data["message"])

    def test_a_missing_optional_side_still_gives_plates(self):
        FoodItem.objects.filter(category="vegetables").delete()
        r = self.get()
        self.assertTrue(r.data["meals"])
        self.assertTrue(all([i["role"] for i in m["items"]] == ["protein", "carb"] for m in r.data["meals"]))

    def test_exclude_skips_those_foods_as_the_main_item(self):
        first = self.get(limit=2)
        shown = [m["items"][0]["food"]["id"] for m in first.data["meals"]]
        second = self.get(limit=6, exclude=",".join(map(str, shown)))
        for main in self.mains(second):
            self.assertNotIn(FoodItem.objects.get(name=main).id, shown)

    def test_excluding_every_possible_main_ends_with_a_message(self):
        every_protein = ",".join(str(f.id) for f in (self.chicken, self.tilapia, self.egg, self.tofu))
        r = self.get(exclude=every_protein + ",abc,,-1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["meals"], [])
        self.assertEqual(r.data["message"], "That's all the meal ideas for now.")

    def test_a_food_already_eaten_today_is_not_the_main_item_again(self):
        log(self.user, self.chicken)
        self.assertNotIn("Chicken breast, cooked", self.mains(self.get(limit=6)))

    def test_foods_eaten_often_are_favoured(self):
        a = make_food("Bangus A, fried", "viands_fish", 150, 28, 0, 4)
        b = make_food("Bangus B, fried", "viands_fish", 150, 28, 0, 4)
        yesterday = timezone.localdate() - datetime.timedelta(days=1)
        for _ in range(4):
            log(self.user, b, date=yesterday)
        mains = self.mains(self.get(limit=6))
        self.assertLess(mains.index("Bangus B, fried"), mains.index("Bangus A, fried"))

    def test_other_users_custom_foods_never_appear_but_your_own_can(self):
        make_food("Secret protein", "viands_meat", 200, 45, 0, 3, created_by=self.other, source="User-submitted")
        make_food("My protein", "viands_meat", 200, 45, 0, 3, created_by=self.user, source="User-submitted")
        names = {i["food"]["name"] for m in self.get(limit=8).data["meals"] for i in m["items"]}
        self.assertNotIn("Secret protein", names)
        self.assertIn("My protein", names)

    def test_raw_flour_and_seasoning_items_are_not_used(self):
        make_food("Pork belly, raw", "viands_meat", 518, 9, 0, 53)
        make_food("Rice flour", "rice_grains", 366, 6, 80, 1.4)
        make_food("Garlic, raw", "vegetables", 149, 6.4, 33, 0.5)
        make_food("Tomato paste", "vegetables", 82, 4.3, 19, 0.5)
        names = {i["food"]["name"] for m in self.get(limit=8).data["meals"] for i in m["items"]}
        for banned in ("Pork belly, raw", "Rice flour", "Garlic, raw", "Tomato paste"):
            self.assertNotIn(banned, names)

    def test_validation_and_auth(self):
        self.assertEqual(self.client.get("/nutrition/suggestions/meals/").status_code, 400)
        self.assertEqual(self.get(meal_type="brunch").status_code, 400)
        self.assertEqual(self.get(date="nope").status_code, 400)
        self.client.force_authenticate(user=None)
        self.assertEqual(self.get().status_code, 401)

    def test_does_not_create_daily_entry_rows(self):
        self.get()
        self.assertFalse(DailyEntry.objects.exists())

    def test_service_returns_plates_best_first(self):
        remaining, plates = build_meal_suggestions(self.user, self.profile, "dinner", timezone.localdate(), limit=5)
        self.assertEqual(remaining.calories, 2000.0)
        self.assertEqual([p.score for p in plates], sorted((p.score for p in plates), reverse=True))


class PlateExplanationTests(PlateTestBase):
    def test_llm_failure_falls_back_to_rule_based_reasons(self):
        with mock.patch("nutrition.views.SuggestionExplainer", side_effect=ValueError("no key")):
            r = self.client.get("/nutrition/suggestions/meals/", {"meal_type": "lunch"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["meals"])
        self.assertTrue(all(m["reason_source"] == "rule" and m["reason"] for m in r.data["meals"]))

    def test_llm_picks_are_used_in_its_order(self):
        def fake_pick(self_, meal_type, remaining, plates, limit):
            return [(plates[1], "Lean and filling."), (plates[0], "Classic plate.")]

        with mock.patch.object(SuggestionExplainer, "__init__", lambda s: None), \
                mock.patch.object(SuggestionExplainer, "pick_meals", fake_pick):
            ai = self.client.get("/nutrition/suggestions/meals/", {"meal_type": "lunch"})
        rule = self.get()
        self.assertEqual([m["reason_source"] for m in ai.data["meals"]], ["ai", "ai"])
        self.assertEqual(ai.data["meals"][0]["reason"], "Lean and filling.")
        self.assertEqual(ai.data["meals"][0]["items"][0]["food"]["id"], rule.data["meals"][1]["items"][0]["food"]["id"])


class PickMealsTests(TestCase):
    """The LLM can only choose among real plates; everything else is dropped."""

    def setUp(self):
        self.remaining = Remaining(2000, 1500, 80, 200, 50)
        self.plates = []
        for i in range(4):
            food = make_food(f"Food {i}", "viands_meat", 200, 20, 5, 10)
            item = PlateItem(
                food=food, role="protein", servings=1, calories=200, protein_g=20, carbs_g=5, fat_g=10, amount_label="100 g"
            )
            self.plates.append(Plate(items=[item], calories=200, protein_g=20, carbs_g=5, fat_g=10, score=1))

    def explainer(self, content, finish_reason="stop"):
        self.sent = []

        def create(**kwargs):
            self.sent.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)]
            )

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        return SuggestionExplainer(client=client, model="m")

    def pick(self, content, **kw):
        return self.explainer(content, **kw).pick_meals("lunch", self.remaining, self.plates, 3)

    def test_valid_picks_map_back_to_plates(self):
        picks = self.pick('{"meals":[{"meal_id":2,"reason":"Good."},{"meal_id":0,"reason":"Also good."}]}')
        self.assertEqual([p for p, _ in picks], [self.plates[2], self.plates[0]])

    def test_hallucinated_and_duplicate_ids_are_dropped(self):
        picks = self.pick(
            '{"meals":[{"meal_id":99,"reason":"x"},{"meal_id":-1,"reason":"x"},{"meal_id":1,"reason":"One."},'
            '{"meal_id":1,"reason":"Dup."},{"meal_id":3,"reason":"Two."}]}'
        )
        self.assertEqual([p for p, _ in picks], [self.plates[1], self.plates[3]])
        self.assertEqual([r for _, r in picks], ["One.", "Two."])

    def test_a_json_boolean_is_not_accepted_as_a_plate_id(self):
        # In Python True == 1, so a sloppy check would treat `true` as plate 1.
        picks = self.pick(
            '{"meals":[{"meal_id":true,"reason":"bool"},{"meal_id":0,"reason":"A"},{"meal_id":3,"reason":"B"}]}'
        )
        self.assertEqual([p for p, _ in picks], [self.plates[0], self.plates[3]])

    def test_unusable_answers_return_none(self):
        for content in ("not json", "{}", '{"meals":"nope"}', '{"meals":[{"meal_id":0,"reason":"only one"}]}', None):
            self.assertIsNone(self.pick(content), content)
        self.assertIsNone(self.pick('{"meals":[{"meal_id":0,"reason":"a"},{"meal_id":1,"reason":"b"}]}', finish_reason="length"))

    def test_model_only_sees_database_foods_and_numbers(self):
        self.pick('{"meals":[{"meal_id":0,"reason":"a"},{"meal_id":1,"reason":"b"}]}')
        user_message = self.sent[0]["messages"][1]["content"]
        for plate in self.plates:
            self.assertIn(plate.items[0].food.name, user_message)
        self.assertIn("candidate_meals", user_message)

    def test_single_food_picking_still_works_after_the_refactor(self):
        from .services.food_suggester import Suggestion

        cands = [
            Suggestion(food=p.items[0].food, servings=1, calories=200, protein_g=20, carbs_g=5, fat_g=10, amount_label="100 g", score=1)
            for p in self.plates
        ]
        a, b = cands[0].food.id, cands[1].food.id
        content = f'{{"suggestions":[{{"food_id":{b},"reason":"x"}},{{"food_id":{a},"reason":"y"}}]}}'
        picks = self.explainer(content).pick_and_explain("lunch", self.remaining, cands, 3)
        self.assertEqual([c.food.id for c, _ in picks], [b, a])


class BulkLogTests(PlateTestBase):
    def url(self):
        return "/nutrition/entries/bulk/"

    def payload(self, **overrides):
        body = {
            "meal_type": "lunch",
            "items": [
                {"food_item": self.chicken.id, "servings": 1.5},
                {"food_item": self.rice.id, "servings": 2},
                {"food_item": self.kangkong.id, "servings": 1},
            ],
        }
        body.update(overrides)
        return body

    def post(self, **overrides):
        return self.client.post(self.url(), self.payload(**overrides), format="json")

    def test_logs_every_item_with_snapshotted_macros(self):
        r = self.post()
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(r.data), 3)
        entries = FoodEntry.objects.order_by("id")
        self.assertEqual([e.meal_type for e in entries], ["lunch"] * 3)
        self.assertAlmostEqual(entries[0].calories, 165 * 1.5)
        self.assertAlmostEqual(entries[1].carbs_g, 28 * 2)
        self.assertEqual(DailyEntry.objects.count(), 1)

    def test_uses_the_requested_date_within_the_window(self):
        two_days_ago = (timezone.localdate() - datetime.timedelta(days=2)).isoformat()
        self.assertEqual(self.post(date=two_days_ago).status_code, 201)
        self.assertEqual(DailyEntry.objects.get().date.isoformat(), two_days_ago)

    def test_rejects_bad_input_and_logs_nothing(self):
        today = timezone.localdate()
        cases = {
            "empty items": {"items": []},
            "items not a list": {"items": "nope"},
            "too many items": {"items": [{"food_item": self.rice.id, "servings": 1}] * 11},
            "bad meal type": {"meal_type": "brunch"},
            "future date": {"date": (today + datetime.timedelta(days=1)).isoformat()},
            "too old": {"date": (today - datetime.timedelta(days=30)).isoformat()},
            "bad date": {"date": "tomorrow"},
            "zero servings": {"items": [{"food_item": self.rice.id, "servings": 0}]},
            "huge servings": {"items": [{"food_item": self.rice.id, "servings": 500}]},
            "item not an object": {"items": [5]},
            "missing food": {"items": [{"servings": 1}]},
            "junk food id": {"items": [{"food_item": "abc", "servings": 1}]},
            "list food id": {"items": [{"food_item": [1], "servings": 1}]},
        }
        for label, override in cases.items():
            r = self.post(**override)
            self.assertIn(r.status_code, (400, 404), label)
        self.assertFalse(FoodEntry.objects.exists())

    def test_one_bad_item_means_nothing_is_logged(self):
        items = [{"food_item": self.chicken.id, "servings": 1}, {"food_item": 999999, "servings": 1}]
        r = self.post(items=items)
        self.assertEqual(r.status_code, 404)
        self.assertFalse(FoodEntry.objects.exists())
        self.assertFalse(DailyEntry.objects.exists())

    def test_all_or_nothing_even_if_saving_fails_midway(self):
        real_create = FoodEntry.objects.create
        calls = {"n": 0}

        def flaky(**kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("disk full")
            return real_create(**kwargs)

        with mock.patch.object(FoodEntry.objects, "create", side_effect=flaky):
            with self.assertRaises(RuntimeError):
                self.post()
        self.assertFalse(FoodEntry.objects.exists())
        self.assertFalse(DailyEntry.objects.exists())

    def test_cannot_log_someone_elses_custom_food(self):
        secret = make_food("Secret", "snacks", 200, 5, 20, 10, created_by=self.other, source="User-submitted")
        r = self.post(items=[{"food_item": self.rice.id, "servings": 1}, {"food_item": secret.id, "servings": 1}])
        self.assertEqual(r.status_code, 404)
        self.assertFalse(FoodEntry.objects.exists())

    def test_can_log_your_own_custom_food(self):
        mine = make_food("Mine", "snacks", 200, 5, 20, 10, created_by=self.user, source="User-submitted")
        self.assertEqual(self.post(items=[{"food_item": mine.id, "servings": 1}]).status_code, 201)

    def test_requires_auth(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.post().status_code, 401)


class FoodVisibilityTests(PlateTestBase):
    """Private custom foods can't be logged or swapped in by guessing their id."""

    def setUp(self):
        super().setUp()
        self.secret = make_food("Secret", "snacks", 200, 5, 20, 10, created_by=self.other, source="User-submitted")

    def test_single_log_of_someone_elses_food_is_refused(self):
        r = self.client.post(
            "/nutrition/entries/", {"food_item": self.secret.id, "meal_type": "lunch", "servings": 1}, format="json"
        )
        self.assertEqual(r.status_code, 404)
        self.assertFalse(FoodEntry.objects.exists())

    def test_swapping_an_entry_to_someone_elses_food_is_refused(self):
        entry = log(self.user, self.rice)
        r = self.client.patch(f"/nutrition/entries/{entry.id}/", {"food_item": self.secret.id}, format="json")
        self.assertEqual(r.status_code, 404)
        entry.refresh_from_db()
        self.assertEqual(entry.food_item_id, self.rice.id)

    def test_logging_shared_and_own_foods_still_works(self):
        mine = make_food("Mine", "snacks", 200, 5, 20, 10, created_by=self.user, source="User-submitted")
        for food in (self.rice, mine):
            r = self.client.post(
                "/nutrition/entries/", {"food_item": food.id, "meal_type": "lunch", "servings": 1}, format="json"
            )
            self.assertEqual(r.status_code, 201)
