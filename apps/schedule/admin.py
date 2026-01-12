from django.contrib import admin
from .models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "event_type", "start_datetime", "end_datetime", "course", "external_url", "created_by")
    list_filter = ("event_type", "course")
    search_fields = ("title", "description", "course__name", "created_by__username")
    filter_horizontal = ("participants",)
