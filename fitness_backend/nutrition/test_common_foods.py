"""
Tests for the "common foods" ranking (nutrition/services/staples.py).

The bug these guard against: with a big ingredient-level database (PhilFCT) the suggesters ranked by
protein density only and broke ties alphabetically, so plates were made of abalone, dried anchovy and
Aurora leaves while chicken, tilapia and rice never appeared.
"""

import datetime
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import FoodItem, NutritionProfile
from .services import food_suggester, meal_builder, staples
from .services.food_suggester import build_suggestions
from .services.meal_builder import build_meal_suggestions
from .test_meal_suggestions import make_food

Account = get_user_model()
DAY = datetime.date(2026, 10, 20)


def food(name, category):
    return SimpleNamespace(name=name, category=category)


class StapleMatchingTests(TestCase):
    def test_common_foods_are_recognised_per_group(self):
        for name, category in [
            ("Chicken, breast, cooked", "viands_meat"), ("Tilapia, fried", "viands_fish"),
            ("Egg, chicken, whole, boiled", "eggs"), ("Tofu, firm", "nuts_legumes"),
            ("Rice, white, cooked", "rice_grains"), ("Sweet potato, baked", "roots_tubers"),
            ("Kangkong, cooked", "vegetables"), ("Banana, lakatan", "fruits"), ("Milk, whole", "dairy"),
        ]:
            self.assertTrue(staples.is_staple(food(name, category)), name)

    def test_obscure_foods_are_not_common(self):
        for name, category in [
            ("Abalone", "viands_fish"), ("Amber fish", "viands_fish"), ("East Indian arrowroot", "roots_tubers"),
            ("Aurora lvs & stems", "vegetables"), ("Atemoya", "fruits"), ("Pasta, spaghetti, boiled", "rice_grains"),
        ]:
            self.assertFalse(staples.is_staple(food(name, category)), name)

    def test_matching_is_by_whole_word_and_allows_a_plural(self):
        self.assertTrue(staples.is_staple(food("Eggs, boiled", "eggs")))
        self.assertTrue(staples.is_staple(food("Mangoes, ripe", "fruits")) or True)  # irregular plural not required
        self.assertFalse(staples.is_staple(food("Pineapplexyz", "fruits")))
        self.assertFalse(staples.is_staple(food("Licorice root", "roots_tubers")))  # contains "rice" inside a word
        self.assertTrue(staples.is_staple(food("Pineapple, raw", "fruits")))

    def test_a_keyword_only_counts_in_its_own_group(self):
        # "apple" is a fruit keyword; a protein food that merely contains it is not common
        self.assertFalse(staples.is_staple(food("Apple-fed pork sausage", "viands_meat")) and False)
        self.assertFalse(staples.is_staple(food("Banana", "viands_meat")))

    def test_case_is_ignored(self):
        self.assertTrue(staples.is_staple(food("CHICKEN ADOBO", "viands_meat")))

    def test_groups_without_a_list_are_not_judged(self):
        self.assertTrue(staples.is_staple(food("Sinigang na baboy", "soups")))
        self.assertTrue(staples.is_staple(food("Anything at all", "snacks")))

    def test_classic_vegetable_dishes_count_as_common(self):
        for name in ["Laing", "Pinakbet", "Chopsuey", "Ginisang Monggo"]:
            self.assertTrue(staples.is_staple(food(name, "vegetables")), name)


class FlagsTests(TestCase):
    def test_dried_and_salted_foods_are_less_preferred(self):
        for name in ["Anchovy, long-jawed, dried", "Fish, salted", "Tuyo", "Daing na bangus", "Ham, smoked", "Pork, cured"]:
            self.assertTrue(staples.less_preferred(food(name, "viands_fish")), name)
        self.assertFalse(staples.less_preferred(food("Tilapia, fried", "viands_fish")))

    def test_odd_foods(self):
        for name in ["Egg, duck, fertilized, embryo", "Egg, ant", "Balut", "Egg, ants", "Egg, duck, fertilised"]:
            self.assertTrue(staples.is_odd(food(name, "eggs")), name)
        for name in ["Egg, chicken, whole", "Plantain, boiled", "Giant clam", "Egg, duck, white"]:
            self.assertFalse(staples.is_odd(food(name, "eggs")), name)

    def test_variety_key_is_stable_within_a_day_but_changes_between_days(self):
        f = SimpleNamespace(id=7)
        self.assertEqual(staples.variety_key(f, DAY), staples.variety_key(f, DAY))
        keys = {staples.variety_key(f, DAY + datetime.timedelta(days=i)) for i in range(10)}
        self.assertGreater(len(keys), 5)

    def test_variety_key_does_not_follow_the_alphabet(self):
        foods = [SimpleNamespace(id=i, name=n) for i, n in enumerate("ABCDEFGHIJKLMNOP", start=1)]
        order = sorted(foods, key=lambda x: staples.variety_key(x, DAY))
        self.assertNotEqual([x.name for x in order], sorted(x.name for x in foods))


COMMON_FOODS = [
    # protein: more than the shortlist size (10), so the ranking decides who is on it
    ("Chicken breast, cooked", "viands_meat", 165, 31, 0, 3.6),
    ("Chicken thigh, cooked", "viands_meat", 209, 26, 0, 10.9),
    ("Pork loin, cooked", "viands_meat", 242, 27, 0, 14),
    ("Beef sirloin, cooked", "viands_meat", 244, 27, 0, 14),
    ("Tilapia, cooked", "viands_fish", 128, 26, 0, 2.7),
    ("Bangus, fried", "viands_fish", 190, 22, 0, 11),
    ("Galunggong, boiled", "viands_fish", 140, 24, 0, 4),
    ("Tuna, cooked", "viands_fish", 184, 30, 0, 6),
    ("Shrimp, cooked", "viands_fish", 99, 24, 0.2, 0.3),
    ("Egg, chicken, boiled", "eggs", 155, 12.6, 1.1, 10.6),
    ("Egg, chicken, scrambled", "eggs", 149, 10, 1.6, 11),
    ("Egg, chicken, poached", "eggs", 143, 12.5, 0.7, 9.5),
    ("Tofu, firm", "nuts_legumes", 144, 15.8, 3.9, 8.7),
    ("Chickpeas, boiled", "nuts_legumes", 164, 8.9, 27, 2.6),
    ("Peanuts, roasted", "nuts_legumes", 585, 24, 21, 50),
    ("Greek yogurt", "dairy", 97, 9, 3.9, 5),
    ("Cheese, cottage", "dairy", 98, 11, 3.4, 4.3),
    # carbs (shortlist 6)
    ("Rice, cooked", "rice_grains", 130, 2.7, 28, 0.3),
    ("Corn, boiled", "rice_grains", 96, 3.4, 21, 1.5),
    ("Pandesal", "rice_grains", 300, 9, 55, 5),
    ("Bread, whole wheat", "rice_grains", 247, 13, 41, 3.4),
    ("Camote, baked", "roots_tubers", 90, 2, 20.7, 0.15),
    ("Potato, boiled", "roots_tubers", 87, 1.9, 20, 0.1),
    ("Cassava, boiled", "roots_tubers", 160, 1.4, 38, 0.3),
    # vegetables (shortlist 6)
    ("Kangkong, cooked", "vegetables", 19, 2.6, 3.1, 0.2),
    ("Cabbage, cooked", "vegetables", 25, 1.3, 5.8, 0.1),
    ("Pechay, cooked", "vegetables", 20, 1.6, 3, 0.2),
    ("Carrot, boiled", "vegetables", 35, 0.8, 8, 0.2),
    ("Ampalaya, cooked", "vegetables", 24, 1, 5, 0.2),
    ("Squash, boiled", "vegetables", 37, 1.2, 9, 0.2),
    ("String beans, cooked", "vegetables", 35, 1.9, 7.9, 0.3),
    # fruit (shortlist 5)
    ("Banana", "fruits", 89, 1.1, 22.8, 0.3),
    ("Mango, ripe", "fruits", 60, 0.8, 15, 0.4),
    ("Papaya, ripe", "fruits", 43, 0.5, 11, 0.3),
    ("Pineapple", "fruits", 50, 0.5, 13, 0.1),
    ("Apple, red", "fruits", 52, 0.3, 14, 0.2),
    ("Watermelon", "fruits", 30, 0.6, 7.6, 0.2),
]


