# apps/accounts/admin.py
from django.contrib import admin
from .models import ActivationCode, Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "cycle", "school_grade")
    list_select_related = ("user",)
    search_fields = ("user__username", "user__first_name", "user__last_name")
    list_filter = ("role", "cycle", "school_grade")


@admin.register(ActivationCode)
class ActivationCodeAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "target_role",
        "course",
        "target_student",
        "created_by_teacher",
        "is_used",
        "used_by",
        "created_at",
    )
    list_filter = ("target_role", "is_used", "created_at", "course")
    search_fields = (
        "code",
        "course__name",
        "created_by_teacher__username",
        "created_by_teacher__first_name",
        "created_by_teacher__last_name",
        "target_student__username",
        "target_student__first_name",
        "target_student__last_name",
    )
    readonly_fields = ("code", "created_at", "used_at")
