from datetime import timedelta

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ProgressReport, ProgressReportSettings, ReportStatus
from .serializers import (
    GenerateReportSerializer,
    ProgressReportDetailSerializer,
    ProgressReportListSerializer,
    ProgressReportSettingsSerializer,
)
from .services.pdf_export import build_report_pdf
from .services.report_generation_service import ReportGenerationService

# A short spam guard, NOT the user's day_interval schedule -- day_interval
# is a preference for how often they *want* a report, and hard-blocking on
# it would fight the deliberate on-demand design (see GenerateReportView's
# docstring). This just stops accidental rapid double/triple-clicks from
# firing multiple real LLM calls and cluttering the report list with
# near-duplicates of the same window.
MIN_SECONDS_BETWEEN_GENERATIONS = 60

# How long an in-progress generation can hold the lock before we treat it
# as stale (e.g. the process crashed mid-generation and never cleared it)
# and let a new request through anyway, rather than being stuck locked out
# forever. Generation is one LLM call -- this is a generous multiple of how
# long that normally takes.
GENERATION_LOCK_TIMEOUT_SECONDS = 120


class ProgressReportListView(generics.ListAPIView):
    """GET /progress/reports/  -- "Generated Reports" list."""

    serializer_class = ProgressReportListSerializer

    def get_queryset(self):
        return ProgressReport.objects.filter(user=self.request.user)


class ProgressReportDetailView(generics.RetrieveDestroyAPIView):
    """GET /progress/reports/<id>/  -- full report view.
    DELETE /progress/reports/<id>/ -- remove a report (e.g. cleaning up
    a failed generation, or one made by mistake)."""

    serializer_class = ProgressReportDetailSerializer

    def get_queryset(self):
        return ProgressReport.objects.filter(user=self.request.user)


class ProgressReportPDFView(APIView):
    """
    GET /progress/reports/<id>/pdf/
    Renders the report as a downloadable PDF -- same content as the
    ReportDetail page (summary/feedback/takeaways/recommendations), for
    saving or sharing outside the app. Only available once a report has
    actually finished generating; a pending/failed report has no
    narrative content to export yet.
    """

    def get(self, request, pk):
        report = get_object_or_404(ProgressReport, id=pk, user=request.user)
        if report.status != ReportStatus.GENERATED:
            return Response(
                {"error": "Only a successfully generated report can be exported."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        pdf_bytes = build_report_pdf(report)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="progress-report-{report.report_number}.pdf"'
        return response


class GenerateReportView(APIView):
    """
    POST /progress/reports/generate/
    Body (optional): {"period_days": 7, "report_type": "short", "triggered_by": "manual"}
    Triggers generation for the last `period_days` days (defaults to the
    user's ProgressReportSettings.day_interval/report_type when omitted).
    This uses an explicit action instead of a Celery-scheduled midnight
    job -- simpler to run/demo without a task queue. "Interval-based"
    generation is driven the same way, just triggered client-side (see
    ProgressReportSettings.due_status()) rather than by a server clock;
    triggered_by="interval" additionally requires is_enabled so a client
    can't fire an "automatic" report while the user has that switched off.
    """

    def post(self, request):
        serializer = GenerateReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        settings_obj, _ = ProgressReportSettings.objects.get_or_create(user=request.user)

        if data["triggered_by"] == "interval" and not settings_obj.is_enabled:
            return Response(
                {"error": "Interval-based generation is turned off in report settings."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if settings_obj.last_generated_at:
            elapsed = (timezone.now() - settings_obj.last_generated_at).total_seconds()
            if elapsed < MIN_SECONDS_BETWEEN_GENERATIONS:
                wait_seconds = round(MIN_SECONDS_BETWEEN_GENERATIONS - elapsed)
                return Response(
                    {
                        "error": f"Please wait {wait_seconds}s before generating another report.",
                        "retry_after_seconds": wait_seconds,
                    },
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

        if settings_obj.generation_started_at:
            in_progress_for = (timezone.now() - settings_obj.generation_started_at).total_seconds()
            if in_progress_for < GENERATION_LOCK_TIMEOUT_SECONDS:
                # A generation is already running for this user (e.g. the
                # user navigated away and back before it finished, and the
                # frontend fired another auto-trigger). last_generated_at
                # alone can't catch this since it hasn't updated yet.
                wait_seconds = round(GENERATION_LOCK_TIMEOUT_SECONDS - in_progress_for)
                return Response(
                    {
                        "error": "A report is already being generated -- please wait for it to finish.",
                        "retry_after_seconds": wait_seconds,
                    },
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

        period_days = data.get("period_days") or settings_obj.day_interval
        report_type = data.get("report_type") or settings_obj.report_type

        period_end = timezone.localdate()
        period_start = period_end - timedelta(days=period_days - 1)

        try:
            service = ReportGenerationService()
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        settings_obj.generation_started_at = timezone.now()
        settings_obj.save(update_fields=["generation_started_at"])
        try:
            report = service.generate_report(
                user=request.user,
                period_start=period_start,
                period_end=period_end,
                report_type=report_type,
                triggered_by=data["triggered_by"],
            )
        finally:
            settings_obj.generation_started_at = None
            settings_obj.save(update_fields=["generation_started_at"])

        # Always 201: a ProgressReport row was genuinely created and
        # persisted here in every case (generate_report() never raises --
        # see its own try/except, which returns a status="failed" report
        # rather than letting an exception escape). Returning 502 for a
        # "failed" status used to make axios treat this as a rejected
        # request, so the frontend's error handler received the raw report
        # JSON instead of an {error: ...} shape and displayed the first
        # object key's value (the report's numeric id) as if it were an
        # error message. The frontend already checks report.status ===
        # "failed" on a successful response to show the real
        # generation_error -- that only works if we actually return 2xx.
        return Response(ProgressReportDetailSerializer(report).data, status=status.HTTP_201_CREATED)


class ProgressReportSettingsView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /progress/settings/  -- report interval/type preferences."""

    serializer_class = ProgressReportSettingsSerializer

    def get_object(self):
        obj, _ = ProgressReportSettings.objects.get_or_create(user=self.request.user)
        return obj