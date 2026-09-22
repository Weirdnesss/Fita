import os
from unittest import mock

from django.contrib.auth import get_user_model
from openai import RateLimitError
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Chat, Message, MessageRole

Account = get_user_model()


class AuthRequiredTests(APITestCase):
    def test_chats_require_auth(self):
        response = self.client.get("/coach/chats/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ChatTests(APITestCase):
    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        self.other = Account.objects.create_user(email="b@test.com", password="pass12345")
        self.client.force_authenticate(user=self.user)

    def test_create_chat(self):
        response = self.client.post("/coach/chats/", {})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Chat.objects.filter(user=self.user).count(), 1)

    def test_cannot_see_other_users_chats(self):
        Chat.objects.create(user=self.other, title="Other's chat")
        response = self.client.get("/coach/chats/")
        self.assertEqual(len(response.data), 0)

    def test_cannot_open_other_users_chat(self):
        chat = Chat.objects.create(user=self.other, title="Other's chat")
        response = self.client.get(f"/coach/chats/{chat.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class SendMessageTests(APITestCase):
    def setUp(self):
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")
        self.chat = Chat.objects.create(user=self.user, title="New Chat")
        self.client.force_authenticate(user=self.user)

    @mock.patch.dict(os.environ, {}, clear=False)
    def test_missing_groq_key_returns_502_without_saving_assistant_reply(self):
        os.environ.pop("GROQ_API_KEY", None)
        response = self.client.post(f"/coach/chats/{self.chat.id}/messages/", {"content": "hello"})
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        # The user's message is still saved even though the assistant failed --
        # only the assistant's reply should be missing.
        self.assertEqual(Message.objects.filter(chat=self.chat, role=MessageRole.USER).count(), 1)
        self.assertEqual(Message.objects.filter(chat=self.chat, role=MessageRole.ASSISTANT).count(), 0)

    def test_groq_rate_limit_returns_429_with_retry_after_message(self):
        fake_response = mock.Mock()
        fake_response.headers = {"retry-after": "5"}
        rate_limit_error = RateLimitError("rate limited", response=fake_response, body=None)
        with mock.patch("coach.views.LLMService") as MockLLM:
            MockLLM.return_value.get_response.side_effect = rate_limit_error
            response = self.client.post(f"/coach/chats/{self.chat.id}/messages/", {"content": "hello"})
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("5 seconds", response.data["error"])
        # Same as the missing-key case -- the user's message is kept, no assistant reply saved.
        self.assertEqual(Message.objects.filter(chat=self.chat, role=MessageRole.ASSISTANT).count(), 0)

    def test_groq_rate_limit_without_retry_after_header_still_returns_429(self):
        fake_response = mock.Mock()
        fake_response.headers = {}
        rate_limit_error = RateLimitError("rate limited", response=fake_response, body=None)
        with mock.patch("coach.views.LLMService") as MockLLM:
            MockLLM.return_value.get_response.side_effect = rate_limit_error
            response = self.client.post(f"/coach/chats/{self.chat.id}/messages/", {"content": "hello"})
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("try again in a moment", response.data["error"])

    def test_first_message_becomes_chat_title(self):
        with mock.patch("coach.views.LLMService") as MockLLM:
            MockLLM.return_value.get_response.return_value = "Sure, here's a plan..."
            self.client.post(f"/coach/chats/{self.chat.id}/messages/", {"content": "Give me a workout plan"})
        self.chat.refresh_from_db()
        self.assertEqual(self.chat.title, "Give me a workout plan")

    def test_cannot_message_other_users_chat(self):
        other = Account.objects.create_user(email="b@test.com", password="pass12345")
        other_chat = Chat.objects.create(user=other, title="Other's chat")
        response = self.client.post(f"/coach/chats/{other_chat.id}/messages/", {"content": "hi"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class DataCollectionServiceRoutinesTests(APITestCase):
    """
    Regression coverage for the bug where the coach's context only ever
    included completed TemplateHistory sessions, never saved
    WorkoutTemplate routines -- so a user who generated (or built) a
    routine but hadn't started a session from it yet got a coach that
    had no idea the routine existed.
    """

    def setUp(self):
        from workouts.models import TemplateExercise, WorkoutTemplate
        self.WorkoutTemplate = WorkoutTemplate
        self.TemplateExercise = TemplateExercise
        self.user = Account.objects.create_user(email="a@test.com", password="pass12345")

    def _service(self):
        from coach.services.data_collection_service import DataCollectionService
        return DataCollectionService(self.user)

    def test_no_routines_yet(self):
        summary = self._service().get_current_routines_summary()
        self.assertEqual(summary, "No saved routines yet.")

    def test_includes_generated_routine_and_its_exercises(self):
        template = self.WorkoutTemplate.objects.create(
            user=self.user, title="Push Day", is_generated=True, day_type="push",
        )
        self.TemplateExercise.objects.create(
            template=template, wger_exercise_id=1, exercise_name="Bench Press", target_sets=4, order=0,
        )
        self.TemplateExercise.objects.create(
            template=template, wger_exercise_id=2, exercise_name="Overhead Press", target_sets=3, order=1,
        )
        summary = self._service().get_current_routines_summary()
        self.assertIn("Push Day", summary)
        self.assertIn("AI-generated", summary)
        self.assertIn("Bench Press", summary)
        self.assertIn("4 sets", summary)

    def test_distinguishes_self_made_routines(self):
        self.WorkoutTemplate.objects.create(user=self.user, title="My Own Plan", is_generated=False)
        summary = self._service().get_current_routines_summary()
        self.assertIn("self-made", summary)

    def test_does_not_include_other_users_routines(self):
        other = Account.objects.create_user(email="b@test.com", password="pass12345")
        self.WorkoutTemplate.objects.create(user=other, title="Other's Plan", is_generated=False)
        summary = self._service().get_current_routines_summary()
        self.assertEqual(summary, "No saved routines yet.")

    def test_full_context_includes_routines_section(self):
        self.WorkoutTemplate.objects.create(user=self.user, title="Leg Day", is_generated=True, day_type="legs")
        context = self._service().get_full_context()
        self.assertIn("SAVED ROUTINES", context)
        self.assertIn("Leg Day", context)