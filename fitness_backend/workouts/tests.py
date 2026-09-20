from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import PerformedExercise, TemplateExercise, TemplateHistory, WgerExercise, WorkoutTemplate

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


class WorkoutTrendsTests(APITestCase):
    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        self.other = Account.objects.create_user(email="b@test.com", password="pass12345")
        self.client.force_authenticate(user=self.user)

    def test_trends_requires_auth(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/workouts/trends/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rejects_invalid_period(self):
        response = self.client.get("/workouts/trends/?period=year")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_history_returns_zeroed_response(self):
        response = self.client.get("/workouts/trends/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["days_logged"], 0)
        self.assertEqual(response.data["total_workouts"], 0)
        self.assertEqual(response.data["current_streak"], 0)
        self.assertEqual(len(response.data["days"]), 7)

    def test_volume_is_sum_of_weight_times_reps_across_all_sets(self):
        history = TemplateHistory.objects.create(
            user=self.user, template_title="Push Day", started_at=timezone.now()
        )
        PerformedExercise.objects.create(
            history=history, exercise_name="Bench Press",
            sets_data=[{"weight": 40, "reps": 10}, {"weight": 42.5, "reps": 8}],
        )
        response = self.client.get("/workouts/trends/")
        today_entry = response.data["days"][-1]
        self.assertEqual(today_entry["volume"], 40 * 10 + 42.5 * 8)
        self.assertEqual(today_entry["sets"], 2)
        self.assertEqual(today_entry["workouts"], 1)

    def test_averages_only_count_days_with_a_workout(self):
        # One workout with 100 total volume, on an otherwise-empty week --
        # averaging over 7 days would understate this; averaging over the
        # 1 active day should give exactly 100.
        history = TemplateHistory.objects.create(
            user=self.user, template_title="Push Day", started_at=timezone.now()
        )
        PerformedExercise.objects.create(
            history=history, exercise_name="Bench Press", sets_data=[{"weight": 50, "reps": 2}],
        )
        response = self.client.get("/workouts/trends/")
        self.assertEqual(response.data["averages"]["volume"], 100)

    def test_does_not_include_other_users_workouts(self):
        TemplateHistory.objects.create(
            user=self.other, template_title="Other's Workout", started_at=timezone.now()
        )
        response = self.client.get("/workouts/trends/")
        self.assertEqual(response.data["days_logged"], 0)
        self.assertEqual(response.data["total_workouts"], 0)

    def test_streak_counts_consecutive_days_ending_today(self):
        for days_ago in [0, 1, 2]:
            TemplateHistory.objects.create(
                user=self.user, template_title="Workout",
                started_at=timezone.now() - timezone.timedelta(days=days_ago),
            )
        response = self.client.get("/workouts/trends/")
        self.assertEqual(response.data["current_streak"], 3)

    def test_streak_still_counts_if_today_has_no_workout_yet(self):
        TemplateHistory.objects.create(
            user=self.user, template_title="Workout",
            started_at=timezone.now() - timezone.timedelta(days=1),
        )
        response = self.client.get("/workouts/trends/")
        self.assertEqual(response.data["current_streak"], 1)

    def test_streak_breaks_on_a_gap(self):
        TemplateHistory.objects.create(
            user=self.user, template_title="Workout", started_at=timezone.now(),
        )
        TemplateHistory.objects.create(
            user=self.user, template_title="Workout",
            started_at=timezone.now() - timezone.timedelta(days=3),
        )
        response = self.client.get("/workouts/trends/")
        self.assertEqual(response.data["current_streak"], 1)

    def test_month_period_returns_30_days(self):
        response = self.client.get("/workouts/trends/?period=month")
        self.assertEqual(len(response.data["days"]), 30)

    def test_includes_total_and_previous_period_volume(self):
        # This week: one workout, 100 volume.
        history = TemplateHistory.objects.create(
            user=self.user, template_title="Push Day", started_at=timezone.now()
        )
        PerformedExercise.objects.create(
            history=history, exercise_name="Bench Press", sets_data=[{"weight": 50, "reps": 2}],
        )
        # Last week: one workout, 50 volume.
        previous_history = TemplateHistory.objects.create(
            user=self.user, template_title="Push Day",
            started_at=timezone.now() - timezone.timedelta(days=10),
        )
        PerformedExercise.objects.create(
            history=previous_history, exercise_name="Bench Press", sets_data=[{"weight": 25, "reps": 2}],
        )
        response = self.client.get("/workouts/trends/")
        self.assertEqual(response.data["total_volume"], 100)
        self.assertEqual(response.data["previous_period_volume"], 50)
        self.assertEqual(response.data["volume_change_pct"], 100)  # doubled

    def test_volume_change_pct_is_none_with_no_prior_data(self):
        history = TemplateHistory.objects.create(
            user=self.user, template_title="Push Day", started_at=timezone.now()
        )
        PerformedExercise.objects.create(
            history=history, exercise_name="Bench Press", sets_data=[{"weight": 50, "reps": 2}],
        )
        response = self.client.get("/workouts/trends/")
        self.assertIsNone(response.data["volume_change_pct"])


class ExerciseFrequencyTests(APITestCase):
    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        self.other = Account.objects.create_user(email="b@test.com", password="pass12345")
        self.client.force_authenticate(user=self.user)

    def test_requires_auth(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/workouts/trends/exercises/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_orders_by_session_frequency(self):
        for i in range(3):
            history = TemplateHistory.objects.create(
                user=self.user, template_title="Push Day",
                started_at=timezone.now() - timezone.timedelta(days=i),
            )
            PerformedExercise.objects.create(history=history, exercise_name="Bench Press", sets_data=[{"weight": 40, "reps": 8}])
        history = TemplateHistory.objects.create(user=self.user, template_title="Push Day", started_at=timezone.now())
        PerformedExercise.objects.create(history=history, exercise_name="Overhead Press", sets_data=[{"weight": 20, "reps": 8}])

        response = self.client.get("/workouts/trends/exercises/")
        self.assertEqual(response.data[0]["name"], "Bench Press")
        self.assertEqual(response.data[0]["sessions"], 3)
        self.assertEqual(response.data[1]["name"], "Overhead Press")
        self.assertEqual(response.data[1]["sessions"], 1)

    def test_counts_sessions_not_sets(self):
        """Two sets of the same exercise in one session is still 1 session, not 2."""
        history = TemplateHistory.objects.create(user=self.user, template_title="Push Day", started_at=timezone.now())
        PerformedExercise.objects.create(history=history, exercise_name="Bench Press", sets_data=[{"weight": 40, "reps": 8}])
        PerformedExercise.objects.create(history=history, exercise_name="Bench Press", sets_data=[{"weight": 42, "reps": 6}])
        response = self.client.get("/workouts/trends/exercises/")
        self.assertEqual(response.data[0]["sessions"], 1)

    def test_does_not_include_other_users_exercises(self):
        history = TemplateHistory.objects.create(user=self.other, template_title="Push Day", started_at=timezone.now())
        PerformedExercise.objects.create(history=history, exercise_name="Deadlift", sets_data=[{"weight": 100, "reps": 5}])
        response = self.client.get("/workouts/trends/exercises/")
        self.assertEqual(response.data, [])


class ExerciseProgressionTests(APITestCase):
    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        self.other = Account.objects.create_user(email="b@test.com", password="pass12345")
        self.client.force_authenticate(user=self.user)

    def test_requires_auth(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/workouts/trends/exercise/?name=Bench Press")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_requires_name_param(self):
        response = self.client.get("/workouts/trends/exercise/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_invalid_period(self):
        response = self.client.get("/workouts/trends/exercise/?name=Bench Press&period=forever")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_tracks_heaviest_set_per_session(self):
        history = TemplateHistory.objects.create(user=self.user, template_title="Push Day", started_at=timezone.now())
        PerformedExercise.objects.create(
            history=history, exercise_name="Bench Press",
            sets_data=[{"weight": 40, "reps": 10}, {"weight": 45, "reps": 6}, {"weight": 42.5, "reps": 8}],
        )
        response = self.client.get("/workouts/trends/exercise/?name=Bench Press&period=all")
        self.assertEqual(len(response.data["sessions"]), 1)
        session = response.data["sessions"][0]
        self.assertEqual(session["top_weight"], 45)
        self.assertEqual(session["top_weight_reps"], 6)
        self.assertEqual(session["total_sets"], 3)

    def test_progression_across_multiple_sessions_in_date_order(self):
        for weight, days_ago in [(40, 14), (45, 7), (50, 0)]:
            history = TemplateHistory.objects.create(
                user=self.user, template_title="Push Day",
                started_at=timezone.now() - timezone.timedelta(days=days_ago),
            )
            PerformedExercise.objects.create(history=history, exercise_name="Bench Press", sets_data=[{"weight": weight, "reps": 5}])

        response = self.client.get("/workouts/trends/exercise/?name=Bench Press&period=all")
        weights = [s["top_weight"] for s in response.data["sessions"]]
        self.assertEqual(weights, [40, 45, 50])  # oldest to newest

    def test_period_filters_out_older_sessions(self):
        old_history = TemplateHistory.objects.create(
            user=self.user, template_title="Push Day",
            started_at=timezone.now() - timezone.timedelta(days=100),
        )
        PerformedExercise.objects.create(history=old_history, exercise_name="Bench Press", sets_data=[{"weight": 40, "reps": 5}])

        response = self.client.get("/workouts/trends/exercise/?name=Bench Press&period=3months")
        self.assertEqual(response.data["sessions"], [])

    def test_unknown_exercise_name_returns_empty_not_error(self):
        response = self.client.get("/workouts/trends/exercise/?name=Nonexistent Exercise&period=all")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["sessions"], [])

    def test_does_not_include_other_users_sessions(self):
        history = TemplateHistory.objects.create(user=self.other, template_title="Push Day", started_at=timezone.now())
        PerformedExercise.objects.create(history=history, exercise_name="Bench Press", sets_data=[{"weight": 100, "reps": 5}])
        response = self.client.get("/workouts/trends/exercise/?name=Bench Press&period=all")
        self.assertEqual(response.data["sessions"], [])


class ExerciseSearchTests(APITestCase):
    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        self.client.force_authenticate(user=self.user)

    def test_requires_auth(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/workouts/exercises/search/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_empty_cache_returns_hint_not_error(self):
        response = self.client.get("/workouts/exercises/search/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("hint", response.data)
        self.assertEqual(response.data["results"], [])

    def test_no_query_and_no_category_browses_everything(self):
        """This is the fix -- previously returned empty until the user typed something."""
        WgerExercise.objects.create(id=1, name="Bench Press", category_name="Chest")
        WgerExercise.objects.create(id=2, name="Squat", category_name="Legs")
        response = self.client.get("/workouts/exercises/search/")
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 2)

    def test_filters_by_query(self):
        WgerExercise.objects.create(id=1, name="Bench Press", category_name="Chest")
        WgerExercise.objects.create(id=2, name="Squat", category_name="Legs")
        response = self.client.get("/workouts/exercises/search/?q=bench")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], "Bench Press")

    def test_filters_by_category_alone_no_query(self):
        WgerExercise.objects.create(id=1, name="Bench Press", category_name="Chest")
        WgerExercise.objects.create(id=2, name="Squat", category_name="Legs")
        response = self.client.get("/workouts/exercises/search/?category=Legs")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], "Squat")

    def test_pagination_next_offset(self):
        for i in range(25):
            WgerExercise.objects.create(id=i, name=f"Exercise {i}", category_name="Chest")
        response = self.client.get("/workouts/exercises/search/")
        self.assertEqual(len(response.data["results"]), 20)  # PAGE_SIZE
        self.assertEqual(response.data["next_offset"], 20)

        response = self.client.get("/workouts/exercises/search/?offset=20")
        self.assertEqual(len(response.data["results"]), 5)
        self.assertIsNone(response.data["next_offset"])


class ExerciseCategoryListTests(APITestCase):
    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        self.client.force_authenticate(user=self.user)

    def test_requires_auth(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/workouts/exercises/categories/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_returns_distinct_sorted_categories(self):
        WgerExercise.objects.create(id=1, name="Bench Press", category_name="Chest")
        WgerExercise.objects.create(id=2, name="Incline Press", category_name="Chest")
        WgerExercise.objects.create(id=3, name="Squat", category_name="Legs")
        response = self.client.get("/workouts/exercises/categories/")
        self.assertEqual(response.data, ["Chest", "Legs"])

    def test_excludes_blank_categories(self):
        WgerExercise.objects.create(id=1, name="Mystery Move", category_name="")
        response = self.client.get("/workouts/exercises/categories/")
        self.assertEqual(response.data, [])

    def test_empty_cache_returns_empty_list(self):
        response = self.client.get("/workouts/exercises/categories/")
        self.assertEqual(response.data, [])