from __future__ import annotations

from typing import NamedTuple

from django.contrib.auth import get_user_model
from django.db.models import Count, Q

from apps.accounts.models import Profile

from .models import Course, ParentChild


BASIC_CYCLE = "BASIC"
BASIC_CYCLE_LABEL = "Базовый"


def _build_cycle_choices() -> tuple[tuple[str, str], ...]:
    choices = list(Profile.Cycle.choices)
    basic_choice = (BASIC_CYCLE, BASIC_CYCLE_LABEL)
    if basic_choice not in choices:
        choices.append(basic_choice)
    return tuple(choices)


CYCLE_CHOICES = _build_cycle_choices()
_CYCLE_LOOKUP = {
    str(value).strip().casefold(): code
    for code, label in CYCLE_CHOICES
    for value in (code, label)
}


class SingleClassResolution(NamedTuple):
    status: str
    course: Course | None


def _normalize_cycle(cycle: str) -> str:
    raw = (cycle or "").strip()
    if not raw:
        return ""
    return _CYCLE_LOOKUP.get(raw.casefold(), raw)


def _teacher_courses_queryset(user):
    return (
        Course.objects.filter(
            Q(teacher=user)
            | Q(student_schedules__teacher=user)
            | Q(lesson_slots__teacher=user)
            | Q(lessons__created_by=user)
            | Q(assignments__created_by=user)
            | Q(student_invitations__teacher=user)
        )
        .distinct()
        .order_by("name", "id")
    )


def get_teacher_group_courses(user):
    return (
        Course.objects.filter(teacher=user)
        .select_related("course_type")
        .annotate(student_total=Count("enrollments", distinct=True))
        .order_by("name", "id")
    )


def get_cycle_choices() -> tuple[tuple[str, str], ...]:
    return CYCLE_CHOICES


def get_user_courses(user, *, include_admin: bool = False):
    role = user.profile.role

    if role == Profile.Role.STUDENT:
        return Course.objects.filter(enrollments__student=user).distinct().order_by("name")

    if role == Profile.Role.PARENT:
        child_ids = ParentChild.objects.filter(parent=user).values_list("child_id", flat=True)
        return Course.objects.filter(enrollments__student_id__in=child_ids).distinct().order_by("name")

    if role == Profile.Role.TEACHER:
        return _teacher_courses_queryset(user)

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
            enrollments__course__in=_teacher_courses_queryset(user),
            profile__role=Profile.Role.STUDENT,
        )
        .select_related("profile")
        .distinct()
        .order_by("first_name", "last_name", "username")
    )
    if cycle:
        students = students.filter(profile__cycle=_normalize_cycle(cycle))
    return students


def get_teacher_student_or_404(teacher, student_id: int):
    from django.shortcuts import get_object_or_404

    return get_object_or_404(get_teacher_students(teacher), id=student_id)


def get_teacher_group_or_404(teacher, group_id: int):
    from django.shortcuts import get_object_or_404

    return get_object_or_404(get_teacher_group_courses(teacher), id=group_id)


def get_group_student_enrollments(course: Course):
    return (
        course.enrollments.filter(student__profile__role=Profile.Role.STUDENT)
        .select_related("student", "student__profile")
        .order_by("student__first_name", "student__last_name", "student__username", "student_id")
    )


def get_teacher_group_student_or_404(teacher, course: Course, student_id: int):
    from django.http import Http404
    from django.shortcuts import get_object_or_404

    if course.teacher_id != teacher.id:
        raise Http404
    return get_object_or_404(get_group_student_enrollments(course), student_id=student_id)


def resolve_teacher_course_for_student(teacher, student):
    base_qs = _teacher_courses_queryset(teacher).filter(enrollments__student=student)
    courses = list(base_qs[:2])
    if not courses:
        return None, "none"
    if len(courses) == 1:
        return courses[0], "single"

    preferred_course = (
        base_qs.filter(student_schedules__teacher=teacher, student_schedules__student=student).first()
        or base_qs.filter(lesson_slots__teacher=teacher, lesson_slots__student=student).first()
        or courses[0]
    )
    return preferred_course, "multiple"
