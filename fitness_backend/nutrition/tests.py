from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Profile
from .models import DailyEntry, FoodEntry, FoodItem, NutritionProfile

import datetime

Account = get_user_model()


def make_food(name="Adobo", calories=250, protein_g=20, carbs_g=10, fat_g=15):
    return FoodItem.objects.create(
        name=name,
        category="viands_meat",
        serving_description="1 cup",
        serving_size_g=150,
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
    )


class AuthRequiredTests(APITestCase):
    def test_daily_requires_auth(self):
        response = self.client.get("/nutrition/daily/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_entries_requires_auth(self):
        response = self.client.post("/nutrition/entries/", {})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class FoodSearchTests(APITestCase):
    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        self.client.force_authenticate(user=self.user)
        make_food("Chicken Adobo")
        make_food("Pork Sinigang")

    def test_search_matches_name(self):
        response = self.client.get("/nutrition/foods/search/?q=adobo")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [f["name"] for f in response.data.get("results", response.data)]
        self.assertTrue(any("Adobo" in n for n in names))


class DailyEntryTests(APITestCase):
    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        self.client.force_authenticate(user=self.user)

    def test_empty_day_returns_zeroed_response_without_creating_row(self):
        response = self.client.get(f"/nutrition/daily/?date={timezone.localdate().isoformat()}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_calories"], 0)
        self.assertFalse(DailyEntry.objects.exists())


