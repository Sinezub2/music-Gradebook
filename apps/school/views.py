# apps/school/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden

from apps.accounts.models import Profile
from apps.gradebook.models import Grade
from apps.goals.models import Goal
from apps.homework.models import AssignmentTarget
from apps.lessons.models import LessonReport, LessonStudent
from .models import Course, Enrollment, ParentChild
from .utils import (
    get_teacher_student_or_404,
    get_teacher_students,
    get_user_single_class,
    resolve_teacher_course_for_student,
)


@login_required
def course_list(request):
    profile = request.user.profile
    single_class = get_user_single_class(request.user)

    if profile.role != Profile.Role.ADMIN:
        if single_class.status == "single":
            return redirect(f"/courses/{single_class.course.id}/")
        if single_class.status == "none":
            return render(
                request,
                "school/course_list.html",
                {"mode": "no_class", "no_class_message": "Класс не назначен. Обратитесь к администратору."},
            )

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
        redirect_url = "/teacher/class/"
        if cycle:
            redirect_url = f"{redirect_url}?cycle={cycle}"
        return redirect(redirect_url)

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
        if student_id:
            link = get_object_or_404(ParentChild, parent=request.user, child_id=student_id)
            child = link.child
        else:
            child_ids = ParentChild.objects.filter(parent=request.user).values_list("child_id", flat=True)
            enrolled_child_ids = list(
                Enrollment.objects.filter(course=course, student_id__in=child_ids)
                .values_list("student_id", flat=True)
                .distinct()[:2]
            )
            if not enrolled_child_ids:
                return HttpResponseForbidden("Ребёнок не записан на этот курс.")
            if len(enrolled_child_ids) > 1:
                return HttpResponseForbidden("Выберите ученика.")
            child = get_object_or_404(ParentChild.objects.select_related("child"), parent=request.user, child_id=enrolled_child_ids[0]).child
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


@login_required
def teacher_class_list(request):
    profile = request.user.profile
    if profile.role != Profile.Role.TEACHER:
        return HttpResponseForbidden("Доступ запрещён.")

    cycle = request.GET.get("cycle") or ""
    students = list(get_teacher_students(request.user, cycle=cycle))
    return render(
        request,
        "teacher/class_list.html",
        {
            "students": students,
            "cycle": cycle,
            "cycle_options": Profile.Cycle.choices,
        },
    )


@login_required
def teacher_student_workspace(request, student_id: int):
    profile = request.user.profile
    if profile.role != Profile.Role.TEACHER:
        return HttpResponseForbidden("Доступ запрещён.")

    student = get_teacher_student_or_404(request.user, student_id)
    teacher_courses = list(
        Course.objects.filter(teacher=request.user, enrollments__student=student).distinct().order_by("name")
    )
    course_for_actions, course_status = resolve_teacher_course_for_student(request.user, student)

    recent_assignments = list(
        AssignmentTarget.objects.filter(student=student, assignment__course__teacher=request.user)
        .select_related("assignment", "assignment__course")
        .order_by("-assignment__due_date")[:5]
    )
    recent_lessons = list(
        LessonStudent.objects.filter(student=student, lesson__course__teacher=request.user)
        .select_related("lesson", "lesson__course")
        .order_by("-lesson__date", "-lesson_id")[:5]
    )
    recent_reports = list(
        LessonReport.objects.filter(student=student, lesson__course__teacher=request.user)
        .select_related("lesson")
        .order_by("-created_at")[:5]
    )
    recent_grades = list(
        Grade.objects.filter(student=student, assessment__course__teacher=request.user)
        .select_related("assessment")
        .order_by("-assessment_id")[:5]
    )
    goals = list(Goal.objects.filter(student=student).select_related("teacher").order_by("-created_at")[:5])

    return render(
        request,
        "teacher/student_workspace.html",
        {
            "student": student,
            "teacher_courses": teacher_courses,
            "course_for_actions": course_for_actions,
            "course_status": course_status,
            "recent_assignments": recent_assignments,
            "recent_lessons": recent_lessons,
            "recent_reports": recent_reports,
            "recent_grades": recent_grades,
            "goals": goals,
        },
    )
