# apps/gradebook/views.py
from decimal import Decimal
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseForbidden
from django.db import transaction
from django.views.decorators.http import require_POST
from urllib.parse import urlencode

from apps.accounts.decorators import role_required
from apps.accounts.models import Profile
from apps.school.models import Course, Enrollment, ParentChild
from apps.school.utils import get_teacher_student_or_404, resolve_teacher_course_for_student
from .models import Assessment, Grade
from .services import compute_average_percent


def _build_teacher_grades_url(course_id: int, cycle: str) -> str:
    params = {}
    if cycle:
        params["cycle"] = cycle
    base = f"/teacher/courses/{course_id}/grades/"
    return f"{base}?{urlencode(params)}" if params else base


@role_required(Profile.Role.TEACHER, Profile.Role.ADMIN)
def teacher_course_grades(request, course_id: int):
    profile = request.user.profile
    if profile.role == Profile.Role.ADMIN:
        course = get_object_or_404(Course, id=course_id)
    else:
        course = get_object_or_404(Course, id=course_id, teacher=request.user)
    cycle = request.GET.get("cycle") or ""
    select_mode = request.GET.get("select") == "1"
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
                    if raw_comment and len(raw_comment) >= 50:
                        messages.error(
                            request,
                            f"Комментарий слишком длинный (короче 50 символов): {student.username} / {a.title}",
                        )
                        continue

                    score_val = None
                    if raw_score != "":
                        if not raw_score.isdigit():
                            messages.error(request, f"Некорректный результат: {student.username} / {a.title}")
                            continue
                        try:
                            score_int = int(raw_score)
                        except ValueError:
                            messages.error(request, f"Некорректный результат: {student.username} / {a.title}")
                            continue
                        if score_int < 0 or score_int > 100:
                            messages.error(request, f"Результат вне диапазона 0–100: {student.username} / {a.title}")
                            continue
                        score_val = Decimal(score_int)

                    obj, _created = Grade.objects.get_or_create(assessment=a, student=student)
                    obj.score = score_val
                    obj.comment = raw_comment
                    obj.save()

        messages.success(request, "Результаты сохранены.")
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
            "select_mode": select_mode,
            "clear_select_url": f"{_build_teacher_grades_url(course.id, cycle)}{'&' if cycle else '?'}select=1",
            "cancel_select_url": _build_teacher_grades_url(course.id, cycle),
        },
    )


@require_POST
@role_required(Profile.Role.TEACHER, Profile.Role.ADMIN)
def teacher_course_grades_bulk_clear(request, course_id: int):
    profile = request.user.profile
    if profile.role == Profile.Role.ADMIN:
        course = get_object_or_404(Course, id=course_id)
    else:
        course = get_object_or_404(Course, id=course_id, teacher=request.user)

    cycle = request.POST.get("cycle") or ""
    redirect_url = _build_teacher_grades_url(course.id, cycle)

    selected_ids = []
    for raw_id in request.POST.getlist("selected_ids"):
        try:
            selected_ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue
    if not selected_ids:
        messages.info(request, "Ничего не выбрано для очистки.")
        return redirect(redirect_url)

    existing_ids = set(Assessment.objects.filter(course=course, id__in=selected_ids).values_list("id", flat=True))
    if len(existing_ids) != len(set(selected_ids)):
        return HttpResponseForbidden("Нет доступа к очистке выбранных результатов.")

    updated = Grade.objects.filter(assessment_id__in=existing_ids, assessment__course=course).update(score=None, comment="")
    messages.success(request, f"Очищено результатов: {updated}.")
    return redirect(redirect_url)


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
            student_id = str(enrolled_child_ids[0])
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


@role_required(Profile.Role.TEACHER)
def teacher_student_results(request, student_id: int):
    student = get_teacher_student_or_404(request.user, student_id)
    course, status = resolve_teacher_course_for_student(request.user, student)
    if status == "none":
        return HttpResponseForbidden("Ученик не назначен на ваш курс.")
    if status == "multiple":
        return HttpResponseForbidden("У ученика несколько ваших курсов. Уточните курс у администратора.")

    assessments = list(Assessment.objects.filter(course=course).order_by("id"))
    grades = Grade.objects.filter(assessment__in=assessments, student=student).select_related("assessment")
    grade_map = {g.assessment_id: g for g in grades}

    if request.method == "POST":
        with transaction.atomic():
            for a in assessments:
                score_key = f"grade-{a.id}"
                comment_key = f"comment-{a.id}"
                raw_score = (request.POST.get(score_key) or "").strip()
                raw_comment = (request.POST.get(comment_key) or "").strip()
                if raw_comment and len(raw_comment) >= 50:
                    messages.error(request, f"Комментарий слишком длинный: {a.title}")
                    continue

                score_val = None
                if raw_score != "":
                    if not raw_score.isdigit():
                        messages.error(request, f"Некорректный результат: {a.title}")
                        continue
                    try:
                        score_int = int(raw_score)
                    except ValueError:
                        messages.error(request, f"Некорректный результат: {a.title}")
                        continue
                    if score_int < 0 or score_int > 100:
                        messages.error(request, f"Результат вне диапазона 0–100: {a.title}")
                        continue
                    score_val = Decimal(score_int)

                obj, _created = Grade.objects.get_or_create(assessment=a, student=student)
                obj.score = score_val
                obj.comment = raw_comment
                obj.save()

        messages.success(request, "Результаты сохранены.")
        return redirect(f"/teacher/students/{student.id}/results/")

    rows = [{"assessment": a, "grade": grade_map.get(a.id)} for a in assessments]
    return render(
        request,
        "gradebook/teacher_student_results.html",
        {
            "course": course,
            "student": student,
            "rows": rows,
        },
    )
