from rest_framework import serializers

from .models import ProgressReport, ProgressReportSettings


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
    day_interval = serializers.IntegerField(min_value=1, max_value=90)
    due_status = serializers.SerializerMethodField()
    next_generation_date = serializers.SerializerMethodField()

    class Meta:
        model = ProgressReportSettings
        fields = [
            "day_interval",
            "report_type",
            "is_enabled",
            "last_generated_at",
            "due_status",
            "next_generation_date",
        ]
        read_only_fields = ["last_generated_at", "due_status", "next_generation_date"]

    def get_due_status(self, obj):
        return obj.due_status()

    def get_next_generation_date(self, obj):
        return obj.next_generation_date()


class GenerateReportSerializer(serializers.Serializer):
    """POST body for triggering report generation."""

    period_days = serializers.IntegerField(required=False, min_value=1, max_value=90)
    report_type = serializers.ChoiceField(choices=["short", "detailed"], required=False)
    triggered_by = serializers.ChoiceField(choices=["manual", "interval"], required=False, default="manual")