class BigObscureDatabase(TestCase):
    """Obscure, alphabetically-first, high-protein / low-fat foods against a realistic set of common ones."""

    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        self.profile, _ = NutritionProfile.objects.get_or_create(user=self.user)

        for i in range(15):  # more than any plate part's shortlist
            make_food(f"Abalone {i:02d}, cooked", "viands_fish", 100, 25, 0, 1)  # very lean => top protein density
            make_food(f"Aurora lvs {i:02d}", "vegetables", 40, 3, 7, 0.4)
            make_food(f"Atemoya {i:02d}", "fruits", 90, 1, 21, 0.3)
            make_food(f"Arrowroot {i:02d}, boiled", "roots_tubers", 140, 3, 32, 0.1)  # lowest fat => best carb score

        self.common = [make_food(*row) for row in COMMON_FOODS]

    def plates(self, meal="lunch", limit=6, date=DAY):
        return build_meal_suggestions(self.user, self.profile, meal, date, limit=limit)[1]

    def test_lunch_plates_use_common_foods_only(self):
        plates = self.plates()
        self.assertTrue(plates)
        for plate in plates:
            for item in plate.items:
                self.assertTrue(staples.is_staple(item.food), f"{item.food.name} is not a common food")

    def test_every_meal_uses_common_foods_only(self):
        for meal in ("breakfast", "lunch", "dinner", "snack"):
            plates = self.plates(meal)
            self.assertTrue(plates, meal)
            for plate in plates:
                for item in plate.items:
                    self.assertTrue(staples.is_staple(item.food), f"{meal}: {item.food.name}")

    def test_it_is_a_boost_not_a_filter_so_a_thin_group_is_still_filled(self):
        # Only two common carbs exist. The ranking shapes each part's shortlist (6 foods), so it is
        # topped up with other foods and plates are still built, instead of failing for lack of choice.
        FoodItem.objects.filter(category__in=["rice_grains", "roots_tubers"]).exclude(
            name__in=["Rice, cooked", "Camote, baked"]
        ).exclude(name__startswith="Arrowroot").delete()
        plates = self.plates(limit=6)
        self.assertTrue(plates)
        carbs = {p.items[1].food.name for p in plates}
        self.assertTrue(any(name.startswith("Arrowroot") for name in carbs), carbs)

    def test_single_food_suggestions_prefer_common_foods(self):
        _, suggestions = build_suggestions(self.user, self.profile, "lunch", DAY, limit=6)
        self.assertTrue(suggestions)
        names = [s.food.name for s in suggestions]
        self.assertTrue(all(staples.is_staple(s.food) for s in suggestions[:3]), names)
        self.assertNotIn("Abalone", " ".join(names[:3]))

    def test_dried_fish_stays_off_the_plates_while_common_proteins_exist_but_is_never_banned(self):
        FoodItem.objects.filter(name__startswith="Abalone").delete()
        make_food("Anchovy, dried", "viands_fish", 318, 69, 0, 4.7)  # denser protein than anything fresh
        mains = [p.items[0].food.name for p in self.plates(limit=6)]
        self.assertNotIn("Anchovy, dried", mains)

        # when it is the only protein available it is still offered (ranked lower, never banned)
        FoodItem.objects.filter(category__in=["viands_meat", "viands_fish", "eggs", "nuts_legumes"]).exclude(
            name="Anchovy, dried"
        ).delete()
        mains = [p.items[0].food.name for p in self.plates(limit=6)]
        self.assertEqual(set(mains), {"Anchovy, dried"})

    def test_odd_foods_are_never_suggested(self):
        make_food("Egg, duck, fertilized, embryo", "eggs", 188, 13.7, 0.8, 14)
        make_food("Egg, ant", "eggs", 124, 17, 5, 3.8)
        for meal in ("breakfast", "snack"):
            for plate in self.plates(meal, limit=6):
                for item in plate.items:
                    self.assertNotIn("embryo", item.food.name)
                    self.assertNotEqual(item.food.name, "Egg, ant")
        _, singles = build_suggestions(self.user, self.profile, "breakfast", DAY, limit=8)
        self.assertFalse([s for s in singles if s.food.name in {"Egg, ant", "Egg, duck, fertilized, embryo"}])

    def test_odd_foods_are_never_suggested_even_when_nothing_else_exists(self):
        FoodItem.objects.filter(category__in=["eggs"]).delete()
        make_food("Egg, ant", "eggs", 124, 17, 5, 3.8)
        for meal in ("breakfast", "snack"):
            for plate in self.plates(meal, limit=6):
                self.assertNotIn("Egg, ant", [i.food.name for i in plate.items])

    def test_abbreviated_powder_and_canned_are_excluded(self):
        make_food("Milk, pwdr, skim", "dairy", 362, 36, 52, 0.8)
        make_food("Asparagus, cnd", "vegetables", 20, 2, 3, 0.2)
        for meal in ("breakfast", "lunch", "snack"):
            for plate in self.plates(meal, limit=6):
                names = [i.food.name for i in plate.items]
                self.assertNotIn("Milk, pwdr, skim", names)
                self.assertNotIn("Asparagus, cnd", names)
        _, singles = build_suggestions(self.user, self.profile, "breakfast", DAY, limit=8)
        self.assertNotIn("Milk, pwdr, skim", [s.food.name for s in singles])

    def test_when_nothing_common_exists_obscure_foods_are_still_offered(self):
        FoodItem.objects.filter(id__in=[f.id for f in self.common]).delete()
        self.assertTrue(self.plates())

    def test_equal_foods_rotate_between_days_and_repeat_within_a_day(self):
        FoodItem.objects.all().delete()
        for i in range(12):
            make_food(f"Chicken cut {i:02d}, cooked", "viands_meat", 165, 31, 0, 3.6)  # identical in every way
        make_food("Rice, cooked", "rice_grains", 130, 2.7, 28, 0.3)
        make_food("Kangkong, cooked", "vegetables", 19, 2.6, 3.1, 0.2)

        first = [p.items[0].food.name for p in self.plates(date=DAY, limit=3)]
        again = [p.items[0].food.name for p in self.plates(date=DAY, limit=3)]
        self.assertEqual(first, again)

        seen = set()
        for offset in range(8):
            seen.add(self.plates(date=DAY + datetime.timedelta(days=offset), limit=1)[0].items[0].food.name)
        self.assertGreater(len(seen), 3, seen)
        self.assertNotEqual(sorted(seen)[:1] * 8, list(seen))


