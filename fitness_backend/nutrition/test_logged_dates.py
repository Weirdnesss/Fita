from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from nutrition.models import DailyEntry, FoodEntry, FoodItem, NutritionProfile


class LoggedDatesTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(email="dots@example.com", password="pw12345678")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.profile, _ = NutritionProfile.objects.get_or_create(user=self.user)
        self.food = FoodItem.objects.create(
            name="Test rice", category="rice_grains", serving_size_g=100, calories=130, protein_g=2.7, carbs_g=28, fat_g=0.3,
        )

    def log(self, date_str):
        entry, _ = DailyEntry.objects.get_or_create(nutrition_profile=self.profile, date=date_str)
        FoodEntry.objects.create(
            daily_entry=entry, food_item=self.food, meal_type="lunch",
            servings=1, calories=130, protein_g=2.7, carbs_g=28, fat_g=0.3,
        )
        return entry

    def get(self, month):
        return self.client.get("/nutrition/daily/dates/", {"month": month})

    def test_lists_only_days_with_food_in_that_month(self):
        self.log("2026-11-03")
        self.log("2026-11-03")
        self.log("2026-11-10")
        self.log("2026-10-31")
        res = self.get("2026-11")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["dates"], ["2026-11-03", "2026-11-10"])

    def test_day_with_all_entries_deleted_is_not_marked(self):
        entry = self.log("2026-11-05")
        entry.food_entries.all().delete()
        self.assertEqual(self.get("2026-11").data["dates"], [])

    def test_other_users_days_are_not_included(self):
        User = get_user_model()
        other = User.objects.create_user(email="other@example.com", password="pw12345678")
        other_profile, _ = NutritionProfile.objects.get_or_create(user=other)
        entry = DailyEntry.objects.create(nutrition_profile=other_profile, date="2026-11-07")
        FoodEntry.objects.create(
            daily_entry=entry, food_item=self.food, meal_type="lunch",
            servings=1, calories=130, protein_g=2.7, carbs_g=28, fat_g=0.3,
        )
        self.assertEqual(self.get("2026-11").data["dates"], [])

    def test_bad_month_is_rejected(self):
        for bad in ("", "2026", "2026-13", "abcd-ef", "2026-1-1"):
            self.assertEqual(self.get(bad).status_code, 400, bad)

    def test_requires_login(self):
        res = APIClient().get("/nutrition/daily/dates/", {"month": "2026-11"})
        self.assertIn(res.status_code, (401, 403))
