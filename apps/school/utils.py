from __future__ import annotations

from typing import NamedTuple

from django.contrib.auth import get_user_model

from apps.accounts.models import Profile

from .models import Course, ParentChild


class SingleClassResolution(NamedTuple):
    status: str
    course: Course | None


def get_user_courses(user, *, include_admin: bool = False):
    role = user.profile.role

    if role == Profile.Role.STUDENT:
        return Course.objects.filter(enrollments__student=user).distinct().order_by("name")

    if role == Profile.Role.PARENT:
        child_ids = ParentChild.objects.filter(parent=user).values_list("child_id", flat=True)
        return Course.objects.filter(enrollments__student_id__in=child_ids).distinct().order_by("name")

    if role == Profile.Role.TEACHER:
        return Course.objects.filter(teacher=user).order_by("name")

    if include_admin and role == Profile.Role.ADMIN:
        return Course.objects.all().order_by("name")

    return Course.objects.none()


def get_user_single_class(user, *, include_admin: bool = False) -> SingleClassResolution:
    courses = list(get_user_courses(user, include_admin=include_admin)[:2])
    if not courses:
        return SingleClassResolution(status="none", course=None)
    if len(courses) == 1:
        return SingleClassResolution(status="single", course=courses[0])
    return SingleClassResolution(status="multiple", course=None)


def get_teacher_students(user, *, cycle: str = ""):
    user_model = get_user_model()
    students = (
        user_model.objects.filter(
            enrollments__course__teacher=user,
            profile__role=Profile.Role.STUDENT,
        )
        .select_related("profile")
        .distinct()
        .order_by("username")
    )
    if cycle:
        students = students.filter(profile__cycle=cycle)
    return students


def get_teacher_student_or_404(teacher, student_id: int):
    from django.shortcuts import get_object_or_404

    return get_object_or_404(get_teacher_students(teacher), id=student_id)


def resolve_teacher_course_for_student(teacher, student):
    courses = list(
        Course.objects.filter(teacher=teacher, enrollments__student=student).distinct().order_by("name")[:2]
    )
    if not courses:
        return None, "none"
    if len(courses) == 1:
        return courses[0], "single"
    return courses[0], "multiple"
