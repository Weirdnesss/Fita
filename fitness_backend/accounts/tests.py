from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Profile, WeightLog
from nutrition.models import NutritionProfile

import datetime

Account = get_user_model()


class RegisterTests(APITestCase):
    """POST /accounts/register/ -- open to anyone, creates an empty Profile shell."""

    def test_register_creates_account_and_profile(self):
        response = self.client.post(
            "/accounts/register/",
            {
                "email": "new@test.com",
                "first_name": "New",
                "last_name": "User",
                "password": "strongpass123",
                "confirm_password": "strongpass123",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = Account.objects.get(email="new@test.com")
        self.assertTrue(Profile.objects.filter(user=user).exists())

    def test_register_rejects_mismatched_passwords(self):
        response = self.client.post(
            "/accounts/register/",
            {
                "email": "new2@test.com",
                "first_name": "New",
                "last_name": "User",
                "password": "strongpass123",
                "confirm_password": "different123",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Account.objects.filter(email="new2@test.com").exists())

    def test_register_rejects_duplicate_email(self):
        Account.objects.create_user(email="dupe@test.com", password="pass12345")
        response = self.client.post(
            "/accounts/register/",
            {
                "email": "dupe@test.com",
                "first_name": "A",
                "last_name": "B",
                "password": "strongpass123",
                "confirm_password": "strongpass123",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class AuthRequiredTests(APITestCase):
    """Protected endpoints should reject unauthenticated requests."""

    def test_me_requires_auth(self):
        response = self.client.get("/accounts/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_profile_requires_auth(self):
        response = self.client.get("/accounts/profile/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_weight_logs_require_auth(self):
        response = self.client.get("/accounts/weight-logs/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ProfileTests(APITestCase):
    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        Profile.objects.create(user=self.user)
        self.client.force_authenticate(user=self.user)

    def test_me_returns_own_account(self):
        response = self.client.get("/accounts/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "a@test.com")

    def test_patch_profile_updates_fields(self):
        response = self.client.patch(
            "/accounts/profile/",
            {"gender": "male", "activity_level": "very_active", "primary_goal": "gain_muscle"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.gender, "male")
        self.assertEqual(self.user.profile.primary_goal, "gain_muscle")

    def test_current_weight_kg_is_read_only_on_profile_patch(self):
        """current_weight_kg is derived from WeightLog entries, not directly writable."""
        response = self.client.patch("/accounts/profile/", {"current_weight_kg": 999})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.profile.refresh_from_db()
        self.assertNotEqual(self.user.profile.current_weight_kg, 999)


class WeightLogTests(APITestCase):
    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        Profile.objects.create(user=self.user)
        self.other = Account.objects.create_user(email="b@test.com", password="pass12345")
        Profile.objects.create(user=self.other)
        self.client.force_authenticate(user=self.user)

    def test_logging_weight_syncs_profile_current_weight(self):
        response = self.client.post("/accounts/weight-logs/", {"weight_kg": 70.5, "logged_at": "2026-09-01"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.current_weight_kg, 70.5)

    def test_logging_same_day_twice_updates_not_duplicates(self):
        self.client.post("/accounts/weight-logs/", {"weight_kg": 70, "logged_at": "2026-09-01"})
        self.client.post("/accounts/weight-logs/", {"weight_kg": 71, "logged_at": "2026-09-01"})
        self.assertEqual(WeightLog.objects.filter(user=self.user).count(), 1)
        self.assertEqual(WeightLog.objects.get(user=self.user).weight_kg, 71)

    def test_rejects_implausible_weight(self):
        response = self.client.post("/accounts/weight-logs/", {"weight_kg": 5, "logged_at": "2026-09-01"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_see_other_users_weight_logs(self):
        WeightLog.objects.create(user=self.other, weight_kg=80, logged_at="2026-09-01")
        response = self.client.get("/accounts/weight-logs/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_deleting_last_entry_clears_current_weight(self):
        create = self.client.post("/accounts/weight-logs/", {"weight_kg": 70, "logged_at": "2026-09-01"})
        entry_id = create.data["id"]
        response = self.client.delete(f"/accounts/weight-logs/{entry_id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.user.profile.refresh_from_db()
        self.assertIsNone(self.user.profile.current_weight_kg)

    def test_cannot_delete_other_users_weight_log(self):
        entry = WeightLog.objects.create(user=self.other, weight_kg=80, logged_at="2026-09-01")
        response = self.client.delete(f"/accounts/weight-logs/{entry.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class NutritionGoalSyncTests(APITestCase):
    """
    accounts changes (weight logs, Profile edits) should keep nutrition
    goals fresh via sync_calculated_goals() -- but only while
    auto_recalculate_goals is on (the default); see nutrition.tests for
    the toggle itself.
    """

    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        Profile.objects.create(
            user=self.user, gender="male", date_of_birth=datetime.date(1998, 1, 1),
            activity_level="moderately_active", height_ft=5, height_in=10,
        )
        self.client.force_authenticate(user=self.user)

    def test_logging_weight_seeds_nutrition_profile_with_calculated_goals(self):
        # No NutritionProfile exists yet -- logging a weight (which is
        # itself a required field for the calculation) should trigger
        # get_or_create's own seeding path the next time nutrition is
        # touched, not create one here directly. sync_calculated_goals
        # is a no-op with no NutritionProfile yet.
        self.client.post("/accounts/weight-logs/", {"weight_kg": 75, "logged_at": "2026-09-01"})
        self.assertFalse(NutritionProfile.objects.filter(user=self.user).exists())

    def test_weight_change_updates_existing_unedited_nutrition_goals(self):
        self.client.post("/accounts/weight-logs/", {"weight_kg": 75, "logged_at": "2026-09-01"})
        self.user.refresh_from_db()  # picks up current_weight_kg set via a separate query in _sync_current_weight
        self.client.get("/nutrition/daily/")  # first touch -- seeds calculated goals
        original = NutritionProfile.objects.get(user=self.user).daily_calories_goal

        # force_authenticate reuses one Python `self.user` object across every
        # client call in this test -- a real request always fetches a fresh
        # one, so refresh here to match that (see get_or_create_nutrition_profile
        # / sync_calculated_goals, both of which read the cached user.profile).
        self.user.refresh_from_db()
        self.client.post("/accounts/weight-logs/", {"weight_kg": 95, "logged_at": "2026-09-02"})
        updated = NutritionProfile.objects.get(user=self.user).daily_calories_goal
        self.assertNotEqual(original, updated)

    def test_profile_edit_updates_existing_unedited_nutrition_goals(self):
        self.client.post("/accounts/weight-logs/", {"weight_kg": 75, "logged_at": "2026-09-01"})
        self.user.refresh_from_db()
        self.client.get("/nutrition/daily/")
        original = NutritionProfile.objects.get(user=self.user).daily_calories_goal

        self.user.refresh_from_db()
        self.client.patch("/accounts/profile/", {"activity_level": "very_active"})
        updated = NutritionProfile.objects.get(user=self.user).daily_calories_goal
        self.assertNotEqual(original, updated)