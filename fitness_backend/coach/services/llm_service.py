"""
Wraps the chat LLM call. Uses the `openai` SDK pointed at Groq's
OpenAI-compatible endpoint (https://api.groq.com/openai/v1) -- Groq's
free tier needs no credit card and this SDK path means swapping to
OpenAI, or any other OpenAI-compatible provider, later is a one-line
change (just the base_url and model name).
"""

import os
from pathlib import Path

from openai import OpenAI

from .data_collection_service import DataCollectionService

PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "system_prompt.txt"
DEFAULT_MODEL = "openai/gpt-oss-120b"


class LLMService:
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY environment variable is not set. "
                "Get a free key at https://console.groq.com"
            )
        self.client = OpenAI(
            api_key=api_key,
            base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
        )
        self.model = os.getenv("GROQ_MODEL", DEFAULT_MODEL)

    def _build_system_prompt(self, user):
        base_prompt = PROMPT_FILE.read_text(encoding="utf-8").strip()
        context = DataCollectionService(user).get_full_context()
        return f"{base_prompt}\n\n{context}"

    def get_response(self, chat):
        """
        chat: a Chat instance with related `messages` already saved
        (including the latest user message). Returns the assistant's
        reply text.
        """
        messages = [{"role": "system", "content": self._build_system_prompt(chat.user)}]

        # Cap history to keep the context window and Groq's per-minute
        # token limits under control on the free tier.
        recent_messages = chat.messages.order_by("-created_at")[:15]
        for msg in reversed(list(recent_messages)):
            messages.append({"role": msg.role, "content": msg.content})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_completion_tokens=1536,
            temperature=0.7,
            reasoning_effort="low",
        )
        choice = response.choices[0]
        reply = choice.message.content
        if choice.finish_reason == "length":
            reply += "\n\n[Response was cut short -- ask me to continue if you'd like the rest.]"
        return reply