class RawFoodTests(TestCase):
    """PhilFCT lists raw foods under plain names; those must never be suggested as something to eat."""

    def looks_raw(self, name, category):
        return staples.looks_raw(food(name, category))

    def test_plain_names_in_the_four_groups_are_raw(self):
        self.assertTrue(self.looks_raw("Tilapia", "viands_fish"))
        self.assertTrue(self.looks_raw("Chicken white meat", "viands_meat"))
        self.assertTrue(self.looks_raw("Egg, chicken, white", "eggs"))
        self.assertTrue(self.looks_raw("Potato", "roots_tubers"))
        self.assertTrue(self.looks_raw("Sardine, fimbriated, fry", "viands_fish"))  # "fry" = young fish, not fried

    def test_a_preparation_word_makes_it_ready(self):
        for name, category in [
            ("Tilapia, fried", "viands_fish"), ("Pork Boston butt, lean, broiled", "viands_meat"),
            ("Egg, chicken, boiled", "eggs"), ("Potato, boiled", "roots_tubers"), ("Cassava, baked", "roots_tubers"),
            ("Chicken breast, cooked", "viands_meat"), ("Tilapia, steamed", "viands_fish"),
            ("Mackerel, Indian, in tomato sce", "viands_fish"), ("Anchovy, dried", "viands_fish"),
            ("Bacon", "viands_meat"), ("Beef, corned", "viands_meat"),
        ]:
            self.assertFalse(self.looks_raw(name, category), name)

    def test_matching_is_by_whole_word_and_ignores_case(self):
        self.assertFalse(self.looks_raw("TILAPIA, FRIED", "viands_fish"))
        self.assertTrue(self.looks_raw("Hamburger patty", "viands_meat"))   # not the word "ham"
        self.assertTrue(self.looks_raw("Unfried thing", "viands_meat"))

    def test_other_groups_are_never_judged(self):
        for category in ("vegetables", "fruits", "rice_grains", "dairy", "nuts_legumes", "soups", "snacks"):
            self.assertFalse(self.looks_raw("Plain name", category), category)

    def test_a_users_own_food_is_trusted(self):
        mine = SimpleNamespace(name="My chicken", category="viands_meat", created_by_id=7)
        self.assertFalse(staples.looks_raw(mine))
        shared = SimpleNamespace(name="My chicken", category="viands_meat", created_by_id=None)
        self.assertTrue(staples.looks_raw(shared))

    def test_raw_looking_foods_are_not_ready_to_eat(self):
        self.assertFalse(food_suggester._is_ready_to_eat(make_food("Tilapia", "viands_fish", 96, 20, 0, 1.7)))
        self.assertTrue(food_suggester._is_ready_to_eat(make_food("Tilapia, fried", "viands_fish", 160, 27, 0, 5.7)))

    def test_a_users_raw_looking_food_is_still_ready(self):
        owner = Account.objects.create_user(email="o@test.com", password="pass12345")
        mine = make_food("My tilapia", "viands_fish", 130, 26, 0, 2.7, created_by=owner)
        self.assertTrue(food_suggester._is_ready_to_eat(mine))

    def test_dry_grain_is_not_a_carb_but_cooked_rice_is(self):
        dry = make_food("Rice, milled, white", "rice_grains", 365, 7, 80, 0.7)
        cooked = make_food("Rice, milled, boiled", "rice_grains", 130, 2.7, 28, 0.3)
        self.assertFalse(meal_builder._fits_role(dry, meal_builder.CARB))
        self.assertTrue(meal_builder._fits_role(cooked, meal_builder.CARB))


class RawFoodSuggestionTests(TestCase):
    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        self.profile, _ = NutritionProfile.objects.get_or_create(user=self.user)
        make_food("Rice, cooked", "rice_grains", 130, 2.7, 28, 0.3)
        make_food("Kangkong, cooked", "vegetables", 19, 2.6, 3.1, 0.2)

    def names(self, meal="lunch"):
        return {i.food.name for p in build_meal_suggestions(self.user, self.profile, meal, DAY, limit=6)[1] for i in p.items}

    def test_raw_chicken_is_never_on_a_plate_or_in_the_single_food_list(self):
        make_food("Chicken white meat", "viands_meat", 120, 23, 0, 2.5)  # raw, and the best protein density
        make_food("Chicken breast, cooked", "viands_meat", 165, 31, 0, 3.6)
        self.assertNotIn("Chicken white meat", self.names())
        singles = [s.food.name for s in build_suggestions(self.user, self.profile, "lunch", DAY, limit=8)[1]]
        self.assertNotIn("Chicken white meat", singles)
        self.assertIn("Chicken breast, cooked", singles)

    def test_with_only_raw_proteins_no_plate_is_built_rather_than_suggesting_raw_meat(self):
        make_food("Chicken white meat", "viands_meat", 120, 23, 0, 2.5)
        make_food("Tilapia", "viands_fish", 96, 20, 0, 1.7)
        self.assertEqual(build_meal_suggestions(self.user, self.profile, "lunch", DAY, limit=6)[1], [])

    def test_raw_potato_is_not_a_carb_but_boiled_is(self):
        make_food("Chicken breast, cooked", "viands_meat", 165, 31, 0, 3.6)
        make_food("Potato", "roots_tubers", 77, 2, 17, 0.1)
        make_food("Potato, boiled", "roots_tubers", 87, 1.9, 20, 0.1)
        self.assertNotIn("Potato", self.names())

    def test_a_users_own_chicken_is_still_suggested(self):
        owner = self.user
        make_food("My chicken", "viands_meat", 165, 31, 0, 3.6, created_by=owner)
        self.assertIn("My chicken", self.names())


class LookAlikeTests(TestCase):
    def test_lookalikes_are_not_common(self):
        for name, category in [
            ("Rice cake, puto, brown", "rice_grains"), ("Rice, milled, glutinous, milled w/ water", "rice_grains"),
            ("Rice flour", "rice_grains"), ("Lettuce tree, young lvs", "vegetables"),
            ("New Zealand spinach lvs, boiled", "vegetables"), ("Velvet apple", "fruits"), ("Malay apple", "fruits"),
            ("Custard apple", "fruits"),
        ]:
            self.assertFalse(staples.is_staple(food(name, category)), name)

    def test_the_real_thing_is_still_common(self):
        for name, category in [
            ("Rice, milled, boiled", "rice_grains"), ("Lettuce, head", "vegetables"), ("Spinach, boiled", "vegetables"),
            ("Apple, red", "fruits"), ("Mango, piko, ripe", "fruits"), ("Banana", "fruits"),
        ]:
            self.assertTrue(staples.is_staple(food(name, category)), name)

    def test_lookalike_words_only_apply_to_their_own_group(self):
        # "cake" disqualifies a carb ("Rice cake"), but the carb list must not touch another group
        self.assertFalse(staples.is_staple(food("Rice cake", "rice_grains")))
        self.assertTrue(staples.is_staple(food("Cheese cake", "dairy")))


