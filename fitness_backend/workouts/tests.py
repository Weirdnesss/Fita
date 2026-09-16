from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import TemplateExercise, TemplateHistory, WgerExercise, WorkoutTemplate

Account = get_user_model()


class AuthRequiredTests(APITestCase):
    def test_templates_require_auth(self):
        response = self.client.get("/workouts/templates/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_history_requires_auth(self):
        response = self.client.get("/workouts/history/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class WorkoutTemplateTests(APITestCase):
    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        self.other = Account.objects.create_user(email="b@test.com", password="pass12345")
        self.client.force_authenticate(user=self.user)

    def test_create_template(self):
        response = self.client.post("/workouts/templates/", {"title": "Push Day", "kind": "main"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(WorkoutTemplate.objects.filter(user=self.user).count(), 1)

    def test_cannot_see_other_users_templates(self):
        WorkoutTemplate.objects.create(user=self.other, title="Other's Plan", kind="main")
        response = self.client.get("/workouts/templates/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_cannot_retrieve_other_users_template_by_id(self):
        template = WorkoutTemplate.objects.create(user=self.other, title="Other's Plan", kind="main")
        response = self.client.get(f"/workouts/templates/{template.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_delete_other_users_template(self):
        template = WorkoutTemplate.objects.create(user=self.other, title="Other's Plan", kind="main")
        response = self.client.delete(f"/workouts/templates/{template.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(WorkoutTemplate.objects.filter(id=template.id).exists())


class AddExerciseTests(APITestCase):
    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        self.template = WorkoutTemplate.objects.create(user=self.user, title="Push Day", kind="main")
        self.client.force_authenticate(user=self.user)

    def test_add_exercise_to_own_template(self):
        # AddExerciseToTemplateView looks up wger_exercise_id in the local
        # WgerExercise cache (populated by `sync_wger_exercises` in real
        # use) -- a ready-to-add exercise has to exist there first.
        WgerExercise.objects.create(id=1, name="Bench Press", category_name="Chest")
        response = self.client.post(
            f"/workouts/templates/{self.template.id}/exercises/",
            {"wger_exercise_id": 1, "target_sets": 4},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(TemplateExercise.objects.filter(template=self.template).count(), 1)

    def test_adding_exercise_not_in_cache_returns_404(self):
        response = self.client.post(
            f"/workouts/templates/{self.template.id}/exercises/",
            {"wger_exercise_id": 999, "target_sets": 4},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_add_exercise_to_other_users_template(self):
        WgerExercise.objects.create(id=1, name="Bench Press", category_name="Chest")
        other = Account.objects.create_user(email="b@test.com", password="pass12345")
        other_template = WorkoutTemplate.objects.create(user=other, title="Other's Plan", kind="main")
        response = self.client.post(
            f"/workouts/templates/{other_template.id}/exercises/",
            {"wger_exercise_id": 1},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class FinishWorkoutTests(APITestCase):
    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        self.client.force_authenticate(user=self.user)

    def test_finish_workout_logs_history(self):
        payload = {
            "template_title": "Push Day",
            "started_at": timezone.now().isoformat(),
            "exercises": [
                {
                    "exercise_name": "Bench Press",
                    "weight_unit": "kg",
                    "sets_data": [{"weight": 40, "reps": 10}, {"weight": 42.5, "reps": 8}],
                }
            ],
        }
        response = self.client.post("/workouts/history/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(TemplateHistory.objects.filter(user=self.user).count(), 1)

    def test_finish_workout_rejects_no_sets_logged(self):
        payload = {
            "template_title": "Push Day",
            "started_at": timezone.now().isoformat(),
            "exercises": [{"exercise_name": "Bench Press", "sets_data": []}],
        }
        response = self.client.post("/workouts/history/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_finish_workout_rejects_future_start_time(self):
        payload = {
            "template_title": "Push Day",
            "started_at": (timezone.now() + timezone.timedelta(days=1)).isoformat(),
            "exercises": [{"exercise_name": "Bench Press", "sets_data": [{"weight": 40, "reps": 10}]}],
        }
        response = self.client.post("/workouts/history/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_see_other_users_history(self):
        other = Account.objects.create_user(email="b@test.com", password="pass12345")
        TemplateHistory.objects.create(
            user=other, template_title="Other's Workout", started_at=timezone.now()
        )
        response = self.client.get("/workouts/history/")
        self.assertEqual(len(response.data), 0)