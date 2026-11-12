from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import InputType, PerformedExercise, TemplateHistory

Account = get_user_model()


def make_account(email):
    return Account.objects.create_user(email=email, password="pass12345", first_name="T", last_name="U")


class HistoryEditTests(APITestCase):
    def setUp(self):
        self.user = make_account("edit@example.com")
        self.client.force_authenticate(self.user)
        self.history = TemplateHistory.objects.create(
            user=self.user, template_title="Push", started_at=timezone.now() - timedelta(hours=1), note="old"
        )
        self.bench = PerformedExercise.objects.create(
            history=self.history,
            exercise_name="Bench Press",
            input_type=InputType.WEIGHT_REPS,
            sets_data=[{"weight": 100.0, "display_weight": 100.0, "reps": 5}],
        )
        self.plank = PerformedExercise.objects.create(
            history=self.history, exercise_name="Plank", input_type=InputType.TIME, sets_data=[{"seconds": 30}]
        )
        self.url = f"/workouts/history/{self.history.id}/"

    def age(self, days):
        TemplateHistory.objects.filter(pk=self.history.pk).update(completed_at=timezone.now() - timedelta(days=days))

    def test_detail_reports_editable_flag(self):
        self.assertTrue(self.client.get(self.url).data["is_editable"])
        self.age(30)
        self.assertFalse(self.client.get(self.url).data["is_editable"])

    def test_can_correct_sets_and_note(self):
        response = self.client.patch(
            self.url,
            {
                "note": "felt good",
                "exercises": [
                    {"id": self.bench.id, "sets_data": [{"weight": 60.0, "display_weight": 60.0, "reps": 8}, {"weight": 60.0, "display_weight": 60.0, "reps": 7}]},
                    {"id": self.plank.id, "sets_data": [{"seconds": 45}]},
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.bench.refresh_from_db()
        self.plank.refresh_from_db()
        self.history.refresh_from_db()
        self.assertEqual(len(self.bench.sets_data), 2)
        self.assertEqual(self.bench.sets_data[0]["reps"], 8)
        self.assertEqual(self.plank.sets_data, [{"seconds": 45}])
        self.assertEqual(self.history.note, "felt good")
        self.assertEqual(response.data["performed_exercises"][0]["total_volume"], 60 * 8 + 60 * 7)

    def test_note_only_leaves_sets_alone(self):
        response = self.client.patch(self.url, {"note": "just a note"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.bench.refresh_from_db()
        self.assertEqual(self.bench.sets_data[0]["reps"], 5)

    def test_cannot_edit_after_the_window(self):
        self.age(8)
        response = self.client.patch(self.url, {"note": "late"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.history.refresh_from_db()
        self.assertEqual(self.history.note, "old")

    def test_edit_allowed_on_last_day_of_window(self):
        self.age(7)
        response = self.client.patch(self.url, {"note": "ok"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_set_must_match_the_exercise_type(self):
        response = self.client.patch(
            self.url, {"exercises": [{"id": self.plank.id, "sets_data": [{"reps": 10}]}]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.plank.refresh_from_db()
        self.assertEqual(self.plank.sets_data, [{"seconds": 30}])

    def test_rejects_invalid_numbers_and_empty_sets(self):
        bad = self.client.patch(
            self.url, {"exercises": [{"id": self.bench.id, "sets_data": [{"weight": -5, "reps": 5}]}]}, format="json"
        )
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)
        empty = self.client.patch(self.url, {"exercises": [{"id": self.bench.id, "sets_data": []}]}, format="json")
        self.assertEqual(empty.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_touch_another_workouts_exercise(self):
        other = TemplateHistory.objects.create(user=self.user, template_title="Pull", started_at=timezone.now())
        stranger = PerformedExercise.objects.create(history=other, exercise_name="Row", sets_data=[{"weight": 40, "reps": 10}])
        response = self.client.patch(
            self.url, {"exercises": [{"id": stranger.id, "sets_data": [{"weight": 1, "reps": 1}]}]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        stranger.refresh_from_db()
        self.assertEqual(stranger.sets_data[0]["weight"], 40)

    def test_other_users_cannot_edit_or_delete(self):
        self.client.force_authenticate(make_account("someone@example.com"))
        self.assertEqual(self.client.patch(self.url, {"note": "x"}, format="json").status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.delete(self.url).status_code, status.HTTP_404_NOT_FOUND)

    def test_exercise_cannot_be_renamed_or_retyped(self):
        self.client.patch(
            self.url,
            {"exercises": [{"id": self.bench.id, "exercise_name": "Hacked", "input_type": "time", "sets_data": [{"weight": 1, "reps": 1}]}]},
            format="json",
        )
        self.bench.refresh_from_db()
        self.assertEqual(self.bench.exercise_name, "Bench Press")
        self.assertEqual(self.bench.input_type, InputType.WEIGHT_REPS)

    def test_delete_works_at_any_age(self):
        self.age(60)
        self.assertEqual(self.client.delete(self.url).status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(TemplateHistory.objects.filter(pk=self.history.pk).exists())
        self.assertFalse(PerformedExercise.objects.filter(pk=self.bench.pk).exists())
