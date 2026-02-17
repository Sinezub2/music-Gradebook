import json
from collections import defaultdict

from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.models import Profile
from apps.school.models import Course, Enrollment, ParentChild
from apps.homework.models import AssignmentTarget
from apps.gradebook.models import Grade
from apps.lessons.models import LessonReport
from .models import Achievement, MediaLink


def _teacher_can_view_student(teacher_user, student_id: int) -> bool:
    return Enrollment.objects.filter(course__teacher=teacher_user, student_id=student_id).exists()


def my_portfolio(request):
    if not request.user.is_authenticated:
        return HttpResponseForbidden("Требуется вход.")

    profile = getattr(request.user, "profile", None)
    if not profile:
        messages.error(request, "Профиль не найден.")
        return redirect("/dashboard")

    if profile.role == Profile.Role.STUDENT:
        return redirect(f"/students/{request.user.id}/profile/")

    if profile.role == Profile.Role.PARENT:
        child_id = (
            ParentChild.objects.filter(parent=request.user)
            .select_related("child")
            .order_by("child__first_name", "child__last_name", "child__username")
            .values_list("child_id", flat=True)
            .first()
        )
        if child_id:
            return redirect(f"/students/{child_id}/profile/")

        messages.error(request, "Нет привязанных учеников для просмотра портфолио.")
        return redirect("/dashboard")

    messages.error(request, "Портфолио доступно только ученикам и родителям.")
    return redirect("/dashboard")


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

    grade_series = (
        Grade.objects.filter(student_id=student_id, score__isnull=False)
        .select_related("assessment", "assessment__course")
        .order_by("assessment__id")
    )
    grade_labels = [f"{g.assessment.course.name}: {g.assessment.title}" for g in grade_series]
    grade_scores = [float(g.score) for g in grade_series]

    course_totals: dict[str, list[float]] = defaultdict(list)
    for grade in grade_series:
        course_totals[grade.assessment.course.name].append(float(grade.score))
    course_avg_labels = list(course_totals.keys())
    course_avg_scores = [
        round(sum(scores) / len(scores), 2) for scores in course_totals.values()
    ]

    chart_payload = {
        "gradeLabels": grade_labels,
        "gradeScores": grade_scores,
        "courseAvgLabels": course_avg_labels,
        "courseAvgScores": course_avg_scores,
    }
    chart_has_data = bool(grade_labels or course_avg_labels)

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
            "chart_payload": json.dumps(chart_payload, ensure_ascii=False),
            "chart_has_data": chart_has_data,
        },
    )
