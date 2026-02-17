
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from urllib.parse import urlencode

from apps.accounts.decorators import role_required
from apps.accounts.models import Profile
from apps.gradebook.models import Assessment
from apps.school.models import Course, ParentChild
from apps.school.utils import get_user_single_class
from .forms import AssignmentCreateForm, StudentAssignmentCreateForm
from .models import Assignment, AssignmentTarget
from .services import create_assignment_with_targets_and_gradebook
from apps.school.utils import get_teacher_student_or_404, resolve_teacher_course_for_student


def _effective_status(assignment: Assignment, target: AssignmentTarget | None) -> str:
    """
    Display logic:
    DONE stays DONE
    else if due_date < today -> LATE (computed)
    else TODO
    """
    if target and target.status == AssignmentTarget.Status.DONE:
        return "DONE"
    if assignment.due_date < date.today():
        return "LATE"
    return "TODO"


def _can_delete_assignment(user, role: str, assignment: Assignment) -> bool:
    if role == Profile.Role.ADMIN:
        return True
    if role != Profile.Role.TEACHER:
        return False
    return assignment.created_by_id == user.id or assignment.course.teacher_id == user.id


def _build_assignments_url(cycle: str) -> str:
    params = {}
    if cycle:
        params["cycle"] = cycle
    return f"/assignments/?{urlencode(params)}" if params else "/assignments/"


@login_required
def assignment_list(request):
    profile = request.user.profile
    cycle = request.GET.get("cycle") or ""
    select_mode = request.GET.get("select") == "1"

    if profile.role == Profile.Role.TEACHER:
        qs = Assignment.objects.filter(created_by=request.user).select_related("course")
        if cycle:
            qs = qs.filter(targets__student__profile__cycle=cycle).distinct()
        qs = qs.order_by("due_date", "id")
        rows = []
        for a in qs:
            targets_qs = a.targets.all()
            if cycle:
                targets_qs = targets_qs.filter(student__profile__cycle=cycle)
            count_targets = targets_qs.count()
            rows.append(
                {
                    "assignment": a,
                    "count_targets": count_targets,
                    "can_delete": _can_delete_assignment(request.user, profile.role, a),
                }
            )
        base_url = _build_assignments_url(cycle)
        return render(
            request,
            "homework/assignment_list.html",
            {
                "mode": "TEACHER",
                "rows": rows,
                "cycle": cycle,
                "cycle_options": Profile.Cycle.choices,
                "select_mode": select_mode,
                "can_bulk_delete": True,
                "select_url": f"{base_url}{'&' if '?' in base_url else '?'}select=1",
                "cancel_select_url": base_url,
            },
        )

    if profile.role == Profile.Role.ADMIN:
        qs = Assignment.objects.all().select_related("course", "created_by")
        if cycle:
            qs = qs.filter(targets__student__profile__cycle=cycle).distinct()
        qs = qs.order_by("due_date", "id")
        assignments = []
        for assignment in qs:
            assignments.append(
                {"assignment": assignment, "can_delete": _can_delete_assignment(request.user, profile.role, assignment)}
            )
        base_url = _build_assignments_url(cycle)
        return render(
            request,
            "homework/assignment_list.html",
            {
                "mode": "ADMIN",
                "assignments": assignments,
                "cycle": cycle,
                "cycle_options": Profile.Cycle.choices,
                "select_mode": select_mode,
                "can_bulk_delete": True,
                "select_url": f"{base_url}{'&' if '?' in base_url else '?'}select=1",
                "cancel_select_url": base_url,
            },
        )

    if profile.role == Profile.Role.STUDENT:
        targets = (
            AssignmentTarget.objects.filter(student=request.user)
            .select_related("assignment", "assignment__course")
            .order_by("assignment__due_date", "assignment_id")
        )
        rows = []
        for t in targets:
            a = t.assignment
            rows.append({"target": t, "assignment": a, "status": _effective_status(a, t)})
        return render(request, "homework/assignment_list.html", {"mode": "STUDENT", "rows": rows, "student": request.user})

    if profile.role == Profile.Role.PARENT:
        children = ParentChild.objects.filter(parent=request.user).select_related("child").order_by("child__username")

        child_blocks = []
        for link in children:
            child = link.child
            targets = (
                AssignmentTarget.objects.filter(student=child)
                .select_related("assignment", "assignment__course")
                .order_by("assignment__due_date", "assignment_id")
            )
            rows = []
            for t in targets:
                a = t.assignment
                rows.append({"target": t, "assignment": a, "status": _effective_status(a, t)})
            child_blocks.append({"child": child, "rows": rows})

        return render(request, "homework/assignment_list.html", {"mode": "PARENT", "child_blocks": child_blocks})

    return render(request, "homework/assignment_list.html", {"mode": "UNKNOWN"})