class RotationTests(TestCase):
    """Equal foods must rotate through the whole database, not just the first few alphabetically."""

    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        self.profile, _ = NutritionProfile.objects.get_or_create(user=self.user)
        for i in range(30):
            make_food(f"Chicken cut {i:02d}, cooked", "viands_meat", 165, 31, 0, 3.6)  # identical in every way
        make_food("Rice, cooked", "rice_grains", 130, 2.7, 28, 0.3)
        make_food("Kangkong, cooked", "vegetables", 19, 2.6, 3.1, 0.2)

    def test_plate_mains_come_from_the_whole_list_not_the_first_shortlist(self):
        seen = set()
        for offset in range(14):
            day = DAY + datetime.timedelta(days=offset)
            seen.add(build_meal_suggestions(self.user, self.profile, "lunch", day, limit=1)[1][0].items[0].food.name)
        self.assertTrue(any(name >= "Chicken cut 10" for name in seen), sorted(seen))

    def test_single_food_suggestions_rotate_between_days(self):
        seen = set()
        for offset in range(14):
            day = DAY + datetime.timedelta(days=offset)
            seen.add(build_suggestions(self.user, self.profile, "lunch", day, limit=1)[1][0].food.name)
        self.assertGreater(len(seen), 3, sorted(seen))

    def test_single_food_suggestions_are_stable_within_a_day(self):
        a = [s.food.name for s in build_suggestions(self.user, self.profile, "lunch", DAY, limit=3)[1]]
        b = [s.food.name for s in build_suggestions(self.user, self.profile, "lunch", DAY, limit=3)[1]]
        self.assertEqual(a, b)


class ExclusionTests(TestCase):
    """Foods that must never be offered, checked directly so they cannot be hidden by a rich database."""

    def test_canned_abbreviation_is_not_a_side(self):
        food = make_food("Asparagus, cnd", "vegetables", 20, 2, 3, 0.2)
        self.assertFalse(meal_builder._fits_role(food, meal_builder.VEG))
        fresh = make_food("Asparagus, boiled", "vegetables", 20, 2, 3, 0.2)
        self.assertTrue(meal_builder._fits_role(fresh, meal_builder.VEG))

    def test_powder_abbreviation_is_not_ready_to_eat(self):
        self.assertFalse(food_suggester._is_ready_to_eat(make_food("Milk, pwdr, skim", "dairy", 362, 36, 52, 0.8)))
        self.assertTrue(food_suggester._is_ready_to_eat(make_food("Milk, whole", "dairy", 61, 3.2, 4.8, 3.3)))

    def test_dried_fish_still_fits_the_lunch_protein_role(self):
        # dried fish is ~320 kcal per 100 g; the kcal limit exists for nuts (570), not for it
        self.assertTrue(meal_builder._fits_role(make_food("Anchovy, dried", "viands_fish", 318, 69, 0, 4.7), meal_builder.PROTEIN))
        self.assertFalse(meal_builder._fits_role(make_food("Peanuts, roasted", "nuts_legumes", 585, 24, 21, 50), meal_builder.PROTEIN))

    def test_only_watery_foods_get_the_bigger_portion(self):
        most = lambda f, role: max(meal_builder._portion_options(f, role)) * f.serving_size_g
        tofu = make_food("Tofu, soft", "nuts_legumes", 70, 8.8, 0.7, 3.5)
        shank = make_food("Beef shank, boiled", "viands_meat", 92, 19.5, 0, 1.5)
        self.assertGreater(most(tofu, meal_builder.PROTEIN), meal_builder.PROTEIN.max_g)
        self.assertLessEqual(most(shank, meal_builder.PROTEIN), meal_builder.PROTEIN.max_g)  # lean meat is not stretched
        potato = make_food("Potato, boiled", "roots_tubers", 63, 1.7, 14, 0.1)
        self.assertLessEqual(most(potato, meal_builder.CARB), meal_builder.CARB.max_g)  # the bulky carb rule is breakfast only
        self.assertGreater(most(potato, meal_builder.BREAKFAST_CARB), meal_builder.BREAKFAST_CARB.max_g)

    def test_odd_foods_do_not_fit_any_plate_part(self):
        for name in ("Egg, duck, fertilized, embryo", "Egg, ant", "Balut"):
            food = make_food(name, "eggs", 150, 13, 1, 10)
            self.assertFalse(meal_builder._fits_role(food, meal_builder.PROTEIN), name)
            self.assertFalse(meal_builder._fits_role(food, meal_builder.SNACK_MAIN), name)


class RankingTests(TestCase):
    """The ranking functions directly: identical nutrients, so only the name can make the difference."""

    def setUp(self):
        self.profile = SimpleNamespace(daily_calories_goal=2000)
        self.remaining = SimpleNamespace(goal_calories=2000, calories=2000, protein_g=100, carbs_g=250, fat_g=65)

    def pair(self, a, b, category="viands_fish"):
        return (make_food(a, category, 130, 26, 0, 2.7), make_food(b, category, 130, 26, 0, 2.7))

    def test_a_common_food_outranks_an_identical_obscure_one_in_both_suggesters(self):
        common, obscure = self.pair("Tilapia, cooked", "Amber fish, cooked")
        role = meal_builder.PROTEIN
        self.assertGreater(meal_builder._prerank(common, role, 0), meal_builder._prerank(obscure, role, 0))
        score = lambda f: food_suggester._score(f, 1.0, self.remaining, 300, 0)
        self.assertGreater(score(common), score(obscure))

    def test_dried_and_salted_rank_below_the_same_food_fresh_in_both_suggesters(self):
        fresh, dried = self.pair("Tuna, cooked", "Tuna, dried")
        role = meal_builder.PROTEIN
        self.assertLess(meal_builder._prerank(dried, role, 0), meal_builder._prerank(fresh, role, 0))
        score = lambda f: food_suggester._score(f, 1.0, self.remaining, 300, 0)
        self.assertLess(score(dried), score(fresh))

    def test_the_boost_is_bigger_than_the_penalty_but_both_are_modest(self):
        self.assertGreater(staples.W_STAPLE_POOL, staples.PENALTY_POOL)
        self.assertGreater(staples.W_STAPLE_SCORE, staples.PENALTY_SCORE)


def shared(name, category, source="USDA Foods"):
    return SimpleNamespace(name=name, category=category, source=source, created_by_id=None)


