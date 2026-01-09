from django.contrib import admin
from .models import Lesson, LessonReport


class LessonReportInline(admin.TabularInline):
    model = LessonReport
    extra = 0
    autocomplete_fields = ("student",)
    fields = ("student", "text", "media_url", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("course", "date", "topic", "created_by")
    list_filter = ("course", "date")
    search_fields = ("topic", "course__name", "created_by__username")
    inlines = [LessonReportInline]


@admin.register(LessonReport)
class LessonReportAdmin(admin.ModelAdmin):
    list_display = ("lesson", "student", "created_at")
    list_filter = ("lesson__course",)
    search_fields = ("lesson__topic", "student__username")
