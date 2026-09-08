"""
Ties together the hybrid progress-report pipeline:
  1. Collect structured nutrition/workout/weight data for the period
     (coach.services.DataCollectionService).
  2. Run it through RuleBasedAnalyzer for threshold-based insights.
  3. Hand both the raw data and the rule-based insights to the LLM,
     which writes the narrative -- constrained to a JSON shape so it's
     no longer relying on fragile text-delimiter parsing.
"""

import json
import os
from pathlib import Path

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from openai import OpenAI

from coach.services.data_collection_service import DataCollectionService
from progress.models import ProgressReport, ProgressReportSettings, ReportStatus
from progress.services.rule_based_analyzer import RuleBasedAnalyzer

PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "report_prompt.txt"
DEFAULT_MODEL = "openai/gpt-oss-120b"


class ReportGenerationService:
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

    def generate_report(self, user, period_start, period_end, report_type="short", triggered_by="manual"):
        with transaction.atomic():
            # select_for_update locks this user's existing report rows for
            # the duration of the transaction, so two near-simultaneous
            # generate calls for the same user can't both read the same
            # max and pick the same report_number.
            last_number = (
                ProgressReport.objects.select_for_update()
                .filter(user=user)
                .aggregate(Max("report_number"))["report_number__max"]
                or 0
            )
            report = ProgressReport.objects.create(
                user=user,
                report_number=last_number + 1,
                period_start=period_start,
                period_end=period_end,
                report_type=report_type,
                status=ReportStatus.PENDING,
                triggered_by=triggered_by,
            )

        try:
            data_service = DataCollectionService(user)
            nutrition_data = data_service.get_structured_nutrition_data(period_start, period_end)
            workout_data = data_service.get_structured_workout_data(period_start, period_end)
            weight_data = data_service.get_structured_weight_data(period_start, period_end)

            if not nutrition_data.get("has_data") and not workout_data.get("has_data"):
                report.status = ReportStatus.FAILED
                report.generation_error = "Insufficient data: no nutrition or workout logs found for this period"
                report.save()
                return report

            insights = RuleBasedAnalyzer().analyze_all(nutrition_data, workout_data, weight_data)
            report.rule_based_insights = insights

            content = self._generate_narrative(
                user, nutrition_data, workout_data, weight_data, insights, report_type
            )

            report.progress_summary = content.get("progress_summary", "")
            report.workout_feedback = content.get("workout_feedback", "")
            report.nutrition_feedback = content.get("nutrition_feedback", "")
            report.key_takeaways = content.get("key_takeaways", "")
            report.status = ReportStatus.GENERATED
            report.save()

            settings_obj, _ = ProgressReportSettings.objects.get_or_create(user=user)
            settings_obj.last_generated_at = timezone.now()
            settings_obj.save(update_fields=["last_generated_at"])

            return report

        except Exception as exc:
            report.status = ReportStatus.FAILED
            report.generation_error = str(exc)
            report.save()
            return report

    def _generate_narrative(self, user, nutrition_data, workout_data, weight_data, insights, report_type):
        base_prompt = PROMPT_FILE.read_text(encoding="utf-8").strip()

        if report_type == "short":
            replacements = {
                "{LENGTH_MODE_INSTRUCTION}": (
                    "Write a SHORT report. Every field below should be brief -- "
                    "hit the key point and stop, don't elaborate."
                ),
                "{PROGRESS_SUMMARY_LENGTH}": "2-3 sentences",
                "{WORKOUT_FEEDBACK_LENGTH}": "1-2 sentences",
                "{NUTRITION_FEEDBACK_LENGTH}": "1-2 sentences",
                "{KEY_TAKEAWAYS_LENGTH}": "2-3 short bullet-style sentences",
            }
        else:
            replacements = {
                "{LENGTH_MODE_INSTRUCTION}": (
                    "Write a DETAILED report. Every field below should be thorough -- "
                    "cite specific numbers from the data, explain the 'why' behind each "
                    "observation, and don't compress multiple points into one sentence."
                ),
                "{PROGRESS_SUMMARY_LENGTH}": "5-7 sentences",
                "{WORKOUT_FEEDBACK_LENGTH}": "2-3 full paragraphs",
                "{NUTRITION_FEEDBACK_LENGTH}": "2-3 full paragraphs",
                "{KEY_TAKEAWAYS_LENGTH}": "5-7 detailed bullet-style sentences, each with brief reasoning",
            }

        system_prompt = base_prompt
        for placeholder, value in replacements.items():
            system_prompt = system_prompt.replace(placeholder, value)

        profile_summary = DataCollectionService(user).get_profile_summary()
        user_prompt = (
            f"=== USER PROFILE ===\n{profile_summary}\n\n"
            f"=== NUTRITION DATA ===\n{json.dumps(nutrition_data, indent=2)}\n\n"
            f"=== WORKOUT DATA ===\n{json.dumps(workout_data, indent=2)}\n\n"
            f"=== WEIGHT DATA ===\n{json.dumps(weight_data, indent=2)}\n\n"
            f"=== RULE-BASED INSIGHTS ===\n{json.dumps(insights, indent=2)}"
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_completion_tokens=3000 if report_type == "detailed" else 1600,
            temperature=0.6,
            reasoning_effort="low",
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        if response.choices[0].finish_reason == "length":
            # Truncated mid-JSON is very likely unparseable -- fail loudly
            # via the except branch below rather than silently returning
            # a partial/garbled report.
            raise ValueError(
                "LLM response was cut off before completion (finish_reason=length). "
                "Try increasing max_completion_tokens or using report_type='short'."
            )
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            # Model didn't return clean JSON -- fall back to dumping the
            # raw text into progress_summary rather than losing the report.
            return {"progress_summary": raw or "Report generation returned an unexpected format."}