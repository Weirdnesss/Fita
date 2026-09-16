import os
from unittest import mock

from django.contrib.auth import get_user_model
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