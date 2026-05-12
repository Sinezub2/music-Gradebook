from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.db.models import Avg, Count, Q
from django.utils import timezone
from urllib.parse import urlencode

from apps.accounts.forms import TeacherStudentCycleForm
from apps.accounts.models import Profile
from apps.gradebook.models import Grade
from apps.goals.models import Goal
from apps.homework.models import AssignmentTarget
from apps.lessons.models import LessonReport, LessonStudent
from apps.lessons.models import Lesson
from apps.schedule.models import Event
from .forms import CourseInternalGroupForm
from .models import Course, CourseInternalGroup, Enrollment, ParentChild
from .utils import (
    extract_school_grade_number,
    get_group_student_enrollments,
    get_student_internal_groups_for_course,
    get_teacher_group_courses,
    get_teacher_group_or_404,
    get_teacher_group_student_or_404,
    get_teacher_student_or_404,
    get_teacher_students,
    get_user_single_class,
    normalize_school_grade_label,
    resolve_course_scope,
    resolve_teacher_course_for_student,
)


INTERNAL_GROUP_DEFAULT_NAMES = {
    CourseInternalGroup.GroupType.SPLIT: "Подгруппа",
    CourseInternalGroup.GroupType.REMEDIAL: "Нужна поддержка",
    CourseInternalGroup.GroupType.ADVANCED: "Продвинутые",
}


def _build_internal_group_name(course: Course, group_type: str, raw_name: str) -> str:
    base_name = (raw_name or "").strip() or INTERNAL_GROUP_DEFAULT_NAMES.get(group_type, "Своя группа")
    if not course.internal_groups.filter(name=base_name).exists():
        return base_name

    suffix = 2
    while True:
        candidate = f"{base_name} {suffix}"
        if not course.internal_groups.filter(name=candidate).exists():
            return candidate
        suffix += 1


def _build_event_create_url(*, course_id: int, preset: str, student_id: int | None = None) -> str:
    params = {"course": course_id, "preset": preset}
    if student_id:
        params["students"] = str(student_id)
    return f"/calendar/create/?{urlencode(params)}"


def _build_group_event_shortcuts(group: Course, *, include_grade_4: bool, include_grade_7: bool) -> list[dict]:
    rows = [
        {"label": "Квиз", "url": _build_event_create_url(course_id=group.id, preset="quiz")},
        {"label": "Контроль", "url": _build_event_create_url(course_id=group.id, preset="control")},
        {"label": "Итоговая", "url": _build_event_create_url(course_id=group.id, preset="final")},
        {"label": "Промежуточная проверка", "url": _build_event_create_url(course_id=group.id, preset="milestone")},
    ]
    if include_grade_4:
        rows.append({"label": "Оценка 4 класса", "url": _build_event_create_url(course_id=group.id, preset="grade4_final")})
    if include_grade_7:
        rows.append({"label": "Оценка 7 класса", "url": _build_event_create_url(course_id=group.id, preset="grade7_final")})
    return rows