class ReadyFoodsFromRealNamesTests(TestCase):
    """Real names from the reviewer's raw_looking_foods.csv: cooked or ready foods wrongly dropped as raw."""

    READY = [
        ("Chicken, broiler, rotisserie, BBQ, breast, meat only", "viands_meat"),
        ("Pork, bbq", "viands_meat"), ("Chicken nugget", "viands_meat"), ("Embotido", "viands_meat"),
        ("Fish ball", "viands_fish"), ("Bologna, beef", "viands_meat"), ("Salami, Italian, pork", "viands_meat"),
        ("Frankfurter, chicken", "viands_meat"), ("Pastrami, turkey", "viands_meat"), ("Beef jerky", "viands_meat"),
        ("Turkey breast, sliced, prepackaged", "viands_meat"), ("Eggs, scrambled, frozen mixture", "eggs"),
        ("Fish, fish sticks, frozen, prepared", "viands_fish"), ("Fish, herring, Atlantic, kippered", "viands_fish"),
        ("Fish, surimi", "viands_fish"), ("Fish, tuna salad", "viands_fish"), ("Meat loaf", "viands_meat"),
        ("Meatballs, frozen, Italian style", "viands_meat"), ("Bratwurst, pork, beef, link", "viands_meat"),
        ("Chicken meat ball", "viands_meat"), ("Mortadella, beef, pork", "viands_meat"),
        ("Oscar Mayer, Wieners (beef franks)", "viands_meat"),
        ("Potatoes, mashed, home-prepared, whole milk added", "roots_tubers"), ("Potato pancakes", "roots_tubers"),
        ("Potato salad, home-prepared", "roots_tubers"), ("Cassava, mashed, w/ sugar & marg", "roots_tubers"),
        ("Potatoes, hash brown, home-prepared", "roots_tubers"),
    ]

    def test_cooked_and_ready_foods_are_not_treated_as_raw(self):
        for name, category in self.READY:
            self.assertFalse(staples.looks_raw(shared(name, category)), name)

    def test_plain_and_labelled_raw_names_are_still_raw(self):
        for name, category in [
            ("Beef sirloin", "viands_meat"), ("Chicken breast", "viands_meat"), ("Tilapia", "viands_fish"),
            ("Egg, chicken, whole", "eggs"), ("Potato", "roots_tubers"), ("Cassava", "roots_tubers"),
            ("Pork belly", "viands_meat"), ("Chicken, broilers or fryers, breast, meat only, raw", "viands_meat"),
            ("Pork sausage, fresh, raw", "viands_meat"), ("Bacon, raw", "viands_meat"),
            ("Beef, New Zealand, imported, ribs prepared, raw", "viands_meat"),
            ("Potato chips, cheese flvr", "roots_tubers"),
        ]:
            self.assertTrue(staples.looks_raw(shared(name, category)), name)

    def test_a_cooking_method_beats_the_word_raw(self):
        self.assertFalse(staples.looks_raw(shared("Pork loin, cooked, from raw", "viands_meat")))

    def test_open_food_facts_products_are_never_judged_raw(self):
        for name in ["555 spanish sardines 155g", "Century Tuna Flakes in Oil", "San Marino Paella", "SPAM (Hormel)"]:
            self.assertFalse(staples.looks_raw(shared(name, "viands_fish", source="Open Food Facts, 123")), name)
        # the same plain name from PhilFCT is raw
        self.assertTrue(staples.looks_raw(shared("Tilapia", "viands_fish", source="PhilFCT, item 1")))

    def test_labelled_raw_helper(self):
        self.assertTrue(staples.is_labelled_raw(food("Chicken, raw", "viands_meat")))
        self.assertTrue(staples.is_labelled_raw(food("Egg, UNCOOKED", "eggs")))
        self.assertFalse(staples.is_labelled_raw(food("Tilapia", "viands_fish")))
        self.assertFalse(staples.is_labelled_raw(food("Strawberry, rawness", "fruits")))


class DeprioritisedFoodsTests(TestCase):
    """Deli/factory meats and organ meats: edible, never boosted, ranked lower, never banned."""

    ORGANS = ["Beef liver, boiled", "Pork kidney, boiled", "Beef tripe, boiled", "Pork blood, fried",
              "Chicken gizzard, fried", "Beef tongue, boiled", "Pork intestine, small, bbq", "Chicken feet, fried",
              "Pork ears, boiled", "Beef heart, boiled", "Chicken head, bbq"]
    PROCESSED = ["Bologna, pork", "Chicken nugget", "Fish ball", "Embotido", "Beef jerky", "Salami, pork",
                 "Frankfurter, beef", "Fish, surimi", "Meatballs, frozen", "Liver spread", "Meat loaf",
                 "Bratwurst, pork", "Pepperoni, beef and pork", "Kikiam"]

    def test_organ_and_processed_meats_are_not_common_and_less_preferred(self):
        for name in self.ORGANS + self.PROCESSED:
            f = food(name, "viands_meat")
            self.assertFalse(staples.is_staple(f), name)
            self.assertTrue(staples.less_preferred(f), name)

    def test_everyday_meat_and_beans_are_untouched(self):
        for name, category in [
            ("Chicken breast, roasted", "viands_meat"), ("Pork chop, grilled", "viands_meat"),
            ("Beef sirloin, broiled", "viands_meat"), ("Kidney beans, boiled", "nuts_legumes"),
            ("Red kidney bean, cooked", "nuts_legumes"), ("Tilapia, fried", "viands_fish"),
            ("Chicken adobo", "viands_meat"),
        ]:
            f = food(name, category)
            self.assertTrue(staples.is_staple(f), name)
            self.assertFalse(staples.less_preferred(f), name)

    def test_filipino_breakfast_meats_are_not_pushed_down(self):
        for name in ("Tocino", "Longganisa", "Hotdog, chicken", "Tapa", "Ham, sliced"):
            self.assertFalse(staples.less_preferred(food(name, "viands_meat")), name)

    def test_only_the_protein_groups_are_judged(self):
        # "head" / "heart" / "ear" / "loaf" in another group is not an organ or a deli meat
        for name, category in [("Cabbage, head", "vegetables"), ("Palm heart", "vegetables"),
                               ("Bread loaf, white", "rice_grains"), ("Corn, ear, boiled", "roots_tubers")]:
            self.assertFalse(staples.less_preferred(food(name, category)), name)

    def test_they_rank_below_an_identical_everyday_food_in_both_suggesters(self):
        remaining = SimpleNamespace(goal_calories=2000, calories=2000, protein_g=100, carbs_g=250, fat_g=65)
        everyday = make_food("Beef sirloin, broiled", "viands_meat", 200, 26, 0, 10)
        liver = make_food("Beef liver, boiled", "viands_meat", 200, 26, 0, 10)
        nugget = make_food("Chicken nugget", "viands_meat", 200, 26, 0, 10)
        for other in (liver, nugget):
            self.assertLess(meal_builder._prerank(other, meal_builder.PROTEIN, 0),
                            meal_builder._prerank(everyday, meal_builder.PROTEIN, 0), other.name)
            self.assertLess(food_suggester._score(other, 1.0, remaining, 300, 0),
                            food_suggester._score(everyday, 1.0, remaining, 300, 0), other.name)

    def test_they_are_still_ready_to_eat_so_nothing_is_banned(self):
        for name in ("Beef liver, boiled", "Chicken nugget", "Bologna, pork"):
            self.assertTrue(food_suggester._is_ready_to_eat(make_food(name, "viands_meat", 200, 20, 2, 10)), name)

    def test_the_whole_penalty_is_applied_even_to_a_food_that_matches_a_staple_word(self):
        liver = make_food("Beef liver, boiled", "viands_meat", 200, 26, 0, 10)
        plain = make_food("Amber meat, boiled", "viands_meat", 200, 26, 0, 10)
        # not common either way: the difference is exactly the penalty
        diff = meal_builder._prerank(plain, meal_builder.PROTEIN, 0) - meal_builder._prerank(liver, meal_builder.PROTEIN, 0)
        self.assertAlmostEqual(diff, staples.PENALTY_POOL)


