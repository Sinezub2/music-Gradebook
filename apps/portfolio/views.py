from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render

from apps.accounts.models import Profile
from apps.school.models import Course, Enrollment, ParentChild
from apps.homework.models import AssignmentTarget
from apps.gradebook.models import Grade
from apps.lessons.models import LessonReport
from .models import Achievement, MediaLink


def _teacher_can_view_student(teacher_user, student_id: int) -> bool:
    return Enrollment.objects.filter(course__teacher=teacher_user, student_id=student_id).exists()


def student_profile(request, student_id: int):
    if not request.user.is_authenticated:
        return HttpResponseForbidden("Требуется вход.")

    student = get_object_or_404(Profile.objects.select_related("user"), user_id=student_id, role=Profile.Role.STUDENT).user
    role = request.user.profile.role

    if role == Profile.Role.STUDENT:
        if request.user.id != student_id:
            return HttpResponseForbidden("Нет доступа.")
    elif role == Profile.Role.PARENT:
        if not ParentChild.objects.filter(parent=request.user, child_id=student_id).exists():
            return HttpResponseForbidden("Нет доступа.")
    elif role == Profile.Role.TEACHER:
        if not _teacher_can_view_student(request.user, student_id):
            return HttpResponseForbidden("Нет доступа.")
    # admin ok

    courses = Course.objects.filter(enrollments__student_id=student_id).order_by("name")

    last_targets = (
        AssignmentTarget.objects.filter(student_id=student_id)
        .select_related("assignment", "assignment__course")
        .order_by("-updated_at")[:5]
    )

    last_grades = (
        Grade.objects.filter(student_id=student_id, score__isnull=False)
        .select_related("assessment", "assessment__course")
        .order_by("-id")[:5]
    )

    last_reports = (
        LessonReport.objects.filter(student_id=student_id)
        .select_related("lesson", "lesson__course")
        .order_by("-created_at")[:5]
    )

    achievements = Achievement.objects.filter(student_id=student_id).order_by("-date", "-id")
    media_links = MediaLink.objects.filter(student_id=student_id).order_by("-created_at", "-id")

    return render(
        request,
        "portfolio/student_profile.html",
        {
            "student": student,
            "courses": courses,
            "last_targets": last_targets,
            "last_grades": last_grades,
            "last_reports": last_reports,
            "achievements": achievements,
            "media_links": media_links,
        },
    )
