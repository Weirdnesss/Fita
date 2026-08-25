from django.conf import settings
from django.db import models
from django.utils import timezone


class ReportType(models.TextChoices):
    SHORT = "short", "Short"
    DETAILED = "detailed", "Detailed"


class ReportStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    GENERATED = "generated", "Generated"
    FAILED = "failed", "Failed"


class ProgressReport(models.Model):
    """
    A generated progress report. Combines rule-based analysis (stored
    verbatim in rule_based_insights, for transparency/audit) with an
    LLM-generated narrative in the text fields below.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="progress_reports"
    )
    period_start = models.DateField()
    period_end = models.DateField()
    report_type = models.CharField(
        max_length=10, choices=ReportType.choices, default=ReportType.SHORT
    )
    status = models.CharField(
        max_length=10, choices=ReportStatus.choices, default=ReportStatus.PENDING
    )

    progress_summary = models.TextField(blank=True)
    workout_feedback = models.TextField(blank=True)
    nutrition_feedback = models.TextField(blank=True)
    key_takeaways = models.TextField(blank=True)

    # Raw rule-based analyzer output -- kept alongside the narrative so
    # the hybrid approach (rules -> LLM) is inspectable, not just the
    # LLM's prose summary of it.
    rule_based_insights = models.JSONField(default=dict, blank=True)

    generation_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Report #{self.id} for {self.user.email} ({self.period_start} - {self.period_end})"


class ProgressReportSettings(models.Model):
    """Per-user schedule/type preference for report generation."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="report_settings"
    )
    day_interval = models.PositiveSmallIntegerField(default=7)
    report_type = models.CharField(
        max_length=10, choices=ReportType.choices, default=ReportType.SHORT
    )
    is_enabled = models.BooleanField(default=True)
    last_generated_at = models.DateTimeField(null=True, blank=True)

    def next_generation_date(self):
        if not self.last_generated_at:
            return timezone.now()
        return self.last_generated_at + timezone.timedelta(days=self.day_interval)

    def __str__(self):
        return f"ReportSettings<{self.user.email}>"
