from rest_framework import serializers

from .models import ProgressReport, ProgressReportSettings


class ProgressReportListSerializer(serializers.ModelSerializer):
    """For the 'Generated Reports' list -- lighter payload."""

    class Meta:
        model = ProgressReport
        fields = ["id", "period_start", "period_end", "status", "progress_summary", "created_at"]


class ProgressReportDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProgressReport
        fields = [
            "id",
            "period_start",
            "period_end",
            "report_type",
            "status",
            "progress_summary",
            "workout_feedback",
            "nutrition_feedback",
            "key_takeaways",
            "rule_based_insights",
            "generation_error",
            "created_at",
        ]


class ProgressReportSettingsSerializer(serializers.ModelSerializer):
    day_interval = serializers.IntegerField(min_value=1, max_value=90)

    class Meta:
        model = ProgressReportSettings
        fields = ["day_interval", "report_type", "is_enabled", "last_generated_at"]
        read_only_fields = ["last_generated_at"]


class GenerateReportSerializer(serializers.Serializer):
    """POST body for triggering report generation."""

    period_days = serializers.IntegerField(required=False, min_value=1, max_value=90)
    report_type = serializers.ChoiceField(choices=["short", "detailed"], required=False, default="short")