def _build_shared_course_rows(student, *, exclude_teacher=None) -> list[dict]:
    enrollments = list(
        Enrollment.objects.filter(student=student)
        .exclude(course__teacher=exclude_teacher)
        .select_related("course", "course__course_type", "course__teacher")
        .order_by("course__name", "course_id")
    )
    if not enrollments:
        return []

    course_ids = [enrollment.course_id for enrollment in enrollments]
    latest_lessons = {}
    for lesson in Lesson.objects.filter(course_id__in=course_ids).select_related("course").order_by("course_id", "-date", "-id"):
        latest_lessons.setdefault(lesson.course_id, lesson)

    recent_grades_map = {}
    grades_qs = (
        Grade.objects.filter(student=student, assessment__course_id__in=course_ids)
        .select_related("assessment", "assessment__course")
        .order_by("assessment__course_id", "-assessment_id")
    )
    for grade in grades_qs:
        bucket = recent_grades_map.setdefault(grade.assessment.course_id, [])
        if len(bucket) < 3:
            bucket.append(grade)

    next_events = {}
    events_qs = (
        Event.objects.exclude(event_type=Event.EventType.LESSON)
        .filter(course_id__in=course_ids, start_datetime__gte=timezone.now())
        .select_related("course")
        .order_by("start_datetime", "id")
    )
    for event in events_qs:
        next_events.setdefault(event.course_id, event)

    rows = []
    for enrollment in enrollments:
        course = enrollment.course
        latest_lesson = latest_lessons.get(course.id)
        next_event = next_events.get(course.id)
        rows.append(
            {
                "course": course,
                "teacher_label": (course.teacher.get_full_name() or "").strip() or getattr(course.teacher, "username", "") or "Преподаватель не назначен",
                "latest_lesson": latest_lesson,
                "recent_grades": recent_grades_map.get(course.id, []),
                "next_event": next_event,
                "school_grade": normalize_school_grade_label(student.profile.school_grade),
            }
        )
    return rows


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
            children = (
                ParentChild.objects.filter(parent=request.user)
                .select_related("child")
                .order_by("child__first_name", "child__last_name", "child__username")
            )
            return render(request, "school/course_list.html", {"children_links": children, "mode": "parent_pick"})
        link = get_object_or_404(ParentChild, parent=request.user, child_id=student_id)
        child = link.child
        courses = Course.objects.filter(enrollments__student=child).distinct().order_by("name")
        return render(request, "school/course_list.html", {"courses": courses, "mode": "parent_child", "student": child})

    if profile.role == Profile.Role.TEACHER:
        redirect_url = profile.teacher_home_url
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
    if profile.can_access_group_teacher_flow and not profile.can_access_individual_teacher_flow:
        return redirect("/teacher/groups/")

    cycle = request.GET.get("cycle") or ""
    students = list(get_teacher_students(request.user, cycle=cycle))
    student_ids = [student.id for student in students]

    course_map = {}
    enrollments = (
        Enrollment.objects.filter(course__teacher=request.user, student_id__in=student_ids)
        .select_related("course", "course__course_type")
        .order_by("course__name")
    )
    for enrollment in enrollments:
        course_map.setdefault(enrollment.student_id, []).append(enrollment.course)

    grade_rows = (
        Grade.objects.filter(student_id__in=student_ids, assessment__course__teacher=request.user, score__isnull=False)
        .values("student_id")
        .annotate(avg_score=Avg("score"))
    )
    grade_map = {row["student_id"]: row["avg_score"] for row in grade_rows}

    attendance_rows = (
        LessonStudent.objects.filter(student_id__in=student_ids, lesson__course__teacher=request.user)
        .values("student_id")
        .annotate(total=Count("id"), present=Count("id", filter=Q(attended=True)))
    )
    attendance_map = {row["student_id"]: row for row in attendance_rows}

    student_cards = []
    attendance_values = []
    for student in students:
        courses = course_map.get(student.id, [])
        instruments = ", ".join(sorted({course.course_type.name for course in courses})) if courses else "Без направления"
        level_label = student.profile.get_cycle_display()

        avg_score = grade_map.get(student.id)
        avg_score_label = f"{float(avg_score):.1f}" if avg_score is not None else "—"

        attendance_row = attendance_map.get(student.id, {"total": 0, "present": 0})
        total_lessons = attendance_row["total"] or 0
        present_lessons = attendance_row["present"] or 0
        attendance_percent = round((present_lessons * 100) / total_lessons) if total_lessons else None
        if attendance_percent is not None:
            attendance_values.append(attendance_percent)

        student_cards.append(
            {
                "student": student,
                "instruments": instruments,
                "level_label": level_label,
                "avg_score_label": avg_score_label,
                "attendance_percent": attendance_percent,
                "courses_label": ", ".join(course.name for course in courses),
            }
        )

    summary_stats = {
        "students_total": len(student_cards),
        "avg_attendance": round(sum(attendance_values) / len(attendance_values)) if attendance_values else 0,
        "active_cycles": len({card["level_label"] for card in student_cards}),
    }

    return render(
        request,
        "teacher/class_list.html",
        {
            "students": students,
            "student_cards": student_cards,
            "summary_stats": summary_stats,
            "cycle": cycle,
            "cycle_options": Profile.Cycle.choices,
        },
    )


@login_required
def teacher_group_list(request):
    profile = request.user.profile
    if profile.role != Profile.Role.TEACHER:
        return HttpResponseForbidden("Доступ запрещён.")
    if not profile.can_access_group_teacher_flow:
        return redirect("/teacher/class/")

    groups = list(get_teacher_group_courses(request.user))
    group_cards = []
    for group in groups:
        assignment_qs = group.assignments.all()
        total_targets = AssignmentTarget.objects.filter(assignment__course=group).count()
        done_targets = AssignmentTarget.objects.filter(
            assignment__course=group,
            status=AssignmentTarget.Status.DONE,
        ).count()
        latest_lesson = group.lessons.order_by("-date", "-id").first()
        group_cards.append(
            {
                "group": group,
                "student_total": getattr(group, "student_total", group.enrollments.count()),
                "assignment_total": assignment_qs.count(),
                "done_targets": done_targets,
                "total_targets": total_targets,
                "latest_lesson": latest_lesson,
            }
        )

    return render(
        request,
        "teacher/group_list.html",
        {
            "group_cards": group_cards,
        },
    )


