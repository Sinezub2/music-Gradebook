from django.contrib import admin
from .models import Lesson, LessonReport, LessonSlot, StudentSchedule


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


@admin.register(StudentSchedule)
class StudentScheduleAdmin(admin.ModelAdmin):
    list_display = ("teacher", "student", "course", "weekday", "start_time", "active")
    list_filter = ("teacher", "course", "weekday", "active")
    search_fields = ("teacher__username", "student__username", "course__name")


@admin.register(LessonSlot)
class LessonSlotAdmin(admin.ModelAdmin):
    list_display = ("teacher", "student", "course", "scheduled_date", "start_time", "status", "attendance_status")
    list_filter = ("teacher", "course", "status", "attendance_status")
    search_fields = ("teacher__username", "student__username", "course__name")
