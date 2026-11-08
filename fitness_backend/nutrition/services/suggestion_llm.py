"""
LLM step of the suggestion features: choose and explain, never invent.

The model receives rule-built candidates (single foods, or whole plates), each
with an integer id, and must answer with ids from that list plus a short
reason. Anything it returns that isn't a real candidate id is dropped, and if
too little survives the caller falls back to the rule-based reasons. The model
never supplies food names or numbers; those always come from the database.

Uses the same Groq/OpenAI-compatible setup as coach and progress.
"""

import json
import logging
import os

from openai import OpenAI

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "openai/gpt-oss-120b"
MAX_REASON_CHARS = 160
MIN_VALID_PICKS = 2

_RULES = """- Choose ONLY from the candidates, by their integer id. Never mention or suggest a food that is not in the list.
- Do not change, recalculate or invent numbers. If you mention a number, copy it from the candidate.
- Prefer variety and options that suit the meal.
- For each pick, write one short, friendly reason (max 18 words) tied to the user's remaining macros.
- No medical claims, no weight-loss promises, no moral language about food."""

SYSTEM_PROMPT = f"""You help gym beginners in the Philippines choose what to eat next in a fitness app.

You are given the user's remaining calories and macros for today, the meal they are planning, and a list of CANDIDATE foods. Each candidate has an integer "id", an amount, and its calories/protein/carbs/fat for that amount. The candidates are already roughly ranked best-first.

Rules:
{_RULES}

Reply with JSON only, in exactly this shape:
{{"suggestions": [{{"food_id": 123, "reason": "..."}}]}}"""

MEAL_SYSTEM_PROMPT = f"""You help gym beginners in the Philippines choose what to eat next in a fitness app.

You are given the user's remaining calories and macros for today, the meal they are planning, and a list of CANDIDATE MEALS. Each meal has an integer "id", a few foods with amounts, and its total calories/protein/carbs/fat. The meals are already roughly ranked best-first.

Rules:
{_RULES}
- Refer to a meal by its foods (for example "the chicken and rice plate"); never rename or invent foods.

Reply with JSON only, in exactly this shape:
{{"meals": [{{"meal_id": 0, "reason": "..."}}]}}"""


class SuggestionExplainer:
    def __init__(self, client=None, model=None):
        if client is None:
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise ValueError("GROQ_API_KEY environment variable is not set.")
            client = OpenAI(
                api_key=api_key,
                base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            )
        self.client = client
        self.model = model or os.getenv("GROQ_MODEL", DEFAULT_MODEL)

    @staticmethod
    def _remaining_payload(remaining):
        return {
            "calories": round(remaining.calories),
            "protein_g": round(remaining.protein_g),
            "carbs_g": round(remaining.carbs_g),
            "fat_g": round(remaining.fat_g),
        }

    def _ask(self, system_prompt, payload, list_key, max_tokens):
        """One LLM call; returns the model's list under `list_key`, or None if the answer is unusable."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload)},
            ],
            max_completion_tokens=max_tokens,
            temperature=0.4,
            reasoning_effort="low",
            response_format={"type": "json_object"},
        )
        choice = response.choices[0]
        if choice.finish_reason == "length":
            logger.warning("Suggestion LLM response truncated; using rule-based reasons")
            return None

        try:
            raw_picks = json.loads(choice.message.content)[list_key]
        except (json.JSONDecodeError, TypeError, KeyError):
            logger.warning("Suggestion LLM returned unusable JSON; using rule-based reasons")
            return None
        return raw_picks if isinstance(raw_picks, list) else None

    @staticmethod
    def _collect(raw_picks, id_key, by_id, limit):
        """Keep picks with a real, unseen id and a non-blank reason, in the model's order."""
        picks, seen = [], set()
        for item in raw_picks:
            if not isinstance(item, dict):
                continue
            pick_id, reason = item.get(id_key), item.get("reason")
            # bool is an int subclass in Python; json `true` must not pass as id 1
            if isinstance(pick_id, bool) or not isinstance(pick_id, int):
                continue
            if pick_id not in by_id or pick_id in seen:
                continue  # hallucinated or duplicate id
            if not isinstance(reason, str) or not reason.strip():
                continue
            seen.add(pick_id)
            picks.append((by_id[pick_id], reason.strip()[:MAX_REASON_CHARS]))
            if len(picks) >= limit:
                break
        return picks if len(picks) >= MIN_VALID_PICKS else None

    def pick_and_explain(self, meal_type, remaining, candidates, limit):
        """
        candidates: list of food_suggester.Suggestion.
        Returns a list of (Suggestion, reason) in the model's order, or None if the model's answer wasn't usable.
        """
        payload = {
            "meal": meal_type,
            "remaining_today": self._remaining_payload(remaining),
            "pick_up_to": limit,
            "candidates": [
                {
                    "id": c.food.id,
                    "food": c.food.name,
                    "amount": c.amount_label,
                    "calories": c.calories,
                    "protein_g": c.protein_g,
                    "carbs_g": c.carbs_g,
                    "fat_g": c.fat_g,
                }
                for c in candidates
            ],
        }
        raw = self._ask(SYSTEM_PROMPT, payload, "suggestions", 700)
        if raw is None:
            return None
        return self._collect(raw, "food_id", {c.food.id: c for c in candidates}, limit)

    def pick_meals(self, meal_type, remaining, plates, limit):
        """
        plates: list of meal_builder.Plate; the id the model sees is the plate's index in this list.
        Returns a list of (Plate, reason) in the model's order, or None if the model's answer wasn't usable.
        """
        payload = {
            "meal": meal_type,
            "remaining_today": self._remaining_payload(remaining),
            "pick_up_to": limit,
            "candidate_meals": [
                {
                    "id": index,
                    "foods": [{"food": i.food.name, "amount": i.amount_label} for i in plate.items],
                    "calories": plate.calories,
                    "protein_g": plate.protein_g,
                    "carbs_g": plate.carbs_g,
                    "fat_g": plate.fat_g,
                }
                for index, plate in enumerate(plates)
            ],
        }
        raw = self._ask(MEAL_SYSTEM_PROMPT, payload, "meals", 900)
        if raw is None:
            return None
        return self._collect(raw, "meal_id", dict(enumerate(plates)), limit)
