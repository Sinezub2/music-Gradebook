# apps/accounts/admin.py
from django.contrib import admin
from .models import Profile, StudentInvitation


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "cycle", "school_grade")
    list_select_related = ("user",)
    search_fields = ("user__username", "user__first_name", "user__last_name")
    list_filter = ("role", "cycle", "school_grade")


@admin.register(StudentInvitation)
class StudentInvitationAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "teacher", "course", "school_grade", "is_used", "created_at", "expires_at")
    list_filter = ("is_used", "created_at", "expires_at", "course")
    search_fields = (
        "first_name",
        "last_name",
        "teacher__username",
        "teacher__first_name",
        "teacher__last_name",
        "course__name",
    )
    readonly_fields = ("created_at", "used_at", "token")
