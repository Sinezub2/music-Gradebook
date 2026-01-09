from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import Profile
from apps.school.models import Course, ParentChild
from .models import Assignment, AssignmentStatus


def _effective_status(assignment: Assignment, st: AssignmentStatus | None) -> str:
    """
    Display logic:
    - DONE stays DONE
    - If not DONE and due_date < today -> LATE
    - Else TODO
    """
    if st and st.status == AssignmentStatus.Status.DONE:
        return AssignmentStatus.Status.DONE
    if assignment.due_date < date.today():
        return AssignmentStatus.Status.LATE
    return AssignmentStatus.Status.TODO


@login_required
def assignment_list(request):
    profile = request.user.profile

    # Base queryset
    assignments = Assignment.objects.all().select_related("course", "created_by")

    ctx = {"mode": profile.role}

    if profile.role == Profile.Role.ADMIN:
        ctx["assignments"] = assignments.order_by("due_date", "id")
        return render(request, "homework/assignment_list.html", ctx)

    if profile.role == Profile.Role.TEACHER:
        teacher_courses = Course.objects.filter(teacher=request.user)
        ctx["assignments"] = assignments.filter(course__in=teacher_courses).order_by("due_date", "id")
        return render(request, "homework/assignment_list.html", ctx)

    if profile.role == Profile.Role.STUDENT:
        enrolled = Course.objects.filter(enrollments__student=request.user).distinct()
        qs = assignments.filter(course__in=enrolled).order_by("due_date", "id")

        statuses = AssignmentStatus.objects.filter(student=request.user, assignment__in=qs).select_related("assignment")
        status_map = {s.assignment_id: s for s in statuses}

        rows = []
        for a in qs:
            st = status_map.get(a.id)
            rows.append({"assignment": a, "status_obj": st, "status": _effective_status(a, st)})

        ctx["rows"] = rows
        ctx["student"] = request.user
        return render(request, "homework/assignment_list.html", ctx)

    if profile.role == Profile.Role.PARENT:
        children = ParentChild.objects.filter(parent=request.user).select_related("child")
        child_blocks = []
        for link in children:
            child = link.child
            enrolled = Course.objects.filter(enrollments__student=child).distinct()
            qs = assignments.filter(course__in=enrolled).order_by("due_date", "id")

            statuses = AssignmentStatus.objects.filter(student=child, assignment__in=qs).select_related("assignment")
            status_map = {s.assignment_id: s for s in statuses}

            rows = []
            for a in qs:
                st = status_map.get(a.id)
                rows.append({"assignment": a, "status_obj": st, "status": _effective_status(a, st)})

            child_blocks.append({"child": child, "rows": rows})

        ctx["child_blocks"] = child_blocks
        return render(request, "homework/assignment_list.html", ctx)

    ctx["assignments"] = []
    return render(request, "homework/assignment_list.html", ctx)


@require_POST
@login_required
def mark_done(request, assignment_id: int):
    """
    Optional: student can mark DONE for themselves.
    Parent/Teacher/Admin cannot use this endpoint.
    """
    profile = request.user.profile
    if profile.role != Profile.Role.STUDENT:
        messages.error(request, "Недостаточно прав.")
        return redirect("/assignments/")

    assignment = get_object_or_404(Assignment, id=assignment_id)

    # Ensure student is enrolled in the course
    is_enrolled = Course.objects.filter(id=assignment.course_id, enrollments__student=request.user).exists()
    if not is_enrolled:
        messages.error(request, "Вы не записаны на этот курс.")
        return redirect("/assignments/")

    st, _ = AssignmentStatus.objects.get_or_create(assignment=assignment, student=request.user)
    st.status = AssignmentStatus.Status.DONE
    st.save()

    messages.success(request, "Отмечено как DONE.")
    return redirect("/assignments/")
