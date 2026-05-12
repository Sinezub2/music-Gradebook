# apps/school/admin.py
from django.contrib import admin
from .models import Course, CourseInternalGroup, CourseType, Enrollment, ParentChild


@admin.register(CourseType)
class CourseTypeAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("name", "course_type", "teacher")
    list_filter = ("course_type",)
    search_fields = ("name", "teacher__username")


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("course", "student")
    search_fields = ("course__name", "student__username")


@admin.register(CourseInternalGroup)
class CourseInternalGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "course", "group_type")
    list_filter = ("group_type", "course")
    search_fields = ("name", "course__name", "students__username")
    filter_horizontal = ("students",)


@admin.register(ParentChild)
class ParentChildAdmin(admin.ModelAdmin):
    list_display = ("parent", "child")
    search_fields = ("parent__username", "child__username")