@login_required
def teacher_group_detail(request, group_id: int):
    profile = request.user.profile
    if profile.role != Profile.Role.TEACHER:
        return HttpResponseForbidden("Доступ запрещён.")
    if not profile.can_access_group_teacher_flow:
        return redirect("/teacher/class/")

    group = get_teacher_group_or_404(request.user, group_id)
    enrollments = list(get_group_student_enrollments(group))
    scope_value = (request.POST.get("scope") or request.GET.get("scope") or "").strip()
    selected_scope, scoped_enrollments, scope_options = resolve_course_scope(group, scope_value, enrollments=enrollments)
    students = [enrollment.student for enrollment in scoped_enrollments]
    student_ids = [student.id for student in students]
    student_id_set = set(student_ids)
    classroom_options = [option for option in scope_options if option["kind"] == "classroom"]
    has_grade_4 = any(extract_school_grade_number(option["label"]) == "4" for option in classroom_options)
    has_grade_7 = any(extract_school_grade_number(option["label"]) == "7" for option in classroom_options)

    internal_group_form = CourseInternalGroupForm(course=group)
    if request.method == "POST" and request.POST.get("action") == "create_internal_group":
        internal_group_form = CourseInternalGroupForm(request.POST, course=group)
        if internal_group_form.is_valid():
            chosen_name = _build_internal_group_name(
                group,
                internal_group_form.cleaned_data["group_type"],
                internal_group_form.cleaned_data["name"],
            )
            internal_group = CourseInternalGroup.objects.create(
                course=group,
                name=chosen_name,
                group_type=internal_group_form.cleaned_data["group_type"],
            )
            valid_student_ids = [student_id for student_id in internal_group_form.cleaned_data["students"] if student_id in student_id_set or student_id in {row.student_id for row in enrollments}]
            internal_group.students.set(valid_student_ids)
            messages.success(request, "Внутренняя группа сохранена.")
            return redirect(f"/teacher/groups/{group.id}/?scope=internal:{internal_group.id}")

    recent_assignment_rows = []
    assignments = list(
        group.assignments.all()
        .prefetch_related("targets")
        .order_by("-due_date", "-id")[:5]
    )
    for assignment in assignments:
        targets_qs = assignment.targets.all()
        if student_ids:
            targets_qs = targets_qs.filter(student_id__in=student_ids)
        total = targets_qs.count()
        done = targets_qs.filter(status=AssignmentTarget.Status.DONE).count()
        recent_assignment_rows.append(
            {
                "assignment": assignment,
                "done_targets": done,
                "total_targets": total,
            }
        )
    recent_lessons = list(group.lessons.order_by("-date", "-id")[:5])
    recent_materials = [lesson for lesson in recent_lessons if lesson.attachment][:3]
    grade_rows = (
        Grade.objects.filter(student_id__in=student_ids, assessment__course=group, score__isnull=False)
        .values("student_id")
        .annotate(avg_score=Avg("score"))
    )
    grade_map = {row["student_id"]: row["avg_score"] for row in grade_rows}

    student_rows = []
    internal_groups = list(group.internal_groups.prefetch_related("students").order_by("name", "id"))
    internal_group_map = {}
    for internal_group in internal_groups:
        for student in internal_group.students.all():
            internal_group_map.setdefault(student.id, []).append(internal_group)

    for enrollment in enrollments:
        if enrollment.student_id not in student_id_set:
            continue
        student = enrollment.student
        targets_qs = AssignmentTarget.objects.filter(student=student, assignment__course=group)
        total_targets = targets_qs.count()
        done_targets = targets_qs.filter(status=AssignmentTarget.Status.DONE).count()
        student_rows.append(
            {
                "student": student,
                "avg_score": grade_map.get(student.id),
                "done_targets": done_targets,
                "total_targets": total_targets,
                "school_grade": normalize_school_grade_label(student.profile.school_grade),
                "internal_groups": internal_group_map.get(student.id, []),
            }
        )

    total_targets_qs = AssignmentTarget.objects.filter(assignment__course=group)
    if student_ids:
        total_targets_qs = total_targets_qs.filter(student_id__in=student_ids)
    total_targets = total_targets_qs.count()
    done_targets = AssignmentTarget.objects.filter(
        assignment__course=group,
        status=AssignmentTarget.Status.DONE,
    )
    if student_ids:
        done_targets = done_targets.filter(student_id__in=student_ids)
    done_targets = done_targets.count()
    latest_lesson = recent_lessons[0] if recent_lessons else None
    upcoming_events = list(
        Event.objects.exclude(event_type=Event.EventType.LESSON)
        .filter(course=group, start_datetime__gte=timezone.now())
        .order_by("start_datetime", "id")[:4]
    )

    return render(
        request,
        "teacher/group_detail.html",
        {
            "group": group,
            "student_rows": student_rows,
            "recent_assignments": recent_assignment_rows,
            "recent_lessons": recent_lessons,
            "recent_materials": recent_materials,
            "scope_options": scope_options,
            "selected_scope": selected_scope,
            "internal_group_form": internal_group_form,
            "upcoming_events": upcoming_events,
            "event_shortcuts": _build_group_event_shortcuts(
                group,
                include_grade_4=has_grade_4,
                include_grade_7=has_grade_7,
            ),
            "summary_stats": {
                "students_total": len(students),
                "assignments_total": group.assignments.count(),
                "done_targets": done_targets,
                "total_targets": total_targets,
                "topics_total": group.lessons.count(),
            },
            "latest_lesson": latest_lesson,
        },
    )


