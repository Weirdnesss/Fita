import os
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from .models import Chat, Message, MessageRole
from .services.llm_service import LLMService
from .services.pain_guard import PAIN_MAX_TOKENS, is_pain_conversation, is_pain_message

Account = get_user_model()


class PainDetectionTests(SimpleTestCase):
    def test_pain_words_are_caught(self):
        for text in [
            "my shoulder hurts when I press",
            "nah i think my knee pain will go away, i wont go to the doctor",
            "I have a sharp pain in my lower back",
            "my wrist is swollen after push-ups",
            "feeling dizzy during cardio",
            "my joints are so stiff in the morning",
        ]:
            self.assertTrue(is_pain_message(text), text)

    def test_body_part_with_a_feeling_is_caught_without_the_word_pain(self):
        self.assertTrue(is_pain_message("ok, after a workout, my knees feel harder to move"))
        self.assertTrue(is_pain_message("my ankle feels weird on the stairs"))

    def test_normal_fitness_questions_are_not_caught(self):
        for text in [
            "how do I do a chest press",
            "show me back squat form",
            "what is a good protein intake",
            "give an extreme diet",
            "whats 9 + 10",
            "can you give an advanced workout",
            "what stretches help my hips open up",
        ]:
            self.assertFalse(is_pain_message(text), text)

    def test_empty_text_is_not_pain(self):
        self.assertFalse(is_pain_message(""))
        self.assertFalse(is_pain_message(None))

    def test_continue_after_a_pain_message_stays_in_pain_mode(self):
        self.assertTrue(is_pain_conversation(["please continue", "my knee hurts"]))
        self.assertTrue(is_pain_conversation(["Go on.", "my knee hurts"]))

    def test_continue_after_a_normal_message_is_not_pain_mode(self):
        self.assertFalse(is_pain_conversation(["please continue", "give me a meal idea"]))
        self.assertFalse(is_pain_conversation(["continue"]))
        self.assertFalse(is_pain_conversation([]))

    def test_a_later_normal_question_leaves_pain_mode(self):
        self.assertFalse(is_pain_conversation(["what should I eat for lunch", "my knee hurts"]))


class PainModeResponseTests(TestCase):
    def setUp(self):
        self.user = Account.objects.create_user(email="pain@test.com", password="pass12345")
        self.chat = Chat.objects.create(user=self.user, title="t")
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            self.service = LLMService()
        fake = mock.Mock()
        fake.choices = [mock.Mock(message=mock.Mock(content="ok"), finish_reason="stop")]
        self.service.client = mock.Mock()
        self.service.client.chat.completions.create.return_value = fake

    def ask(self, text, detail):
        Message.objects.create(chat=self.chat, role=MessageRole.USER, content=text)
        self.service.get_response(self.chat, detail=detail)
        return self.service.client.chat.completions.create.call_args.kwargs

    def test_pain_message_overrides_detailed_mode(self):
        kwargs = self.ask("my knee hurts after squats", "detailed")
        system = kwargs["messages"][0]["content"]
        self.assertIn("PAIN OR INJURY MODE", system)
        self.assertNotIn("RESPONSE MODE: DETAILED", system)
        self.assertEqual(kwargs["max_completion_tokens"], PAIN_MAX_TOKENS)
        self.assertIn("Reply under 70 words", kwargs["messages"][-1]["content"])

    def test_normal_message_keeps_detailed_mode(self):
        kwargs = self.ask("explain progressive overload", "detailed")
        system = kwargs["messages"][0]["content"]
        self.assertNotIn("PAIN OR INJURY MODE", system)
        self.assertIn("RESPONSE MODE: DETAILED", system)
        self.assertNotEqual(kwargs["max_completion_tokens"], PAIN_MAX_TOKENS)

    def test_continue_after_pain_stays_short(self):
        Message.objects.create(chat=self.chat, role=MessageRole.USER, content="my knee hurts")
        Message.objects.create(chat=self.chat, role=MessageRole.ASSISTANT, content="Rest it.")
        kwargs = self.ask("please continue", "detailed")
        self.assertIn("PAIN OR INJURY MODE", kwargs["messages"][0]["content"])
