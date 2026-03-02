from datetime import date

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from urllib.parse import urlencode

from apps.accounts.models import Profile
from apps.school.models import Course, ParentChild
from .models import Goal
from apps.school.utils import get_teacher_student_or_404

User = get_user_model()
HALF_YEAR_I = "H1"
HALF_YEAR_II = "H2"
GOAL_STATUS_IN_PROGRESS = "IN_PROGRESS"
GOAL_STATUS_DONE = "DONE"
GOAL_STATUS_PREFIX = "__status__:"


def _teacher_student_ids(user):
    teacher_courses = Course.objects.filter(teacher=user)
    return set(
        User.objects.filter(enrollments__course__in=teacher_courses)
        .values_list("id", flat=True)
        .distinct()
    )


def _can_delete_goal(user, role: str, goal: Goal, teacher_student_ids: set[int]) -> bool:
    if role == Profile.Role.ADMIN:
        return True
    if role != Profile.Role.TEACHER:
        return False
    return goal.teacher_id == user.id or goal.student_id in teacher_student_ids


def _current_half_year_code() -> str:
    return HALF_YEAR_I if date.today().month <= 6 else HALF_YEAR_II


def _normalize_half_year(raw_value: str, *, fallback_to_current: bool = True) -> str:
    value = (raw_value or "").strip()
    if value in (HALF_YEAR_I, HALF_YEAR_II):
        return value
    return _current_half_year_code() if fallback_to_current else ""


def _build_goals_url(student_id: str, half_year: str = "") -> str:
    params = {}
    if student_id:
        params["student"] = student_id
    normalized_half_year = _normalize_half_year(half_year, fallback_to_current=False)
    if normalized_half_year:
        params["half_year"] = normalized_half_year
    return f"/goals/?{urlencode(params)}" if params else "/goals/"


def _half_year_start_from_selection(selected_half_year: str):
    today = date.today()
    if selected_half_year == HALF_YEAR_I:
        return date(today.year, 1, 1)
    if selected_half_year == HALF_YEAR_II:
        return date(today.year, 7, 1)
    return None


def _half_year_label(month_value: date) -> str:
    half = "I полугодие" if month_value.month <= 6 else "II полугодие"
    return f"{half} {month_value.year}"


def _normalize_goal_titles(raw_values: list[str], max_input_length: int = 50) -> tuple[list[str], list[str]]:
    titles = []
    errors = []
    for raw_value in raw_values:
        value = (raw_value or "").strip()
        if not value:
            continue
        if len(value) >= max_input_length:
            errors.append("Введите значение короче 50 символов.")
            continue
        titles.append(value)
    if not titles and not errors:
        errors.append("Добавьте хотя бы одну цель.")
    return titles, errors


def _goal_status_from_details(raw_details: str):
    details = (raw_details or "").strip()
    if not details:
        return GOAL_STATUS_IN_PROGRESS, ""
    lines = details.splitlines()
    first_line = lines[0].strip()
    if first_line.startswith(GOAL_STATUS_PREFIX):
        status_code = first_line[len(GOAL_STATUS_PREFIX) :].strip()
        if status_code in (GOAL_STATUS_IN_PROGRESS, GOAL_STATUS_DONE):
            extra_text = "\n".join(lines[1:]).strip()
            return status_code, extra_text
    return GOAL_STATUS_IN_PROGRESS, details


def _goal_details_with_status(status_code: str, raw_details: str) -> str:
    _, extra_text = _goal_status_from_details(raw_details)
    payload = f"{GOAL_STATUS_PREFIX}{status_code}"
    if extra_text:
        payload = f"{payload}\n{extra_text}"
    return payload


def _goal_status_label(status_code: str) -> str:
    return "Выполнено" if status_code == GOAL_STATUS_DONE else "В процессе"


