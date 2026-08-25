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


class ProgressReportListView(generics.ListAPIView):
    """GET /progress/reports/  -- "Generated Reports" list."""

    serializer_class = ProgressReportListSerializer

    def get_queryset(self):
        return ProgressReport.objects.filter(user=self.request.user)


class ProgressReportDetailView(generics.RetrieveAPIView):
    """GET /progress/reports/<id>/  -- full report view."""

    serializer_class = ProgressReportDetailSerializer

    def get_queryset(self):
        return ProgressReport.objects.filter(user=self.request.user)


class GenerateReportView(APIView):
    """
    POST /progress/reports/generate/
    Body (optional): {"period_days": 7, "report_type": "short"}
    Triggers on-demand generation for the last `period_days` days
    (defaults to the user's ProgressReportSettings.day_interval).
    This replaces the original thesis's Celery-scheduled midnight job
    with an explicit action -- simpler to run/demo without a task queue,
    while ProgressReportSettings.next_generation_date() is still
    available if you want to add scheduling later.
    """

    def post(self, request):
        serializer = GenerateReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        settings_obj, _ = ProgressReportSettings.objects.get_or_create(user=request.user)
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
