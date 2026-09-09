from django.contrib import admin

from .models import Resource


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ["title", "category", "source", "created_at"]
    list_filter = ["category"]
    search_fields = ["title", "summary"]