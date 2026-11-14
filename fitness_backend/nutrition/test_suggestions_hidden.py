"""Food and meal suggestions are off by default and come back with FOOD_SUGGESTIONS_ENABLED."""

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

Account = get_user_model()
URLS = ("/nutrition/suggestions/", "/nutrition/suggestions/meals/")


class SuggestionsOffByDefaultTests(APITestCase):
    def setUp(self):
        self.user = Account.objects.create_user(email="off@test.com", password="pass12345")
        self.client.force_authenticate(user=self.user)

    def test_both_endpoints_are_not_found_by_default(self):
        for url in URLS:
            self.assertEqual(self.client.get(url, {"meal_type": "lunch"}).status_code, status.HTTP_404_NOT_FOUND, url)

    def test_not_found_even_without_login(self):
        self.client.force_authenticate(user=None)
        for url in URLS:
            self.assertEqual(self.client.get(url, {"meal_type": "lunch"}).status_code, status.HTTP_404_NOT_FOUND, url)

    @override_settings(FOOD_SUGGESTIONS_ENABLED=True)
    def test_flag_turns_them_back_on(self):
        for url in URLS:
            self.assertNotEqual(self.client.get(url, {"meal_type": "lunch"}).status_code, status.HTTP_404_NOT_FOUND, url)

    def test_goal_suggestions_are_not_affected(self):
        self.assertNotEqual(self.client.get("/nutrition/goals/suggested/").status_code, status.HTTP_404_NOT_FOUND)
