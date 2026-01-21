# apps/school/views.py
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden

from apps.accounts.models import Profile
from .models import Course, Enrollment, ParentChild


@login_required
def course_list(request):
    profile = request.user.profile

    # Parent can view courses for a selected child via ?student=<id>
    student_id = request.GET.get("student")
    cycle = request.GET.get("cycle") or ""

    if profile.role == Profile.Role.STUDENT:
        courses = Course.objects.filter(enrollments__student=request.user).distinct().order_by("name")
        return render(
            request,
            "school/course_list.html",
            {"courses": courses, "mode": "student", "student": request.user},
        )

    if profile.role == Profile.Role.PARENT:
        if not student_id:
            children = ParentChild.objects.filter(parent=request.user).select_related("child").order_by("child__username")
            return render(request, "school/course_list.html", {"children_links": children, "mode": "parent_pick"})
        link = get_object_or_404(ParentChild, parent=request.user, child_id=student_id)
        child = link.child
        courses = Course.objects.filter(enrollments__student=child).distinct().order_by("name")
        return render(request, "school/course_list.html", {"courses": courses, "mode": "parent_child", "student": child})

    if profile.role == Profile.Role.TEACHER:
        courses = Course.objects.filter(teacher=request.user)
        if cycle:
            courses = courses.filter(enrollments__student__profile__cycle=cycle).distinct()
        courses = courses.order_by("name")
        return render(
            request,
            "school/course_list.html",
            {"courses": courses, "mode": "teacher", "student": None, "cycle": cycle, "cycle_options": Profile.Cycle.choices},
        )

    if profile.role == Profile.Role.ADMIN:
        courses = Course.objects.all()
        if cycle:
            courses = courses.filter(enrollments__student__profile__cycle=cycle).distinct()
        courses = courses.order_by("name")
        return render(
            request,
            "school/course_list.html",
            {"courses": courses, "mode": "admin", "student": None, "cycle": cycle, "cycle_options": Profile.Cycle.choices},
        )

    return HttpResponseForbidden("Доступ запрещён.")


@login_required
def course_detail(request, course_id: int):
    profile = request.user.profile
    course = get_object_or_404(Course, id=course_id)

    # Student: must be enrolled
    if profile.role == Profile.Role.STUDENT:
        if not Enrollment.objects.filter(course=course, student=request.user).exists():
            return HttpResponseForbidden("Вы не записаны на этот курс.")
        return render(request, "school/course_detail.html", {"course": course, "mode": "student", "student": request.user})

    # Parent: must be linked to the child and child must be enrolled. Child passed by ?student=<id>
    if profile.role == Profile.Role.PARENT:
        student_id = request.GET.get("student")
        if not student_id:
            return HttpResponseForbidden("Не выбран ученик.")
        link = get_object_or_404(ParentChild, parent=request.user, child_id=student_id)
        child = link.child
        if not Enrollment.objects.filter(course=course, student=child).exists():
            return HttpResponseForbidden("Ребёнок не записан на этот курс.")
        return render(request, "school/course_detail.html", {"course": course, "mode": "parent", "student": child})

    # Teacher/admin: allow view course info (grades are elsewhere)
    if profile.role in (Profile.Role.TEACHER, Profile.Role.ADMIN):
        return render(
            request,
            "school/course_detail.html",
            {"course": course, "mode": "staff", "student": None, "role": profile.role},
        )

    return HttpResponseForbidden("Доступ запрещён.")