@login_required
def goal_list(request):
    profile = request.user.profile
    selected_student_id = request.GET.get("student") or ""
    selected_half_year = _normalize_half_year(request.GET.get("half_year") or "")
    can_edit = profile.role in (Profile.Role.TEACHER, Profile.Role.ADMIN)
    select_mode = request.GET.get("select") == "1"

    students = User.objects.none()
    goals = Goal.objects.none()
    teacher_students = set()

    if profile.role == Profile.Role.STUDENT:
        students = User.objects.filter(id=request.user.id).select_related("profile")
        goals = Goal.objects.filter(student=request.user).select_related("student", "teacher")
        selected_student_id = str(request.user.id)
    elif profile.role == Profile.Role.PARENT:
        children_links = ParentChild.objects.filter(parent=request.user).select_related("child__profile")
        child_ids = [link.child_id for link in children_links]
        students = User.objects.filter(id__in=child_ids).select_related("profile")
        goals = Goal.objects.filter(student__in=child_ids).select_related("student", "teacher")
    elif profile.role == Profile.Role.TEACHER:
        teacher_courses = Course.objects.filter(teacher=request.user)
        teacher_students = set(
            User.objects.filter(enrollments__course__in=teacher_courses).values_list("id", flat=True).distinct()
        )
        students = (
            User.objects.filter(enrollments__course__in=teacher_courses)
            .select_related("profile")
            .distinct()
        )
        goals = Goal.objects.filter(student__in=students).select_related("student", "teacher")
    elif profile.role == Profile.Role.ADMIN:
        students = User.objects.filter(profile__role=Profile.Role.STUDENT).select_related("profile")
        goals = Goal.objects.filter(student__in=students).select_related("student", "teacher")
    else:
        return HttpResponseForbidden("Доступ запрещён.")

    selected_student = None
    if selected_student_id:
        selected_student = students.filter(id=selected_student_id).first()
        if selected_student:
            goals = goals.filter(student=selected_student)
        else:
            selected_student_id = ""

    if selected_half_year == HALF_YEAR_I:
        goals = goals.filter(month__month__lte=6)
    else:
        goals = goals.filter(month__month__gte=7)

    goals = goals.order_by("-month", "student__first_name", "student__last_name", "student__username", "created_at")
    base_url = _build_goals_url(selected_student_id, selected_half_year)
    grouped_goals = []
    groups = {}
    for goal in goals:
        half_start = goal.month.replace(day=1, month=(1 if goal.month.month <= 6 else 7))
        status_code, _ = _goal_status_from_details(goal.details)
        group_key = (half_start.year, half_start.month)
        if group_key not in groups:
            group_data = {
                "label": _half_year_label(half_start),
                "rows": [],
            }
            groups[group_key] = group_data
            grouped_goals.append(group_data)
        groups[group_key]["rows"].append(
            {
                "goal": goal,
                "can_delete": _can_delete_goal(request.user, profile.role, goal, teacher_students),
                "status_code": status_code,
                "status_label": _goal_status_label(status_code),
                "can_update_status": can_edit and _can_delete_goal(request.user, profile.role, goal, teacher_students),
            }
        )

    ctx = {
        "goal_groups": grouped_goals,
        "students": students,
        "selected_student": selected_student,
        "selected_student_id": selected_student_id,
        "selected_half_year": selected_half_year,
        "half_year_options": [
            {
                "value": HALF_YEAR_I,
                "label": "I полугодие",
                "active": selected_half_year == HALF_YEAR_I,
                "url": _build_goals_url(selected_student_id, HALF_YEAR_I),
            },
            {
                "value": HALF_YEAR_II,
                "label": "II полугодие",
                "active": selected_half_year == HALF_YEAR_II,
                "url": _build_goals_url(selected_student_id, HALF_YEAR_II),
            },
        ],
        "can_edit": can_edit,
        "can_bulk_delete": can_edit,
        "select_mode": select_mode,
        "select_url": f"{base_url}{'&' if '?' in base_url else '?'}select=1",
        "cancel_select_url": base_url,
    }
    return render(request, "goals/goal_list.html", ctx)


@require_POST
@login_required
def goal_bulk_delete(request):
    profile = request.user.profile
    if profile.role not in (Profile.Role.TEACHER, Profile.Role.ADMIN):
        return HttpResponseForbidden("Доступ запрещён.")

    selected_ids = []
    for raw_id in request.POST.getlist("selected_ids"):
        try:
            selected_ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue
    selected_student_id = request.POST.get("student") or ""
    selected_half_year = _normalize_half_year(request.POST.get("half_year") or "", fallback_to_current=False)
    redirect_url = _build_goals_url(selected_student_id, selected_half_year)

    if not selected_ids:
        messages.info(request, "Ничего не выбрано для удаления.")
        return redirect(redirect_url)

    goals = list(Goal.objects.filter(id__in=selected_ids).select_related("student", "teacher"))
    teacher_students = _teacher_student_ids(request.user) if profile.role == Profile.Role.TEACHER else set()
    unauthorized = [g.id for g in goals if not _can_delete_goal(request.user, profile.role, g, teacher_students)]
    if unauthorized:
        return HttpResponseForbidden("Нет доступа к удалению выбранных целей.")

    deleted_count = 0
    for goal in goals:
        goal.delete()
        deleted_count += 1
    messages.success(request, f"Удалено целей: {deleted_count}.")
    return redirect(redirect_url)