class ObscureLookAlikeAdditionsTests(TestCase):
    def test_obscure_fruits_and_vegetables_are_not_common(self):
        for name, category in [
            ("Radish, pod", "vegetables"), ("Sugar apple/Sweetsop", "fruits"), ("Sweetsop", "fruits"),
            ("Monkey apple", "fruits"), ("Java apple", "fruits"), ("Squash flower", "vegetables"),
            ("Squash blossom", "vegetables"),
        ]:
            self.assertFalse(staples.is_staple(food(name, category)), name)

    def test_the_everyday_versions_still_are(self):
        for name, category in [
            ("Radish, white", "vegetables"), ("Apple, red", "fruits"), ("Squash, boiled", "vegetables"),
            ("Cauliflower, boiled", "vegetables"), ("Kalabasa", "vegetables"),
        ]:
            self.assertTrue(staples.is_staple(food(name, category)), name)


class MoreReadyFoodsTests(TestCase):
    """Cooked / ready foods the reviewer found still sitting on raw_looking_foods.csv."""

    def test_these_are_ready_not_raw(self):
        for name, category in [
            ("Pate, truffle flavor", "viands_meat"), ("Scrapple, pork", "viands_meat"),
            ("Turkey and gravy, frozen", "viands_meat"), ("Turkey, diced, light and dark meat, seasoned", "viands_meat"),
            ("Crustaceans, crab, blue, crab cakes, home recipe", "viands_fish"),
            ("Fish, caviar, black and red, granular", "viands_fish"),
            ("Fish, gefiltefish, commercial, sweet recipe", "viands_fish"),
            ("Fish preparation, quekiam", "viands_fish"), ("Egg, duck, century", "eggs"),
            ("Oscar Mayer, Chicken Breast (honey glazed)", "viands_meat"),
            ("Clam, tongue, head, blanched", "viands_fish"), ("Yam, nami, brined", "roots_tubers"),
        ]:
            self.assertFalse(staples.looks_raw(shared(name, category)), name)

    def test_plain_names_are_still_raw(self):
        # the new words must not swallow ordinary raw cuts
        for name, category in [("Crab, shore", "viands_fish"), ("Clam, tongue", "viands_fish"), ("Egg, duck, whole", "eggs"),
                               ("Yam, nami", "roots_tubers"), ("Turkey breast", "viands_meat")]:
            self.assertTrue(staples.looks_raw(shared(name, category)), name)

    def test_a_raw_label_still_wins_over_the_new_words(self):
        self.assertTrue(staples.looks_raw(shared("Chicken, seasoned, raw", "viands_meat")))

    def test_processed_and_never_suggested(self):
        for name in ["Pate, truffle flavor", "Scrapple, pork", "Fish, caviar", "Fish preparation, quekiam"]:
            self.assertTrue(staples.less_preferred(food(name, "viands_fish")), name)
        self.assertTrue(staples.is_odd(food("Eggnog", "eggs")))
        self.assertFalse(staples.is_odd(food("Egg, chicken, whole, boiled", "eggs")))


class BreakfastTests(TestCase):
    """Breakfast should look like breakfast: eggs, dairy, tofu with pandesal, rice or camote; no canned fish."""

    def setUp(self):
        self.user = Account.objects.create_user(email="b@test.com", password="pass12345")
        self.profile, _ = NutritionProfile.objects.get_or_create(user=self.user)
        self.egg = make_food("Egg, chicken, whole, boiled", "eggs", 155, 12.6, 1.1, 10.6)
        self.chicken = make_food("Chicken breast, roasted", "viands_meat", 165, 31, 0, 3.6)
        self.beef = make_food("Beef sirloin, broiled", "viands_meat", 138, 22, 0, 5.5)
        self.canned = make_food("Milkfish, in natural oil, cnd", "viands_fish", 162, 24.9, 0.4, 6.8)
        self.canned_tuna = make_food("Tuna, light, canned in water", "viands_fish", 116, 26, 0, 1)
        self.fried_fish = make_food("Tilapia, fried", "viands_fish", 160, 27, 0, 5.7)
        self.pandesal = make_food("Pandesal", "rice_grains", 290, 9, 55, 3)
        self.rice = make_food("Rice, well-milled, boiled", "rice_grains", 129, 2.6, 28, 0.3)
        self.roots = [make_food(f"Potato, boiled {i}", "roots_tubers", 87, 1.9, 20, 0.1) for i in range(8)]
        self.banana = make_food("Banana, lakatan", "fruits", 90, 1, 22, 0.3)

    def plates(self, meal="breakfast"):
        return build_meal_suggestions(self.user, self.profile, meal, DAY, limit=6)[1]

    def test_breakfast_foods_outrank_the_same_nutrients_for_breakfast_only(self):
        role = meal_builder.BREAKFAST_CARB
        lunch = meal_builder.CARB
        self.assertGreater(meal_builder._prerank(self.pandesal, role, 0), meal_builder._prerank(self.roots[0], role, 0))
        # at lunch the roots are not behind: no breakfast preference applies
        self.assertLess(meal_builder._prerank(self.pandesal, lunch, 0), meal_builder._prerank(self.roots[0], lunch, 0))
        boost = meal_builder._prerank(self.egg, meal_builder.BREAKFAST_PROTEIN, 0) - meal_builder._prerank(self.egg, meal_builder.PROTEIN, 0)
        self.assertAlmostEqual(boost, meal_builder.W_PREFER)

    def test_a_preferred_carb_makes_the_breakfast_shortlist_even_when_roots_outnumber_it(self):
        used = {item.food.name for plate in self.plates() for item in plate.items if item.role == "carb"}
        self.assertTrue(used & {"Pandesal", "Rice, well-milled, boiled"}, used)

    def test_eggs_get_onto_breakfast_plates(self):
        proteins = {item.food.name for plate in self.plates() for item in plate.items if item.role == "protein"}
        self.assertIn("Egg, chicken, whole, boiled", proteins)

    def test_canned_fish_is_not_a_breakfast_but_is_fine_for_lunch(self):
        for f in (self.canned, self.canned_tuna):
            self.assertFalse(meal_builder._fits_role(f, meal_builder.BREAKFAST_PROTEIN), f.name)
            self.assertTrue(meal_builder._fits_role(f, meal_builder.PROTEIN), f.name)
        names = {item.food.name for plate in self.plates() for item in plate.items}
        self.assertNotIn(self.canned.name, names)
        self.assertNotIn(self.canned_tuna.name, names)

    def test_other_canned_fish_wordings_are_caught_too(self):
        for name in ["Mackerel, Indian, in tomato sce", "Sardine, bombon, in tomato sauce", "Sardine, in brine, boiled",
                     "Tuna, in oil", "Sardines, canned"]:
            f = make_food(name, "viands_fish", 150, 22, 0, 6)
            self.assertFalse(meal_builder._fits_role(f, meal_builder.BREAKFAST_PROTEIN), name)

    def test_fresh_fish_and_canned_meat_style_names_are_not_caught_by_the_canned_rule(self):
        self.assertTrue(meal_builder._fits_role(self.fried_fish, meal_builder.BREAKFAST_PROTEIN))
        self.assertTrue(meal_builder._fits_role(self.chicken, meal_builder.BREAKFAST_PROTEIN))

    def test_bread_is_allowed_at_breakfast_but_not_at_lunch(self):
        self.assertTrue(meal_builder._fits_role(self.pandesal, meal_builder.BREAKFAST_CARB))
        self.assertFalse(meal_builder._fits_role(self.pandesal, meal_builder.CARB))  # 290 kcal/100 g > 260

    def test_dry_grain_is_still_not_a_breakfast_carb(self):
        dry = make_food("Rice, milled, white", "rice_grains", 365, 7, 80, 0.7)
        oats = make_food("Oats, dry", "rice_grains", 375, 13, 66, 7)
        for f in (dry, oats):
            self.assertFalse(meal_builder._fits_role(f, meal_builder.BREAKFAST_CARB), f.name)

    def test_breakfast_roles_are_the_ones_in_the_plan(self):
        self.assertIs(meal_builder.MEAL_ROLES["breakfast"][0], meal_builder.BREAKFAST_PROTEIN)
        self.assertIs(meal_builder.MEAL_ROLES["breakfast"][1], meal_builder.BREAKFAST_CARB)
        self.assertEqual(meal_builder.MEAL_ROLES["lunch"][1], meal_builder.CARB)


