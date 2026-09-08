from django.urls import path

from .views import (
    GenerateReportView,
    ProgressReportDetailView,
    ProgressReportListView,
    ProgressReportPDFView,
    ProgressReportSettingsView,
)

urlpatterns = [
    path("reports/", ProgressReportListView.as_view(), name="report-list"),
    path("reports/generate/", GenerateReportView.as_view(), name="report-generate"),
    path("reports/<int:pk>/", ProgressReportDetailView.as_view(), name="report-detail"),
    path("reports/<int:pk>/pdf/", ProgressReportPDFView.as_view(), name="report-pdf"),
    path("settings/", ProgressReportSettingsView.as_view(), name="report-settings"),
]