@require_POST
@login_required
def goal_status_update(request, goal_id: int):
    profile = request.user.profile
    if profile.role not in (Profile.Role.TEACHER, Profile.Role.ADMIN):
        return HttpResponseForbidden("Доступ запрещён.")

    goal = get_object_or_404(Goal.objects.select_related("student", "teacher"), id=goal_id)
    teacher_students = _teacher_student_ids(request.user) if profile.role == Profile.Role.TEACHER else set()
    if not _can_delete_goal(request.user, profile.role, goal, teacher_students):
        return HttpResponseForbidden("Доступ запрещён.")

    status_code = (request.POST.get("status") or "").strip()
    if status_code not in (GOAL_STATUS_IN_PROGRESS, GOAL_STATUS_DONE):
        messages.error(request, "Некорректный статус цели.")
    else:
        goal.details = _goal_details_with_status(status_code, goal.details)
        goal.save(update_fields=["details"])
        messages.success(request, "Статус цели обновлён.")

    raw_student_id = request.POST.get("student")
    if raw_student_id is None:
        selected_student_id = str(goal.student_id)
    else:
        selected_student_id = (raw_student_id or "").strip()
    selected_half_year = _normalize_half_year(request.POST.get("half_year") or "", fallback_to_current=False)
    return redirect(_build_goals_url(selected_student_id, selected_half_year))


@login_required
def goal_create(request):
    profile = request.user.profile
    if profile.role not in (Profile.Role.TEACHER, Profile.Role.ADMIN):
        return HttpResponseForbidden("Доступ запрещён.")

    if profile.role == Profile.Role.TEACHER:
        messages.info(request, "Сначала выберите ученика в разделе «Класс».")
        return redirect("/teacher/class/")

    selected_student_id = request.GET.get("student") or ""
    selected_half_year = _normalize_half_year(request.GET.get("half_year") or "")
    students = User.objects.none()

    if profile.role == Profile.Role.TEACHER:
        teacher_courses = Course.objects.filter(teacher=request.user)
        students = (
            User.objects.filter(enrollments__course__in=teacher_courses)
            .select_related("profile")
            .distinct()
        )
    elif profile.role == Profile.Role.ADMIN:
        students = User.objects.filter(profile__role=Profile.Role.STUDENT).select_related("profile")

    selected_student = students.filter(id=selected_student_id).first() if selected_student_id else None
    if not selected_student:
        messages.info(request, "Сначала выберите ученика.")
        return redirect(_build_goals_url("", selected_half_year))

    entered_titles = [""]
    title_errors = []
    half_year_error = ""
    if request.method == "POST":
        raw_titles = request.POST.getlist("goal_titles")
        selected_half_year = (request.POST.get("half_year") or "").strip()
        entered_titles = raw_titles or [""]
        titles, title_errors = _normalize_goal_titles(raw_titles)
        half_start = _half_year_start_from_selection(selected_half_year)
        if not half_start:
            half_year_error = "Выберите полугодие."
        if not title_errors and not half_year_error:
            Goal.objects.bulk_create(
                [
                    Goal(
                        student=selected_student,
                        teacher=request.user,
                        month=half_start,
                        title=title,
                    )
                    for title in titles
                ]
            )
            messages.success(request, f"Добавлено целей: {len(titles)}.")
            return redirect(_build_goals_url(str(selected_student.id), selected_half_year))

    ctx = {
        "selected_student_id": selected_student_id,
        "selected_student": selected_student,
        "entered_titles": entered_titles,
        "title_errors": title_errors,
        "selected_half_year": selected_half_year,
        "half_year_error": half_year_error,
    }
    return render(request, "goals/goal_create.html", ctx)


@login_required
def goal_create_for_student(request, student_id: int):
    profile = request.user.profile
    if profile.role not in (Profile.Role.TEACHER, Profile.Role.ADMIN):
        return HttpResponseForbidden("Доступ запрещён.")

    if profile.role == Profile.Role.TEACHER:
        student = get_teacher_student_or_404(request.user, student_id)
    else:
        student = User.objects.filter(id=student_id, profile__role=Profile.Role.STUDENT).select_related("profile").first()
        if not student:
            return HttpResponseForbidden("Доступ запрещён.")

    entered_titles = [""]
    title_errors = []
    selected_half_year = _normalize_half_year(request.GET.get("half_year") or "")
    half_year_error = ""
    if request.method == "POST":
        raw_titles = request.POST.getlist("goal_titles")
        selected_half_year = (request.POST.get("half_year") or "").strip()
        entered_titles = raw_titles or [""]
        titles, title_errors = _normalize_goal_titles(raw_titles)
        half_start = _half_year_start_from_selection(selected_half_year)
        if not half_start:
            half_year_error = "Выберите полугодие."
        if not title_errors and not half_year_error:
            Goal.objects.bulk_create(
                [
                    Goal(
                        student=student,
                        teacher=request.user,
                        month=half_start,
                        title=title,
                    )
                    for title in titles
                ]
            )
            messages.success(request, f"Добавлено целей: {len(titles)}.")
            return redirect(_build_goals_url(str(student.id), selected_half_year))

    return render(
        request,
        "goals/goal_create_student.html",
        {
            "student": student,
            "entered_titles": entered_titles,
            "title_errors": title_errors,
            "selected_half_year": selected_half_year,
            "half_year_error": half_year_error,
        },
    )
