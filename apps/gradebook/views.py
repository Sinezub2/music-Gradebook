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
    cycle = request.GET.get("cycle") or ""
    assessments = list(Assessment.objects.filter(course=course).order_by("id"))
    enrollments_qs = Enrollment.objects.filter(course=course).select_related("student", "student__profile")
    if cycle:
        enrollments_qs = enrollments_qs.filter(student__profile__cycle=cycle)
    enrollments = list(enrollments_qs.order_by("student__username"))
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
            "cycle": cycle,
            "cycle_options": Profile.Cycle.choices,
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

    # ---- Progress summary + trend ----
    # If homework app doesn't have AssignmentTarget yet, this import will fail.
    # In that case either create it or temporarily wrap this block in try/except.
    from apps.homework.models import AssignmentTarget
    from django.utils import timezone

    today = timezone.localdate()

    # average of non-null grade scores in this course
    non_null_scores = [g.score for g in grades_by_assessment_id.values() if g.score is not None]
    avg_val = None
    if non_null_scores:
        try:
            avg_val = sum([float(x) for x in non_null_scores]) / len(non_null_scores)
            avg_val = round(avg_val, 2)
        except Exception:
            avg_val = None

    targets_qs = AssignmentTarget.objects.filter(student=student, assignment__course=course).select_related("assignment")
    assigned_cnt = targets_qs.count()
    done_cnt = targets_qs.filter(status=AssignmentTarget.Status.DONE).count()

    next_due = (
        targets_qs.filter(status=AssignmentTarget.Status.TODO)
        .order_by("assignment__due_date")
        .values_list("assignment__due_date", flat=True)
        .first()
    )
    next_due_str = next_due.strftime("%d.%m.%Y") if next_due else None

    # streak: how many DONE in a row among last 5 by due_date desc
    last_targets = list(targets_qs.order_by("-assignment__due_date")[:5])
    streak = 0
    for t in last_targets:
        if t.status == AssignmentTarget.Status.DONE:
            streak += 1
        else:
            break

    # badge: if no overdue TODO
    late_exists = targets_qs.filter(status=AssignmentTarget.Status.TODO, assignment__due_date__lt=today).exists()
    badge = None
    if assigned_cnt > 0 and not late_exists:
        badge = "Все задания вовремя (сейчас)"

    trend = []
    for a in assessments:
        g = grades_by_assessment_id.get(a.id)
        if g and g.score is not None:
            trend.append({"label": f"{a.title}", "score": g.score})

    summary = {
        "avg": avg_val,
        "assigned": assigned_cnt,
        "done": done_cnt,
        "next_due": next_due_str,
        "streak": streak,
        "badge": badge,
    }

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
            "summary": summary,
            "trend": trend,
        },
    )
