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


class TriggeredBy(models.TextChoices):
    MANUAL = "manual", "Manual"
    INTERVAL = "interval", "Interval"


class ProgressReport(models.Model):
    """
    A generated progress report. Combines rule-based analysis (stored
    verbatim in rule_based_insights, for transparency/audit) with an
    LLM-generated narrative in the text fields below.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="progress_reports"
    )
    # A per-user display number ("Report #3"), separate from the DB id.
    # The id is a global auto-increment shared across every user's rows,
    # so showing it as "Report #10" to a user with only 2 reports was
    # misleading. This is assigned once at creation and never reused,
    # so deleting an older report leaves a gap rather than renumbering
    # everything after it.
    # default=1 exists only to satisfy existing-row backfill during the
    # migration -- generate_report() always sets an explicit value, so
    # this default is never actually used for new rows.
    report_number = models.PositiveIntegerField(default=1)
    period_start = models.DateField()
    period_end = models.DateField()
    report_type = models.CharField(
        max_length=10, choices=ReportType.choices, default=ReportType.SHORT
    )
    status = models.CharField(
        max_length=10, choices=ReportStatus.choices, default=ReportStatus.PENDING
    )
    triggered_by = models.CharField(
        max_length=10, choices=TriggeredBy.choices, default=TriggeredBy.MANUAL
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
        constraints = [
            models.UniqueConstraint(fields=["user", "report_number"], name="unique_report_number_per_user")
        ]

    def __str__(self):
        return f"Report #{self.report_number} for {self.user.email} ({self.period_start} - {self.period_end})"


class ProgressReportSettings(models.Model):
    """Per-user schedule/type preference for report generation."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="report_settings"
    )
    day_interval = models.PositiveSmallIntegerField(default=7)
    report_type = models.CharField(
        max_length=10, choices=ReportType.choices, default=ReportType.SHORT
    )
    is_enabled = models.BooleanField(
        default=True,
        help_text="Whether interval-based (automatic) report generation is allowed.",
    )
    last_generated_at = models.DateTimeField(null=True, blank=True)
    # Set the instant a generation call starts, cleared when it ends
    # (success or failure). This is the actual concurrency guard --
    # last_generated_at alone can't stop a second request that arrives
    # while the first is still running, since it only updates once
    # generation *finishes*. See GenerateReportView.
    generation_started_at = models.DateTimeField(null=True, blank=True)

    def next_generation_date(self):
        if not self.last_generated_at:
            return timezone.now()
        return self.last_generated_at + timezone.timedelta(days=self.day_interval)

    def is_schedule_due(self):
        """Whether enough time has passed per is_enabled (allow interval-based
        generation)/day_interval, with no regard for whether there's anything
        to report on yet."""
        return self.is_enabled and timezone.now() >= self.next_generation_date()

    def has_new_data(self):
        """Whether there's nutrition or workout data logged in the window a
        new report would cover (the same window GenerateReportView uses:
        the last day_interval days). Local import avoids a hard dependency
        between apps at load time."""
        from coach.services.data_collection_service import DataCollectionService

        today = timezone.localdate()
        period_start = today - timezone.timedelta(days=self.day_interval - 1)
        service = DataCollectionService(self.user)
        nutrition = service.get_structured_nutrition_data(period_start, today)
        workout = service.get_structured_workout_data(period_start, today)
        return nutrition.get("has_data", False) or workout.get("has_data", False)

    def due_status(self):
        """"not_due" | "due" | "due_no_data" -- the single field the UI
        needs to decide whether to show a "due" banner, a "nothing new
        to report on" banner, or nothing."""
        if not self.is_schedule_due():
            return "not_due"
        return "due" if self.has_new_data() else "due_no_data"

    def __str__(self):
        return f"ReportSettings<{self.user.email}>"