@require_POST
@role_required(Profile.Role.TEACHER, Profile.Role.ADMIN)
def assignment_bulk_delete(request):
    role = request.user.profile.role
    selected_ids = []
    for raw_id in request.POST.getlist("selected_ids"):
        try:
            selected_ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue

    cycle = request.POST.get("cycle") or ""
    redirect_url = _build_assignments_url(cycle)

    if not selected_ids:
        messages.info(request, "Ничего не выбрано для удаления.")
        return redirect(redirect_url)

    assignments = list(Assignment.objects.filter(id__in=selected_ids).select_related("course", "created_by"))
    unauthorized = [a.id for a in assignments if not _can_delete_assignment(request.user, role, a)]
    if unauthorized:
        return HttpResponseForbidden("Нет доступа к удалению выбранных заданий.")

    Assessment.objects.filter(source_assignment__in=assignments).delete()
    deleted_count = 0
    for assignment in assignments:
        assignment.delete()
        deleted_count += 1

    messages.success(request, f"Удалено заданий: {deleted_count}.")
    return redirect(redirect_url)


@role_required(Profile.Role.TEACHER)
def assignment_create(request):
    """
    Без JS:
    - при одном классе у преподавателя курс подставляется автоматически
    - при нескольких классах сохраняется fallback-выбор курса
    - POST: создаём Assignment + Assessment + Targets + Grades
    """

    if request.user.profile.role == Profile.Role.TEACHER:
        messages.info(request, "Сначала выберите ученика в разделе «Класс».")
        return redirect("/teacher/class/")

    selected_course = None
    fixed_course = None
    class_resolution = get_user_single_class(request.user)
    if class_resolution.status == "none":
        messages.error(request, "Класс не назначен. Обратитесь к администратору.")
        return redirect("/assignments/")
    if class_resolution.status == "single":
        fixed_course = class_resolution.course
        selected_course = fixed_course
    else:
        course_id = request.GET.get("course") or request.POST.get("course")
        if course_id:
            try:
                selected_course = Course.objects.get(id=course_id, teacher=request.user)
            except Course.DoesNotExist:
                selected_course = None

    course_queryset = Course.objects.filter(id=fixed_course.id) if fixed_course else None

    if request.method == "POST":
        form = AssignmentCreateForm(
            request.POST,
            request.FILES,
            teacher_user=request.user,
            course_for_students=selected_course,
            course_queryset=course_queryset,
        )
        if form.is_valid():
            course = fixed_course or form.cleaned_data["course"]
            title = form.cleaned_data["title"]
            description = form.cleaned_data.get("description", "")
            due_date = form.cleaned_data["due_date"]
            attachment = form.cleaned_data.get("attachment")
            student_ids = [int(x) for x in form.cleaned_data.get("students", [])]

            # Create everything per spec
            create_assignment_with_targets_and_gradebook(
                teacher=request.user,
                course=course,
                title=title,
                description=description,
                due_date=due_date,
                attachment=attachment,
                student_ids=student_ids,
            )

            messages.success(request, "Задание создано и назначено выбранным ученикам.")
            return redirect("/assignments/")
    else:
        form = AssignmentCreateForm(
            teacher_user=request.user,
            course_for_students=selected_course,
            course_queryset=course_queryset,
        )
        # If course selected via GET, prefill it in the form
        if selected_course:
            form.initial["course"] = selected_course

    return render(
        request,
        "homework/assignment_create.html",
        {
            "form": form,
            "selected_course": selected_course,
            "fixed_course": fixed_course,
        },
    )


@role_required(Profile.Role.TEACHER)
def assignment_create_for_student(request, student_id: int):
    student = get_teacher_student_or_404(request.user, student_id)
    course, status = resolve_teacher_course_for_student(request.user, student)
    if status == "none":
        messages.error(request, "Ученик не назначен на ваш курс.")
        return redirect(f"/teacher/students/{student.id}/")
    if status == "multiple":
        messages.error(request, "У ученика несколько ваших курсов. Уточните курс у администратора.")
        return redirect(f"/teacher/students/{student.id}/")

    if request.method == "POST":
        form = StudentAssignmentCreateForm(request.POST, request.FILES)
        if form.is_valid():
            create_assignment_with_targets_and_gradebook(
                teacher=request.user,
                course=course,
                title=form.cleaned_data["title"],
                description=form.cleaned_data.get("description", ""),
                due_date=form.cleaned_data["due_date"],
                attachment=form.cleaned_data.get("attachment"),
                student_ids=[student.id],
            )
            messages.success(request, "Задание создано и назначено ученику.")
            return redirect(f"/teacher/students/{student.id}/")
    else:
        form = StudentAssignmentCreateForm()

    return render(
        request,
        "homework/assignment_create_student.html",
        {"form": form, "student": student, "course": course},
    )


@require_POST
@role_required(Profile.Role.STUDENT)
def mark_done(request, target_id: int):
    """
    Student marks assigned homework as DONE.
    No grade auto-fill.
    """
    target = get_object_or_404(
        AssignmentTarget.objects.select_related("assignment", "assignment__course"),
        id=target_id,
        student=request.user,
    )
    target.status = AssignmentTarget.Status.DONE
    target.save()

    messages.success(request, "Отмечено как DONE (результат выставляется преподавателем отдельно).")
    return redirect("/assignments/")
