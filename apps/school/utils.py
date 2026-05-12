from __future__ import annotations

import re
from typing import NamedTuple

from django.contrib.auth import get_user_model
from django.db.models import Count, Q

from apps.accounts.models import Profile

from .models import Course, CourseInternalGroup, ParentChild


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
_SCHOOL_GRADE_NUMBER_RE = re.compile(r"(\d+)")


class SingleClassResolution(NamedTuple):
    status: str
    course: Course | None


def _normalize_cycle(cycle: str) -> str:
    raw = (cycle or "").strip()
    if not raw:
        return ""
    return _CYCLE_LOOKUP.get(raw.casefold(), raw)


def normalize_school_grade_label(value: str) -> str:
    return " ".join((value or "").upper().split()).strip()


def extract_school_grade_number(value: str) -> str:
    match = _SCHOOL_GRADE_NUMBER_RE.search(normalize_school_grade_label(value))
    return match.group(1) if match else ""


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


def _classroom_scope_value(value: str) -> str:
    normalized = normalize_school_grade_label(value)
    return f"classroom:{normalized}" if normalized else "classroom:__blank__"


def _internal_scope_value(group_id: int) -> str:
    return f"internal:{group_id}"


def build_course_scope_options(course: Course, *, enrollments=None) -> list[dict]:
    rows = list(enrollments if enrollments is not None else get_group_student_enrollments(course))
    all_student_ids = [row.student_id for row in rows]
    options = [
        {
            "value": "",
            "label": "Все ученики",
            "kind": "all",
            "count": len(all_student_ids),
            "student_ids": all_student_ids,
        }
    ]

    classroom_map = {}
    for row in rows:
        classroom_label = normalize_school_grade_label(row.student.profile.school_grade)
        key = classroom_label or "__blank__"
        classroom = classroom_map.setdefault(
            key,
            {
                "value": _classroom_scope_value(classroom_label),
                "label": classroom_label or "Без класса",
                "kind": "classroom",
                "count": 0,
                "student_ids": [],
            },
        )
        classroom["count"] += 1
        classroom["student_ids"].append(row.student_id)

    for classroom in sorted(classroom_map.values(), key=lambda item: item["label"]):
        options.append(classroom)

    allowed_ids = set(all_student_ids)
    for group in course.internal_groups.prefetch_related("students").order_by("name", "id"):
        group_student_ids = [student_id for student_id in group.students.values_list("id", flat=True) if student_id in allowed_ids]
        options.append(
            {
                "value": _internal_scope_value(group.id),
                "label": group.name,
                "kind": "internal",
                "count": len(group_student_ids),
                "student_ids": group_student_ids,
                "group": group,
            }
        )

    return options


def resolve_course_scope(course: Course, scope: str, *, enrollments=None) -> tuple[dict, list, list[dict]]:
    rows = list(enrollments if enrollments is not None else get_group_student_enrollments(course))
    options = build_course_scope_options(course, enrollments=rows)
    options_by_value = {option["value"]: option for option in options}
    selected = options_by_value.get(scope or "", options[0])
    selected_ids = set(selected["student_ids"])
    selected_rows = [row for row in rows if row.student_id in selected_ids]
    return selected, selected_rows, options


def get_student_internal_groups_for_course(student, course: Course):
    return course.internal_groups.filter(students=student).order_by("name", "id")


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