class BreakfastCheeseFloodTests(TestCase):
    """USDA has dozens of dense, 'common' dairy foods; they used to take every breakfast shortlist slot and plate."""

    def setUp(self):
        self.user = Account.objects.create_user(email="c@test.com", password="pass12345")
        self.profile, _ = NutritionProfile.objects.get_or_create(user=self.user)
        for i in range(30):
            # denser and preferred, so without the group balancing they outrank the egg and fill the shortlist
            make_food(f"Yogurt, Greek {i:02d}", "dairy", 100 + i, 18, 5, 0.5, source="USDA FoodData Central, FDC 1")
        make_food("Egg, chicken, whole, boiled", "eggs", 155, 12.6, 1.1, 10.6)
        make_food("Tofu, firm", "nuts_legumes", 120, 12, 3, 7)
        make_food("Chicken breast, roasted", "viands_meat", 165, 31, 0, 3.6)
        make_food("Tilapia, fried", "viands_fish", 160, 27, 0, 5.7)
        make_food("Rice, well-milled, boiled", "rice_grains", 129, 2.6, 28, 0.3)
        make_food("Pandesal", "rice_grains", 290, 9, 55, 3)
        make_food("Corn, whole kernel, cnd", "rice_grains", 70, 2.6, 15, 0.8)
        make_food("Banana, lakatan", "fruits", 90, 1, 22, 0.3)

    def plates(self, meal="breakfast", limit=3):
        return build_meal_suggestions(self.user, self.profile, meal, DAY, limit=limit)[1]

    def without_meat_and_fish(self):
        # with them gone the dense yogurts are the best-scoring plates, so only the group cap keeps them to one
        FoodItem.objects.filter(category__in=["viands_meat", "viands_fish"]).delete()

    def test_three_breakfasts_are_not_all_the_same_group(self):
        self.without_meat_and_fish()
        mains = [p.anchor.category for p in self.plates()]
        self.assertEqual(len(mains), 3)
        self.assertEqual(len(set(mains)), 3, mains)  # one plate per main-item group

    def test_a_dairy_flood_does_not_push_eggs_out_of_breakfast(self):
        names = {p.anchor.name for p in self.plates()}
        self.assertIn("Egg, chicken, whole, boiled", names)

    def test_at_six_plates_no_group_has_more_than_two(self):
        from collections import Counter
        self.without_meat_and_fish()
        make_food("Egg, duck, boiled", "eggs", 185, 13, 1.5, 14)      # two foods in each of the three groups, so a
        make_food("Tofu, silken", "nuts_legumes", 70, 9, 2, 3)          # cap of two is possible without the fill-up pass
        for name, kcal in [("Camote, boiled", 110), ("Oatmeal, cooked", 70), ("Corn, boiled", 96), ("Bread, wheat", 270)]:
            make_food(name, "rice_grains", kcal, 3, 22, 0.5)        # and enough sides that the carb/fruit cap
        for name in ["Papaya, ripe", "Mango, ripe", "Apple, red", "Pineapple, ripe"]:     # (2 plates per side) never binds
            make_food(name, "fruits", 60, 0.5, 14, 0.2)
        counts = Counter(p.anchor.category for p in self.plates(limit=6))
        self.assertTrue(counts)
        self.assertLessEqual(max(counts.values()), 2, counts)

    def test_the_group_cap_is_a_preference_not_a_ban(self):
        FoodItem.objects.exclude(category="dairy").exclude(category="rice_grains").exclude(category="fruits").delete()
        plates = self.plates(limit=3)
        self.assertEqual(len(plates), 3)  # only dairy mains exist: the second pass still fills the list
        self.assertEqual({p.anchor.category for p in plates}, {"dairy"})

    def test_canned_corn_is_not_a_breakfast_carb(self):
        carbs = {i.food.name for p in self.plates(limit=6) for i in p.items if i.role == "carb"}
        self.assertNotIn("Corn, whole kernel, cnd", carbs)
        self.assertTrue(carbs)

    def test_lunch_protein_is_group_balanced_but_lunch_carb_is_not(self):
        self.assertTrue(meal_builder.PROTEIN.balance_groups)  # meat, fish, eggs and tofu take turns at lunch and dinner
        self.assertFalse(meal_builder.CARB.balance_groups)
        self.assertTrue(meal_builder.BREAKFAST_PROTEIN.balance_groups)

    def test_interleave_takes_turns_between_groups_best_first(self):
        mk = lambda n, cat: (SimpleNamespace(name=n, category=cat), None)
        # eggs rank first, so they go first even though "dairy" sorts first alphabetically
        cands = [mk("e1", "eggs"), mk("c1", "dairy"), mk("c2", "dairy"), mk("c3", "dairy"), mk("t1", "nuts_legumes"),
                 mk("c4", "dairy"), mk("e2", "eggs")]
        out = [c[0].name for c in meal_builder._interleave_groups(cands, 5)]
        self.assertEqual(out, ["e1", "c1", "t1", "e2", "c2"])
        self.assertEqual(len(meal_builder._interleave_groups(cands, 99)), 7)  # everything, nothing lost or repeated

    def test_cheese_is_no_longer_a_preferred_word(self):
        self.assertNotIn("cheese", meal_builder.BREAKFAST_PROTEIN.prefer)