class NutritionProfileAutoCalculationTests(APITestCase):
    """
    NutritionProfile is lazily created on first touch (not at registration
    itself). This checks that first touch seeds personalized goals from
    accounts.Profile when enough signup data is present, and only falls
    back to the generic hardcoded defaults when it isn't.
    """

    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        self.client.force_authenticate(user=self.user)

    def test_complete_profile_seeds_calculated_goals_not_generic_defaults(self):
        Profile.objects.create(
            user=self.user,
            gender="male",
            date_of_birth=datetime.date(1998, 1, 1),
            activity_level="moderately_active",
            current_weight_kg=75,
            height_ft=5,
            height_in=10,
        )
        response = self.client.get("/nutrition/daily/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        nutrition_profile = NutritionProfile.objects.get(user=self.user)
        # Wouldn't hold exactly by coincidence for this weight/height/age/gender/activity combo.
        self.assertNotEqual(nutrition_profile.daily_calories_goal, 2000)
        self.assertNotEqual(nutrition_profile.daily_protein_goal, 100)

    def test_incomplete_profile_falls_back_to_generic_defaults(self):
        # No accounts.Profile at all -- e.g. signup wizard was abandoned after step 1.
        response = self.client.get("/nutrition/daily/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        nutrition_profile = NutritionProfile.objects.get(user=self.user)
        self.assertEqual(nutrition_profile.daily_calories_goal, 2000)
        self.assertEqual(nutrition_profile.daily_protein_goal, 100)

    def test_existing_nutrition_profile_is_never_recalculated_on_touch(self):
        """Once seeded (calculated or default), later profile edits shouldn't silently overwrite user-picked goals."""
        Profile.objects.create(
            user=self.user, gender="male", date_of_birth=datetime.date(1998, 1, 1),
            activity_level="moderately_active", current_weight_kg=75, height_ft=5, height_in=10,
        )
        self.client.get("/nutrition/daily/")  # first touch -- seeds calculated goals
        nutrition_profile = NutritionProfile.objects.get(user=self.user)
        nutrition_profile.daily_calories_goal = 1800  # user manually overrides
        nutrition_profile.save()

        self.client.get("/nutrition/daily/")  # second touch
        nutrition_profile.refresh_from_db()
        self.assertEqual(nutrition_profile.daily_calories_goal, 1800)


class AutoRecalculateToggleTests(APITestCase):
    """
    Covers the explicit user-controlled setting (see
    accounts.tests.NutritionGoalSyncTests for the accounts-side trigger
    points): auto_recalculate_goals is a plain on/off switch, not an
    inferred state -- while on, a weight/profile change always overwrites
    goals, even ones the user typed in by hand; while off, nothing
    recalculates automatically, period.
    """

    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        Profile.objects.create(
            user=self.user, gender="male", date_of_birth=datetime.date(1998, 1, 1),
            activity_level="moderately_active", current_weight_kg=75, height_ft=5, height_in=10,
        )
        self.client.force_authenticate(user=self.user)

    def test_defaults_to_enabled_on_first_seed(self):
        self.client.get("/nutrition/daily/")
        nutrition_profile = NutritionProfile.objects.get(user=self.user)
        self.assertTrue(nutrition_profile.auto_recalculate_goals)

    def test_manual_goal_edit_does_not_disable_the_setting(self):
        """Editing a number is not the same action as flipping the toggle off."""
        self.client.get("/nutrition/daily/")
        self.client.patch("/nutrition/profile/", {"daily_calories_goal": 1800})
        nutrition_profile = NutritionProfile.objects.get(user=self.user)
        self.assertEqual(nutrition_profile.daily_calories_goal, 1800)
        self.assertTrue(nutrition_profile.auto_recalculate_goals)

    def test_enabled_setting_overwrites_a_manually_typed_goal_on_next_stat_change(self):
        self.client.get("/nutrition/daily/")
        self.client.patch("/nutrition/profile/", {"daily_calories_goal": 1800})

        self.user.refresh_from_db()
        self.client.patch("/accounts/profile/", {"activity_level": "very_active"})

        nutrition_profile = NutritionProfile.objects.get(user=self.user)
        self.assertNotEqual(nutrition_profile.daily_calories_goal, 1800)

    def test_disabling_setting_stops_all_future_auto_recalculation(self):
        self.client.get("/nutrition/daily/")
        self.client.patch("/nutrition/profile/", {"auto_recalculate_goals": False})
        self.client.patch("/nutrition/profile/", {"daily_calories_goal": 1800})

        self.user.refresh_from_db()
        self.client.patch("/accounts/profile/", {"activity_level": "very_active"})

        nutrition_profile = NutritionProfile.objects.get(user=self.user)
        self.assertEqual(nutrition_profile.daily_calories_goal, 1800)  # untouched
        self.assertFalse(nutrition_profile.auto_recalculate_goals)

    def test_re_enabling_setting_resumes_auto_recalculation(self):
        self.client.get("/nutrition/daily/")
        self.client.patch("/nutrition/profile/", {"auto_recalculate_goals": False})
        self.client.patch("/nutrition/profile/", {"daily_calories_goal": 1800})

        self.client.patch("/nutrition/profile/", {"auto_recalculate_goals": True})
        self.user.refresh_from_db()
        self.client.patch("/accounts/profile/", {"activity_level": "very_active"})

        nutrition_profile = NutritionProfile.objects.get(user=self.user)
        self.assertNotEqual(nutrition_profile.daily_calories_goal, 1800)


class FoodEntryTests(APITestCase):
    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        self.other = Account.objects.create_user(email="b@test.com", password="pass12345")
        self.client.force_authenticate(user=self.user)
        self.food = make_food(calories=200, protein_g=20, carbs_g=10, fat_g=5)

    def test_log_food_creates_daily_entry_with_snapshotted_macros(self):
        response = self.client.post(
            "/nutrition/entries/",
            {"food_item": self.food.id, "meal_type": "lunch", "servings": 2, "date": timezone.localdate().isoformat()},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        entry = FoodEntry.objects.get(daily_entry__nutrition_profile__user=self.user)
        self.assertEqual(entry.calories, 400)  # 200 * 2 servings

    def test_rejects_missing_required_fields(self):
        response = self.client.post("/nutrition/entries/", {"servings": 1})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_invalid_meal_type(self):
        response = self.client.post(
            "/nutrition/entries/",
            {"food_item": self.food.id, "meal_type": "brunch", "servings": 1},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_zero_servings(self):
        response = self.client.post(
            "/nutrition/entries/",
            {"food_item": self.food.id, "meal_type": "lunch", "servings": 0},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_excessive_servings(self):
        response = self.client.post(
            "/nutrition/entries/",
            {"food_item": self.food.id, "meal_type": "lunch", "servings": 999},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_snapshot_survives_later_food_item_edits(self):
        """Editing FoodItem later shouldn't silently rewrite historical logs."""
        self.client.post(
            "/nutrition/entries/",
            {"food_item": self.food.id, "meal_type": "lunch", "servings": 1, "date": timezone.localdate().isoformat()},
        )
        self.food.calories = 9999
        self.food.save()
        entry = FoodEntry.objects.get(daily_entry__nutrition_profile__user=self.user)
        self.assertEqual(entry.calories, 200)

    def test_cannot_delete_other_users_entry(self):
        other_profile, _ = NutritionProfile.objects.get_or_create(user=self.other)
        daily = DailyEntry.objects.create(nutrition_profile=other_profile, date=timezone.localdate().isoformat())
        entry = FoodEntry.objects.create(
            daily_entry=daily, food_item=self.food, meal_type="lunch", servings=1,
            calories=200, protein_g=20, carbs_g=10, fat_g=5,
        )
        response = self.client.delete(f"/nutrition/entries/{entry.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)