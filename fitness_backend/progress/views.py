from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ProgressReport, ProgressReportSettings
from .serializers import (
    GenerateReportSerializer,
    ProgressReportDetailSerializer,
    ProgressReportListSerializer,
    ProgressReportSettingsSerializer,
)
from .services.report_generation_service import ReportGenerationService

# A short spam guard, NOT the user's day_interval schedule -- day_interval
# is a preference for how often they *want* a report, and hard-blocking on
# it would fight the deliberate on-demand design (see GenerateReportView's
# docstring). This just stops accidental rapid double/triple-clicks from
# firing multiple real LLM calls and cluttering the report list with
# near-duplicates of the same window.
MIN_SECONDS_BETWEEN_GENERATIONS = 60


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


class GenerateReportView(APIView):
    """
    POST /progress/reports/generate/
    Body (optional): {"period_days": 7, "report_type": "short"}
    Triggers on-demand generation for the last `period_days` days
    (defaults to the user's ProgressReportSettings.day_interval).
    This uses an explicit action instead of a Celery-scheduled midnight
    job -- simpler to run/demo without a task queue, while
    ProgressReportSettings.next_generation_date() is still
    available if you want to add scheduling later.
    """

    def post(self, request):
        serializer = GenerateReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        settings_obj, _ = ProgressReportSettings.objects.get_or_create(user=request.user)

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

        period_days = data.get("period_days") or settings_obj.day_interval
        report_type = data.get("report_type") or settings_obj.report_type

        period_end = timezone.localdate()
        period_start = period_end - timedelta(days=period_days - 1)

        try:
            service = ReportGenerationService()
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        report = service.generate_report(
            user=request.user,
            period_start=period_start,
            period_end=period_end,
            report_type=report_type,
        )

        response_status = (
            status.HTTP_201_CREATED if report.status == "generated" else status.HTTP_502_BAD_GATEWAY
        )
        return Response(ProgressReportDetailSerializer(report).data, status=response_status)


class ProgressReportSettingsView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /progress/settings/  -- report interval/type preferences."""

    serializer_class = ProgressReportSettingsSerializer

    def get_object(self):
        obj, _ = ProgressReportSettings.objects.get_or_create(user=self.request.user)
        return obj