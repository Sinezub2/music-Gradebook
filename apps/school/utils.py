from __future__ import annotations

from typing import NamedTuple

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
