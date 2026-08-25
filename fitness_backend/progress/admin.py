from django.contrib import admin

from .models import ProgressReport, ProgressReportSettings

admin.site.register(ProgressReport)
admin.site.register(ProgressReportSettings)
