# apps/gradebook/views.py
from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseForbidden
from django.db import transaction

from apps.accounts.decorators import role_required
from apps.accounts.models import Profile
from apps.school.models import Course, Enrollment, ParentChild
from .models import Assessment, Grade
from .services import compute_average_percent


@role_required(Profile.Role.TEACHER)
def teacher_course_grades(request, course_id: int):
    course = get_object_or_404(Course, id=course_id, teacher=request.user)
    assessments = list(Assessment.objects.filter(course=course).order_by("id"))
    enrollments = list(Enrollment.objects.filter(course=course).select_related("student").order_by("student__username"))
    students = [e.student for e in enrollments]

    grades = Grade.objects.filter(assessment__course=course, student__in=students).select_related("assessment", "student")
    grade_map: dict[tuple[int, int], Grade] = {(g.student_id, g.assessment_id): g for g in grades}

    if request.method == "POST":
        with transaction.atomic():
            for student in students:
                for a in assessments:
                    score_key = f"grade-{student.id}-{a.id}"
                    comment_key = f"comment-{student.id}-{a.id}"
                    raw_score = (request.POST.get(score_key) or "").strip()
                    raw_comment = (request.POST.get(comment_key) or "").strip()

                    score_val = None
                    if raw_score != "":
                        try:
                            score_val = Decimal(raw_score.replace(",", "."))
                        except (InvalidOperation, ValueError):
                            messages.error(request, f"Некорректная оценка: {student.username} / {a.title}")
                            continue

                    obj, _created = Grade.objects.get_or_create(assessment=a, student=student)
                    obj.score = score_val
                    obj.comment = raw_comment
                    obj.save()

        messages.success(request, "Оценки сохранены.")
        return redirect(f"/teacher/courses/{course.id}/grades/")

    table_rows = []
    for s in students:
        cells = []
        for a in assessments:
            cells.append({"assessment": a, "grade": grade_map.get((s.id, a.id))})
        table_rows.append({"student": s, "cells": cells})

    return render(
        request,
        "gradebook/teacher_course_grades.html",
        {
            "course": course,
            "assessments": assessments,
            "students": students,
            "table_rows": table_rows,
        },
    )


@role_required(Profile.Role.STUDENT, Profile.Role.PARENT)
def student_course_grades(request, course_id: int):
    course = get_object_or_404(Course, id=course_id)
    profile = request.user.profile

    if profile.role == Profile.Role.STUDENT:
        student = request.user
        if not Enrollment.objects.filter(course=course, student=student).exists():
            return HttpResponseForbidden("Вы не записаны на этот курс.")
    else:
        student_id = request.GET.get("student")
        if not student_id:
            return HttpResponseForbidden("Не выбран ученик.")
        link = get_object_or_404(ParentChild, parent=request.user, child_id=student_id)
        student = link.child
        if not Enrollment.objects.filter(course=course, student=student).exists():
            return HttpResponseForbidden("Ребёнок не записан на этот курс.")

    assessments = list(Assessment.objects.filter(course=course).order_by("id"))
    grades = Grade.objects.filter(assessment__in=assessments, student=student).select_related("assessment")
    grades_by_assessment_id = {g.assessment_id: g for g in grades}

    avg_percent = compute_average_percent(assessments, grades_by_assessment_id)

    rows = []
    for a in assessments:
        g = grades_by_assessment_id.get(a.id)
        score = g.score if g else None
        comment = g.comment if g else ""
        percent = None
        if score is not None and a.max_score:
            try:
                percent = (Decimal(score) / Decimal(a.max_score)) * Decimal("100")
            except Exception:
                percent = None

        rows.append(
            {
                "assessment": a,
                "score": score,
                "comment": comment,
                "percent": percent,
                "max_score": a.max_score,
                "weight": a.weight,
            }
        )

    return render(
        request,
        "gradebook/student_course_grades.html",
        {
            "course": course,
            "student": student,
            "rows": rows,
            "avg_percent": avg_percent,
        },
    )

