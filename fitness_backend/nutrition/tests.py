from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import DailyEntry, FoodEntry, FoodItem, NutritionProfile

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