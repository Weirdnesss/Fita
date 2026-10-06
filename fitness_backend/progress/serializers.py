from rest_framework import serializers

from .models import (
    MAX_DAY_INTERVAL,
    MIN_DAY_INTERVAL,
    ProgressReport,
    ProgressReportSettings,
)


class ProgressReportListSerializer(serializers.ModelSerializer):
    """For the 'Generated Reports' list -- lighter payload."""

    class Meta:
        model = ProgressReport
        fields = ["id", "report_number", "period_start", "period_end", "status", "triggered_by", "progress_summary", "created_at"]


class ProgressReportDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProgressReport
        fields = [
            "id",
            "report_number",
            "period_start",
            "period_end",
            "report_type",
            "status",
            "triggered_by",
            "progress_summary",
            "workout_feedback",
            "nutrition_feedback",
            "key_takeaways",
            "rule_based_insights",
            "generation_error",
            "created_at",
        ]


class ProgressReportSettingsSerializer(serializers.ModelSerializer):
    day_interval = serializers.IntegerField(min_value=MIN_DAY_INTERVAL, max_value=MAX_DAY_INTERVAL)
    due_status = serializers.SerializerMethodField()
    next_generation_date = serializers.SerializerMethodField()
    has_new_data = serializers.SerializerMethodField()

    class Meta:
        model = ProgressReportSettings
        fields = [
            "day_interval",
            "report_type",
            "is_enabled",
            "last_generated_at",
            "due_status",
            "next_generation_date",
            "has_new_data",
        ]
        read_only_fields = ["last_generated_at", "due_status", "next_generation_date", "has_new_data"]

    def get_due_status(self, obj):
        return obj.due_status()

    def get_next_generation_date(self, obj):
        return obj.next_generation_date()

    def get_has_new_data(self, obj):
        return obj.has_new_data()


class GenerateReportSerializer(serializers.Serializer):
    """POST body for triggering report generation."""

    period_days = serializers.IntegerField(required=False, min_value=MIN_DAY_INTERVAL, max_value=MAX_DAY_INTERVAL)
    report_type = serializers.ChoiceField(choices=["short", "detailed"], required=False)
    triggered_by = serializers.ChoiceField(choices=["manual", "interval"], required=False, default="manual")