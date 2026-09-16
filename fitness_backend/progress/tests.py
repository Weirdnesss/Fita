import os
from unittest import mock

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from .models import ProgressReport

Account = get_user_model()


class AuthRequiredTests(APITestCase):
    def test_reports_require_auth(self):
        response = self.client.get("/progress/reports/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_generate_requires_auth(self):
        response = self.client.post("/progress/reports/generate/", {})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ReportListTests(APITestCase):
    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        self.other = Account.objects.create_user(email="b@test.com", password="pass12345")
        self.client.force_authenticate(user=self.user)

    def test_cannot_see_other_users_reports(self):
        ProgressReport.objects.create(
            user=self.other, report_number=1, period_start="2026-08-01", period_end="2026-08-07"
        )
        response = self.client.get("/progress/reports/")
        self.assertEqual(len(response.data), 0)

    def test_cannot_retrieve_other_users_report(self):
        report = ProgressReport.objects.create(
            user=self.other, report_number=1, period_start="2026-08-01", period_end="2026-08-07"
        )
        response = self.client.get(f"/progress/reports/{report.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class GenerateReportTests(APITestCase):
    """
    generate_report() itself never raises (it catches its own errors and
    saves a status="failed" report instead), so the one thing that's cheap
    and reliable to test without a real Groq key or mocking the OpenAI SDK
    is the config-error path: ReportGenerationService.__init__ raises
    ValueError when GROQ_API_KEY is missing, which the view turns into a
    clean 502 before ever touching the database with a report row.
    """

    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        self.client.force_authenticate(user=self.user)

    @mock.patch.dict(os.environ, {}, clear=False)
    def test_missing_groq_key_returns_502(self):
        os.environ.pop("GROQ_API_KEY", None)
        response = self.client.post("/progress/reports/generate/", {})
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertFalse(ProgressReport.objects.filter(user=self.user).exists())

    def test_rejects_invalid_report_type(self):
        response = self.client.post("/progress/reports/generate/", {"report_type": "essay"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_out_of_range_period_days(self):
        response = self.client.post("/progress/reports/generate/", {"period_days": 999})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ReportPDFTests(APITestCase):
    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        self.client.force_authenticate(user=self.user)

    def test_pending_report_cannot_be_exported(self):
        report = ProgressReport.objects.create(
            user=self.user, report_number=1, period_start="2026-08-01", period_end="2026-08-07",
            status="pending",
        )
        response = self.client.get(f"/progress/reports/{report.id}/pdf/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)