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
from .pain_guard import PAIN_MAX_TOKENS, PAIN_REMINDER, PAIN_SYSTEM_BLOCK, is_pain_conversation

PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "system_prompt.txt"
DEFAULT_MODEL = "openai/gpt-oss-120b"

# The base prompt file holds the short-answer rules (the default). "detailed"
# appends an override block, so the user's choice only changes length/style:
# safety rules, the numbers rule, and app-feature redirects always stay in force.
#
# "reminder" is attached to the user's latest message at request time only
# (never saved). Chat history is sent to the model too, and earlier replies
# in the other style act like examples it copies -- so a system-prompt
# instruction alone takes a message or two to win after the user switches.
# A reminder right next to the newest question is the most recent thing the
# model reads, so the switch takes effect immediately.
DEFAULT_DETAIL = "short"
RESPONSE_MODES = {
    "short": {
        "max_tokens": 800,
        "instructions": "",
        "reminder": (
            "[Style for this reply: SHORT. Answer in 2-4 sentences, about 80 words at most, "
            "with the main point first. Ignore the length of your earlier replies in this chat.]"
        ),
    },
    "detailed": {
        "max_tokens": 700,
        "instructions": (
            "## RESPONSE MODE: DETAILED\n"
            "The user has chosen detailed explanations. This replaces the length and style "
            "limits in \"How to respond\" (the 80/150-word targets, the 2-4 sentence guideline, "
            "the one-issue limit, and the no-headings rule). Explain thoroughly, up to about "
            "300 words: cover the reasons behind the advice, give examples where they help, "
            "and use short paragraphs or bullet lists to keep it readable. "
            "Never exceed 300 words, even for complex questions: cut lower-priority points instead of running long. "
            "Keep the safety rules, the scope and beginner-level rules, the rule about only using numbers from the user's data, "
            "and the app-feature redirects exactly as written."
        ),
        "reminder": (
            "[Style for this reply: DETAILED. Explain thoroughly, up to about 300 words, with the "
            "reasons behind the advice and examples where they help. Ignore the brevity of your "
            "earlier replies in this chat. Hard limit: 300 words. Safety, scope, beginner-level and use-only-given-numbers rules still apply.]"
        ),
    },
}


def normalize_detail(value):
    """Whitelist the client-supplied value; anything unknown falls back to the default."""
    return value if value in RESPONSE_MODES else DEFAULT_DETAIL


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

    def _build_system_prompt(self, user, detail=DEFAULT_DETAIL, pain_mode=False):
        base_prompt = PROMPT_FILE.read_text(encoding="utf-8").strip()
        context = DataCollectionService(user).get_full_context()
        mode_block = RESPONSE_MODES[detail]["instructions"]
        parts = [base_prompt, context]
        if mode_block:
            # Last, so it's the freshest instruction in the system prompt.
            parts.append(mode_block)
        if pain_mode:
            parts.append(PAIN_SYSTEM_BLOCK)
        return "\n\n".join(parts)

    def get_response(self, chat, detail=DEFAULT_DETAIL):
        """
        chat: a Chat instance with related `messages` already saved
        (including the latest user message). detail: "short" | "detailed".
        Returns the assistant's reply text.
        """
        detail = normalize_detail(detail)
        # Rule-based guard: pain or injury talk always gets a short, fixed-shape
        # reply, whatever the Detailed setting says (see pain_guard.py).
        recent_user_texts = [
            m.content for m in chat.messages.filter(role="user").order_by("-created_at")[:2]
        ]
        pain_mode = is_pain_conversation(recent_user_texts)
        if pain_mode:
            detail = "short"
        messages = [{"role": "system", "content": self._build_system_prompt(chat.user, detail, pain_mode)}]

        # Cap history to keep the context window and Groq's per-minute
        # token limits under control on the free tier -- gpt-oss-120b's
        # free tier is 8,000 TPM, and system prompt + context + a long
        # completion already eat a meaningful chunk of that on their
        # own, so chat history (the one open-ended, unbounded input
        # here) is kept relatively tight rather than the more common
        # ~20-30 message window other apps might use.
        recent_messages = chat.messages.order_by("-created_at")[:10]
        for msg in reversed(list(recent_messages)):
            messages.append({"role": msg.role, "content": msg.content})

        # Attach the style reminder to the newest user message, in this
        # request only -- the saved message in the database is untouched.
        if messages[-1]["role"] == "user":
            messages[-1] = {
                "role": "user",
                "content": f"{messages[-1]['content']}\n\n{PAIN_REMINDER if pain_mode else RESPONSE_MODES[detail]['reminder']}",
            }

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_completion_tokens=PAIN_MAX_TOKENS if pain_mode else RESPONSE_MODES[detail]["max_tokens"],
            temperature=0.7,
            reasoning_effort="low",
        )
        choice = response.choices[0]
        reply = choice.message.content
        if choice.finish_reason == "length":
            reply += "\n\n[Response was cut short -- ask me to continue if you'd like the rest.]"
        return reply