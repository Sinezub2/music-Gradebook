from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from datetime import date, datetime, timedelta

from apps.accounts.decorators import role_required
from apps.accounts.models import Profile
from apps.school.models import Course, Enrollment, ParentChild
from .forms import LessonCreateForm
from .models import Lesson, LessonReport, LessonStudent


def _student_ids_for_user(request):
    role = request.user.profile.role
    if role == Profile.Role.STUDENT:
        return [request.user.id]
    if role == Profile.Role.PARENT:
        return list(ParentChild.objects.filter(parent=request.user).values_list("child_id", flat=True))
    return []


@login_required
def lesson_list(request):
    role = request.user.profile.role
    course_id = request.GET.get("course")
    student_id = request.GET.get("student")

    if request.method == "POST" and role in (Profile.Role.TEACHER, Profile.Role.ADMIN):
        lesson_id = request.POST.get("lesson_id")
        student_id = request.POST.get("student_id")
        attended = request.POST.get("attended") == "on"
        course_id = request.POST.get("course") or course_id
        if lesson_id and student_id:
            entry = get_object_or_404(
                LessonStudent.objects.select_related("lesson__course"),
                lesson_id=lesson_id,
                student_id=student_id,
            )
            if role == Profile.Role.TEACHER and entry.lesson.course.teacher_id != request.user.id:
                return HttpResponseForbidden("Нет доступа.")
            entry.attended = attended
            entry.save(update_fields=["attended"])
            messages.success(request, "Посещение обновлено.")
        redirect_url = "/lessons/"
        params = []
        if course_id:
            params.append(f"course={course_id}")
        if student_id:
            params.append(f"student={student_id}")
        if params:
            redirect_url = f"{redirect_url}?{'&'.join(params)}"
        return redirect(redirect_url)

    students = []
    selected_student = None
    user_model = get_user_model()
    if role == Profile.Role.ADMIN:
        lessons_qs = Lesson.objects.all().select_related("course", "created_by")
        student_ids = Enrollment.objects.values_list("student_id", flat=True).distinct()
        students = list(user_model.objects.filter(id__in=student_ids).select_related("profile").order_by("username"))
    elif role == Profile.Role.TEACHER:
        lessons_qs = Lesson.objects.filter(course__teacher=request.user).select_related("course", "created_by")
        student_ids = (
            Enrollment.objects.filter(course__teacher=request.user).values_list("student_id", flat=True).distinct()
        )
        students = list(user_model.objects.filter(id__in=student_ids).select_related("profile").order_by("username"))
    else:
        student_ids = _student_ids_for_user(request)
        if role == Profile.Role.PARENT and student_id:
            if int(student_id) not in student_ids:
                return HttpResponseForbidden("Нет доступа.")
            student_ids = [int(student_id)]
        if len(student_ids) == 1:
            student_id = student_ids[0]
        course_ids = Enrollment.objects.filter(student_id__in=student_ids).values_list("course_id", flat=True)
        lessons_qs = Lesson.objects.filter(course_id__in=course_ids).select_related("course", "created_by")
        if student_ids:
            students = list(
                user_model.objects.filter(id__in=student_ids).select_related("profile").order_by("username")
            )

    if course_id:
        lessons_qs = lessons_qs.filter(course_id=course_id)

    if student_id:
        selected_student = get_object_or_404(user_model, id=student_id)
        entries_qs = LessonStudent.objects.filter(student_id=student_id, lesson__in=lessons_qs).select_related(
            "lesson", "lesson__course"
        )
        reports = (
            LessonReport.objects.filter(lesson__in=lessons_qs)
            .filter(Q(student_id=student_id) | Q(student__isnull=True))
            .order_by("-created_at")
        )
        student_report_map = {}
        general_report_map = {}
        for report in reports:
            if report.student_id == int(student_id):
                student_report_map.setdefault(report.lesson_id, report.text)
            elif report.student_id is None:
                general_report_map.setdefault(report.lesson_id, report.text)
        rows = [
            {
                "lesson": entry.lesson,
                "attendance": entry.attended,
                "result": entry.result
                or student_report_map.get(entry.lesson_id)
                or general_report_map.get(entry.lesson_id)
                or "",
            }
            for entry in entries_qs.order_by("-lesson__date", "-lesson_id")
        ]
    else:
        rows = [
            {
                "lesson": lesson,
                "attendance": None,
                "result": "",
            }
            for lesson in lessons_qs.order_by("-date", "-id")
        ]

    return render(
        request,
        "lessons/lesson_list.html",
        {
            "lessons": rows,
            "course_id": course_id,
            "students": students,
            "student_id": str(student_id) if student_id else "",
            "selected_student": selected_student,
        },
    )


