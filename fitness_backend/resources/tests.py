from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Resource, ResourceCategory

Account = get_user_model()


class AuthRequiredTests(APITestCase):
    """
    ResourceListView sets no explicit permission_classes -- it relies on
    DEFAULT_PERMISSION_CLASSES (IsAuthenticated) in settings.py. This test
    exists specifically to catch someone accidentally opening the endpoint
    up later (e.g. by adding permission_classes = [] "to fix a bug").
    """

    def test_list_requires_auth(self):
        response = self.client.get("/resources/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ResourceListTests(APITestCase):
    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        self.client.force_authenticate(user=self.user)
        Resource.objects.create(
            title="Beginner Squat Form", category=ResourceCategory.WORKOUT,
            url="https://example.com/squat", source="NASM",
        )
        Resource.objects.create(
            title="Macro Counting 101", category=ResourceCategory.NUTRITION,
            url="https://example.com/macros", source="Healthline",
        )
        Resource.objects.create(
            title="Sleep and Recovery", category=ResourceCategory.GENERAL,
            url="https://example.com/sleep", source="NASM",
        )

    def test_list_returns_all_resources_unscoped_by_user(self):
        """Resources are a shared catalog -- every user sees the same list."""
        other = Account.objects.create_user(email="b@test.com", password="pass12345")
        self.client.force_authenticate(user=other)
        response = self.client.get("/resources/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)

    def test_filter_by_category(self):
        response = self.client.get("/resources/?category=workout")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["title"], "Beginner Squat Form")

    def test_search_by_title(self):
        response = self.client.get("/resources/?q=macro")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["title"], "Macro Counting 101")

    def test_unknown_category_returns_empty_not_error(self):
        response = self.client.get("/resources/?category=not_a_real_category")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)