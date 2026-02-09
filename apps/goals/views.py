from datetime import date

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from urllib.parse import urlencode

from apps.accounts.models import Profile
from apps.school.models import Course, ParentChild
from .forms import GoalForm
from .models import Goal

User = get_user_model()


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


def _build_goals_url(student_id: str) -> str:
    params = {}
    if student_id:
        params["student"] = student_id
    return f"/goals/?{urlencode(params)}" if params else "/goals/"


@login_required
def goal_list(request):
    profile = request.user.profile
    selected_student_id = request.GET.get("student") or ""
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

    goals = goals.order_by("month", "student__username", "created_at")
    base_url = _build_goals_url(selected_student_id)
    goal_rows = []
    for goal in goals:
        goal_rows.append(
            {
                "goal": goal,
                "can_delete": _can_delete_goal(request.user, profile.role, goal, teacher_students),
            }
        )

    ctx = {
        "goals": goal_rows,
        "students": students,
        "selected_student": selected_student,
        "selected_student_id": selected_student_id,
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
    redirect_url = _build_goals_url(selected_student_id)

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


@login_required
def goal_create(request):
    profile = request.user.profile
    if profile.role not in (Profile.Role.TEACHER, Profile.Role.ADMIN):
        return HttpResponseForbidden("Доступ запрещён.")

    selected_student_id = request.GET.get("student") or ""
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

    selected_student = None
    if selected_student_id:
        selected_student = students.filter(id=selected_student_id).first()
        if not selected_student:
            selected_student_id = ""

    if request.method == "POST":
        form = GoalForm(request.POST)
        form.fields["student"].queryset = students
        if form.is_valid():
            goal = form.save(commit=False)
            goal.teacher = request.user
            goal.month = date.today().replace(month=1, day=1)
            goal.save()
            messages.success(request, "Годовая цель добавлена.")
            redirect_url = "/goals/"
            if selected_student_id:
                redirect_url = f"/goals/?student={selected_student_id}"
            return redirect(redirect_url)
    else:
        form = GoalForm()
        form.fields["student"].queryset = students
        if selected_student:
            form.fields["student"].initial = selected_student

    ctx = {
        "form": form,
        "selected_student_id": selected_student_id,
    }
    return render(request, "goals/goal_create.html", ctx)