@login_required
def attendance_journal(request):
    role = request.user.profile.role
    course_id = request.GET.get("course")
    course_id_int = None
    if course_id:
        try:
            course_id_int = int(course_id)
        except ValueError:
            course_id_int = None
    month_value = request.GET.get("month")

    today = date.today()
    try:
        month_start = datetime.strptime(month_value, "%Y-%m").date().replace(day=1) if month_value else today.replace(day=1)
    except ValueError:
        month_start = today.replace(day=1)
        month_value = None
    month_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    month_input_value = (month_value or month_start.strftime("%Y-%m"))

    user_model = get_user_model()
    students = []
    allowed_courses = Course.objects.none()

    if role == Profile.Role.ADMIN:
        allowed_courses = Course.objects.all()
    elif role == Profile.Role.TEACHER:
        allowed_courses = Course.objects.filter(teacher=request.user)
    else:
        student_ids = _student_ids_for_user(request)
        allowed_courses = Course.objects.filter(enrollments__student_id__in=student_ids).distinct()

    allowed_courses = allowed_courses.order_by("name")
    allowed_course_ids = set(allowed_courses.values_list("id", flat=True))

    if course_id_int:
        if course_id_int not in allowed_course_ids:
            return HttpResponseForbidden("Нет доступа.")
        lessons_qs = Lesson.objects.filter(course_id=course_id_int)
    else:
        lessons_qs = Lesson.objects.none()

    if course_id_int:
        if role in (Profile.Role.ADMIN, Profile.Role.TEACHER):
            student_ids = Enrollment.objects.filter(course_id=course_id_int).values_list("student_id", flat=True).distinct()
        else:
            allowed_student_ids = _student_ids_for_user(request)
            student_ids = Enrollment.objects.filter(course_id=course_id_int, student_id__in=allowed_student_ids).values_list("student_id", flat=True).distinct()
        students = list(user_model.objects.filter(id__in=student_ids).select_related("profile").order_by("username"))

    lessons_qs = lessons_qs.filter(date__gte=month_start, date__lt=month_end).select_related("course")
    lesson_dates = list(lessons_qs.order_by("date").values_list("date", flat=True).distinct())

    attendance_entries = (
        LessonStudent.objects.filter(lesson__in=lessons_qs, student__in=students)
        .select_related("lesson", "student")
    )

    attendance_map = {}
    for entry in attendance_entries:
        attendance_map.setdefault(entry.lesson.date, {})[entry.student_id] = entry.attended

    attendance_counts = (
        LessonStudent.objects.filter(lesson__in=lessons_qs, student__in=students, attended=True)
        .values("student_id")
        .annotate(total=Count("id"))
    )
    total_minutes_by_student = {row["student_id"]: row["total"] * 40 for row in attendance_counts}
    overall_minutes = sum(total_minutes_by_student.values())

    def _format_minutes(total_minutes: int) -> str:
        hours = total_minutes // 60
        minutes = total_minutes % 60
        if hours and minutes:
            return f"{hours} ч {minutes} мин"
        if hours:
            return f"{hours} ч"
        return f"{minutes} мин"

    rows = []
    for lesson_date in lesson_dates:
        cells = []
        for student in students:
            attended = attendance_map.get(lesson_date, {}).get(student.id)
            cells.append({"student": student, "attended": attended})
        rows.append({"date": lesson_date, "cells": cells})

    totals = [
        {
            "student": student,
            "minutes": total_minutes_by_student.get(student.id, 0),
            "label": _format_minutes(total_minutes_by_student.get(student.id, 0)),
        }
        for student in students
    ]

    return render(
        request,
        "lessons/attendance_journal.html",
        {
            "courses": allowed_courses,
            "course_id": str(course_id_int) if course_id_int else "",
            "month_value": month_input_value,
            "rows": rows,
            "students": students,
            "totals": totals,
            "overall_total_label": _format_minutes(overall_minutes),
        },
    )


@role_required(Profile.Role.TEACHER, Profile.Role.ADMIN)
def lesson_create(request):
    if request.method == "POST":
        form = LessonCreateForm(request.POST, teacher_user=(request.user if request.user.profile.role == Profile.Role.TEACHER else None))
        if form.is_valid():
            course = form.cleaned_data["course"]
            if request.user.profile.role == Profile.Role.TEACHER and course.teacher_id != request.user.id:
                return HttpResponseForbidden("Нельзя создавать уроки для чужого курса.")

            lesson = Lesson.objects.create(
                course=course,
                date=form.cleaned_data["date"],
                topic=form.cleaned_data["topic"],
                created_by=request.user,
            )

            enrollments = Enrollment.objects.filter(course=course).select_related("student")
            result = (form.cleaned_data.get("result") or "").strip()
            LessonStudent.objects.bulk_create(
                [
                    LessonStudent(lesson=lesson, student=enrollment.student, attended=True, result=result)
                    for enrollment in enrollments
                ]
            )

            text = (form.cleaned_data.get("report_text") or "").strip()
            media = (form.cleaned_data.get("media_url") or "").strip()
            if text or media:
                LessonReport.objects.create(lesson=lesson, student=None, text=text, media_url=media)

            messages.success(request, "Урок создан.")
            return redirect(f"/lessons/{lesson.id}/")
    else:
        form = LessonCreateForm(teacher_user=(request.user if request.user.profile.role == Profile.Role.TEACHER else None))

    return render(request, "lessons/lesson_create.html", {"form": form})


@login_required
def lesson_detail(request, lesson_id: int):
    lesson = get_object_or_404(Lesson.objects.select_related("course", "created_by"), id=lesson_id)

    role = request.user.profile.role
    if role == Profile.Role.TEACHER:
        if lesson.course.teacher_id != request.user.id:
            return HttpResponseForbidden("Нет доступа.")
    elif role in (Profile.Role.STUDENT, Profile.Role.PARENT):
        student_ids = _student_ids_for_user(request)
        if not Enrollment.objects.filter(course=lesson.course, student_id__in=student_ids).exists():
            return HttpResponseForbidden("Нет доступа.")
    # admin ok

    reports = LessonReport.objects.filter(lesson=lesson).select_related("student").order_by("-created_at")
    return render(request, "lessons/lesson_detail.html", {"lesson": lesson, "reports": reports})
