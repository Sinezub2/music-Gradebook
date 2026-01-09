from django.contrib import admin
from .models import Assignment, AssignmentTarget


class AssignmentTargetInline(admin.TabularInline):
    model = AssignmentTarget
    extra = 0
    autocomplete_fields = ("student",)
    fields = ("student", "status", "student_comment", "updated_at")
    readonly_fields = ("updated_at",)


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "due_date", "created_by", "created_at")
    list_filter = ("course", "due_date")
    search_fields = ("title", "description", "course__name", "created_by__username")
    inlines = [AssignmentTargetInline]


@admin.register(AssignmentTarget)
class AssignmentTargetAdmin(admin.ModelAdmin):
    list_display = ("assignment", "student", "status", "updated_at")
    list_filter = ("status", "assignment__course")
    search_fields = ("assignment__title", "student__username")
