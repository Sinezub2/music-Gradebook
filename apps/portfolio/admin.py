from django.contrib import admin
from .models import Achievement, MediaLink


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ("student", "title", "date")
    search_fields = ("student__username", "title")


@admin.register(MediaLink)
class MediaLinkAdmin(admin.ModelAdmin):
    list_display = ("student", "title", "media_type", "created_at")
    search_fields = ("student__username", "title", "url")
    list_filter = ("media_type",)
