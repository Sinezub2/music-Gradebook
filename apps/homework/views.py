
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import role_required
from apps.accounts.models import Profile
from apps.school.models import Course, ParentChild
from .forms import AssignmentCreateForm
from .models import Assignment, AssignmentTarget
from .services import create_assignment_with_targets_and_gradebook


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


@login_required
def assignment_list(request):
    profile = request.user.profile

    if profile.role == Profile.Role.TEACHER:
        qs = Assignment.objects.filter(created_by=request.user).select_related("course").order_by("due_date", "id")
        rows = []
        for a in qs:
            count_targets = a.targets.count()
            rows.append({"assignment": a, "count_targets": count_targets})
        return render(request, "homework/assignment_list.html", {"mode": "TEACHER", "rows": rows})

    if profile.role == Profile.Role.ADMIN:
        qs = Assignment.objects.all().select_related("course", "created_by").order_by("due_date", "id")
        return render(request, "homework/assignment_list.html", {"mode": "ADMIN", "assignments": qs})

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
        return render(request, "homework/assignment_list.html", {"mode": "STUDENT", "rows": rows})

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


@role_required(Profile.Role.TEACHER)
def assignment_create(request):
    """
    Без JS делаем так:
    - GET: форма + (если выбран course) показываем чекбоксы студентов
    - POST: создаём Assignment + Assessment + Targets + Grades
    """

    selected_course = None
    course_id = request.GET.get("course") or request.POST.get("course")
    if course_id:
        try:
            selected_course = Course.objects.get(id=course_id, teacher=request.user)
        except Course.DoesNotExist:
            selected_course = None

    if request.method == "POST":
        form = AssignmentCreateForm(request.POST, teacher_user=request.user, course_for_students=selected_course)
        if form.is_valid():
            course = form.cleaned_data["course"]
            title = form.cleaned_data["title"]
            description = form.cleaned_data.get("description", "")
            due_date = form.cleaned_data["due_date"]
            student_ids = [int(x) for x in form.cleaned_data.get("students", [])]

            # Create everything per spec
            create_assignment_with_targets_and_gradebook(
                teacher=request.user,
                course=course,
                title=title,
                description=description,
                due_date=due_date,
                student_ids=student_ids,
            )

            messages.success(request, "Задание создано и назначено выбранным ученикам.")
            return redirect("/assignments/")
    else:
        form = AssignmentCreateForm(teacher_user=request.user, course_for_students=selected_course)
        # If course selected via GET, prefill it in the form
        if selected_course:
            form.initial["course"] = selected_course

    return render(
        request,
        "homework/assignment_create.html",
        {
            "form": form,
            "selected_course": selected_course,
        },
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

    messages.success(request, "Отмечено как DONE (оценка выставляется преподавателем отдельно).")
    return redirect("/assignments/")
