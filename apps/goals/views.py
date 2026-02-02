from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.contrib.auth import get_user_model

from apps.accounts.models import Profile
from apps.school.models import Course, ParentChild
from .forms import GoalForm
from .models import Goal

User = get_user_model()


@login_required
def goal_list(request):
    profile = request.user.profile
    selected_student_id = request.GET.get("student") or ""
    can_edit = profile.role in (Profile.Role.TEACHER, Profile.Role.ADMIN)

    students = User.objects.none()
    goals = Goal.objects.none()

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

    ctx = {
        "goals": goals,
        "students": students,
        "selected_student": selected_student,
        "selected_student_id": selected_student_id,
        "can_edit": can_edit,
    }
    return render(request, "goals/goal_list.html", ctx)


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
            goal.save()
            messages.success(request, "Цель добавлена.")
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