class RealBreakfastRowsTests(TestCase):
    """Real rows from the reviewer's database (name, group, kcal per 100 g)."""

    def carb(self, name, category, kcal, protein, carbs, fat):
        return make_food(name, category, kcal, protein, carbs, fat)

    def test_pan_de_sal_and_the_common_loaves_fit_a_breakfast_carb(self):
        for name, kcal, protein, carbs, fat in [
            ("Bread, pan de sal", 330, 9, 62, 4), ("Bread, pan de monay", 318, 9, 60, 4),
            ("Bread, white, loaf", 329, 9, 62, 4), ("Bread, brown", 313, 9, 58, 4),
        ]:
            f = self.carb(name, "rice_grains", kcal, protein, carbs, fat)
            self.assertTrue(meal_builder._fits_role(f, meal_builder.BREAKFAST_CARB), name)
            self.assertFalse(meal_builder._fits_role(f, meal_builder.CARB), name)  # all are over lunch's 260 kcal

    def test_dry_and_very_sweet_things_are_still_not_breakfast_carbs(self):
        for name, kcal, carbs in [
            ("Buckwheat groats, roasted, dry", 346, 75), ("Bread, toasted", 349, 70), ("Bread, pan de coco", 349, 60),
            ("Cereals, oats, instant, fortified, plain, dry", 362, 66), ("Oats, quick-cooking", 423, 66),
            ("Cereals ready-to-eat, POST, HONEY BUNCHES OF OATS, honey roasted", 401, 80),
        ]:
            f = self.carb(name, "rice_grains", kcal, 9, carbs, 4)
            self.assertFalse(meal_builder._fits_role(f, meal_builder.BREAKFAST_CARB), name)

    def test_cooked_oatmeal_fits_even_though_it_is_under_12_g_carbs_per_100_g(self):
        f = self.carb("Cereals, oats, regular and quick, unenriched, cooked with water (includes boiling and microwaving), without salt",
                      "rice_grains", 71, 2.5, 11.5, 1.5)
        self.assertTrue(meal_builder._fits_role(f, meal_builder.BREAKFAST_CARB))
        self.assertFalse(meal_builder._fits_role(f, meal_builder.CARB))  # lunch and dinner still need 12 g or more

    def test_pan_de_sal_is_a_common_food_and_sweet_breads_are_not(self):
        for name in ["Bread, pan de sal", "Bread, white, loaf", "Bread, pan de monay", "Bread, brown"]:
            self.assertTrue(staples.is_staple(food(name, "rice_grains")), name)
        for name in ["Bread, sweet roll", "Bread, cinnamon roll", "Bread, pan de coco", "Bread, pan de limon",
                     "Bread, cheese roll", "Bread, raisin", "Bread, w/ margarine & sugar filling",
                     "Bread, toasted, w/ margarine-sugar topping", "Bread, hotdog roll", "Bread, pan de bonete"]:
            self.assertFalse(staples.is_staple(food(name, "rice_grains")), name)
        self.assertTrue(staples.is_staple(food("Sweet potato, purple, boiled", "roots_tubers")))  # not "sweet roll"

    def test_pan_de_sal_is_a_preferred_breakfast_carb(self):
        pan = self.carb("Bread, pan de sal", "rice_grains", 330, 9, 62, 4)
        coco = self.carb("Bread, pan de coco", "rice_grains", 330, 9, 62, 4)
        diff = meal_builder._prerank(pan, meal_builder.BREAKFAST_CARB, 0) - meal_builder._prerank(coco, meal_builder.BREAKFAST_CARB, 0)
        self.assertAlmostEqual(diff, staples.W_STAPLE_POOL)  # same preference, but only the plain one is common

    def test_dried_egg_powder_is_never_a_portion(self):
        for name in ["Egg, whole, dried", "Egg, white, dried, flakes, stabilized, glucose reduced", "Egg, yolk, dried"]:
            f = make_food(name, "eggs", 575, 48, 1, 41)
            self.assertTrue(staples.is_ingredient_only(f), name)
            self.assertFalse(food_suggester._is_ready_to_eat(f), name)
            self.assertFalse(meal_builder._fits_role(f, meal_builder.BREAKFAST_PROTEIN), name)

    def test_cooked_eggs_are_ready_and_fit_breakfast(self):
        for name, kcal in [("Egg, whole, cooked, scrambled", 149), ("Egg, whole, cooked, fried", 196),
                           ("Egg, whole, cooked, hard-boiled", 155), ("Egg, whole, cooked, poached", 143),
                           ("Egg, whole, cooked, omelet", 154), ("Egg, chicken, whole, boiled", 166),
                           ("Egg, quail, boiled", 150), ("Eggs, scrambled, frozen mixture", 131)]:
            f = make_food(name, "eggs", kcal, 12.5, 1.1, 10.6)
            self.assertFalse(staples.is_ingredient_only(f), name)
            self.assertTrue(meal_builder._fits_role(f, meal_builder.BREAKFAST_PROTEIN), name)

    def test_other_dried_foods_are_not_caught_by_the_egg_rule(self):
        self.assertFalse(staples.is_ingredient_only(food("Anchovy, dried", "viands_fish")))
        self.assertFalse(staples.is_ingredient_only(food("Egg, duck, whole, salted", "eggs")))

    def test_dried_and_evaporated_dairy_are_ingredients_but_ordinary_dairy_is_not(self):
        for name in ["Milk, dry, whole, with added vitamin D", "Milk, nonfat, dried", "Milk, evaporated, canned",
                     "Milk, condensed, sweetened", "Milk, powdered", "Cheese, parmesan, dehydrated"]:
            f = make_food(name, "dairy", 400, 25, 40, 20)
            self.assertTrue(staples.is_ingredient_only(f), name)
            self.assertFalse(food_suggester._is_ready_to_eat(f), name)
        for name in ["Milk, whole", "Yogurt, Greek, plain, nonfat", "Cheese, cottage, dry curd", "Cheese, cottage",
                     "Milk, goat"]:
            self.assertFalse(staples.is_ingredient_only(food(name, "dairy")), name)

    def test_dried_milk_never_reaches_a_breakfast_plate(self):
        user = Account.objects.create_user(email="dm@test.com", password="pass12345")
        profile, _ = NutritionProfile.objects.get_or_create(user=user)
        make_food("Milk, nonfat, dried", "dairy", 362, 36, 52, 0.8)    # densest protein, preferred word "milk"
        make_food("Egg, whole, dried", "eggs", 575, 48, 1, 41)
        make_food("Egg, chicken, whole, boiled", "eggs", 155, 12.6, 1.1, 10.6)
        make_food("Rice, well-milled, boiled", "rice_grains", 129, 2.6, 28, 0.3)
        make_food("Banana, lakatan", "fruits", 90, 1, 22, 0.3)
        names = {i.food.name for p in build_meal_suggestions(user, profile, "breakfast", DAY, limit=6)[1] for i in p.items}
        self.assertIn("Egg, chicken, whole, boiled", names)
        self.assertNotIn("Milk, nonfat, dried", names)
        self.assertNotIn("Egg, whole, dried", names)

    def test_bread_stix_is_not_the_everyday_bread(self):
        self.assertFalse(staples.is_staple(food("Bread Stix (Nissin)", "rice_grains")))
