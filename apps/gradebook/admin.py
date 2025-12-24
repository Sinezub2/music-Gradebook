# apps/gradebook/admin.py
from django.contrib import admin
from .models import Assessment, Grade


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "assessment_type", "max_score", "weight")
    list_filter = ("assessment_type", "course")
    search_fields = ("title", "course__name")


@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ("assessment", "student", "score")
    list_select_related = ("assessment", "student", "assessment__course")
    search_fields = ("student__username", "assessment__title", "assessment__course__name")
    list_filter = ("assessment__course", "assessment__assessment_type")