@login_required
def teacher_group_student_detail(request, group_id: int, student_id: int):
    profile = request.user.profile
    if profile.role != Profile.Role.TEACHER:
        return HttpResponseForbidden("Доступ запрещён.")
    if not profile.can_access_group_teacher_flow:
        return redirect("/teacher/class/")

    group = get_teacher_group_or_404(request.user, group_id)
    enrollment = get_teacher_group_student_or_404(request.user, group, student_id)
    student = enrollment.student

    recent_assignments = list(
        AssignmentTarget.objects.filter(student=student, assignment__course=group)
        .select_related("assignment")
        .order_by("-assignment__due_date", "-assignment_id")[:8]
    )
    recent_grades = list(
        Grade.objects.filter(student=student, assessment__course=group)
        .select_related("assessment")
        .order_by("-assessment_id")[:8]
    )
    attendance_rows = list(
        LessonStudent.objects.filter(student=student, lesson__course=group)
        .select_related("lesson")
        .order_by("-lesson__date", "-lesson_id")[:8]
    )
    latest_lesson_entry = attendance_rows[0] if attendance_rows else None
    student_internal_groups = list(get_student_internal_groups_for_course(student, group))
    upcoming_events = list(
        Event.objects.exclude(event_type=Event.EventType.LESSON)
        .filter(Q(course=group) | Q(participants=student), start_datetime__gte=timezone.now())
        .distinct()
        .order_by("start_datetime", "id")[:4]
    )

    return render(
        request,
        "teacher/group_student_detail.html",
        {
            "group": group,
            "student": student,
            "recent_assignments": recent_assignments,
            "recent_grades": recent_grades,
            "attendance_rows": attendance_rows,
            "latest_lesson_entry": latest_lesson_entry,
            "student_internal_groups": student_internal_groups,
            "upcoming_events": upcoming_events,
        },
    )


@login_required
def teacher_student_workspace(request, student_id: int):
    profile = request.user.profile
    if profile.role != Profile.Role.TEACHER:
        return HttpResponseForbidden("Доступ запрещён.")

    student = get_teacher_student_or_404(request.user, student_id)
    cycle_form = TeacherStudentCycleForm(instance=student.profile)
    if request.method == "POST":
        cycle_form = TeacherStudentCycleForm(request.POST, instance=student.profile)
        if cycle_form.is_valid():
            cycle_form.save()
            messages.success(request, "Цикл ученика обновлён.")
            return redirect(f"/teacher/students/{student.id}/")

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
    shared_course_rows = _build_shared_course_rows(student, exclude_teacher=request.user)
    current_half_year = "H1" if timezone.localdate().month <= 6 else "H2"

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
            "shared_course_rows": shared_course_rows,
            "current_half_year": current_half_year,
            "cycle_form": cycle_form,
        },
    )
