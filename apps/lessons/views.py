from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.db.models import Count, Q
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from datetime import date, datetime, timedelta
from urllib.parse import urlencode
import json

from apps.accounts.decorators import role_required
from apps.accounts.models import Profile
from apps.school.models import Course, Enrollment, ParentChild
from apps.school.utils import get_user_single_class
from .forms import LessonCreateForm, SlotReportForm, StudentLessonCreateForm, StudentScheduleForm
from .models import Lesson, LessonReport, LessonSlot, LessonStudent, StudentSchedule
from .services import generate_slots_for_schedule
from apps.school.utils import get_teacher_student_or_404, resolve_teacher_course_for_student


PLAYS_PREFIX = "__plays__:"


def _student_ids_for_user(request):
    role = request.user.profile.role
    if role == Profile.Role.STUDENT:
        return [request.user.id]
    if role == Profile.Role.PARENT:
        return list(ParentChild.objects.filter(parent=request.user).values_list("child_id", flat=True))
    return []


def _can_delete_lesson(user, role: str, lesson: Lesson) -> bool:
    if role == Profile.Role.ADMIN:
        return True
    if role != Profile.Role.TEACHER:
        return False
    return lesson.created_by_id == user.id or lesson.course.teacher_id == user.id


def _build_lessons_url(*, course_id, student_id):
    params = {}
    if course_id:
        params["course"] = course_id
    if student_id:
        params["student"] = student_id
    return f"/lessons/?{urlencode(params)}" if params else "/lessons/"


def _parse_play_entries(raw_result: str) -> list[dict]:
    value = (raw_result or "").strip()
    if not value.startswith(PLAYS_PREFIX):
        return []
    try:
        payload = json.loads(value[len(PLAYS_PREFIX) :])
    except json.JSONDecodeError:
        return []
    plays = []
    for item in payload if isinstance(payload, list) else []:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        plays.append(
            {
                "name": name,
                "completed": bool(item.get("completed")),
                "comment": str(item.get("comment", "")).strip(),
            }
        )
    return plays


def _serialize_play_entries(plays: list[dict]) -> str:
    cleaned = []
    for play in plays:
        name = str(play.get("name", "")).strip()
        if not name:
            continue
        cleaned.append(
            {
                "name": name,
                "completed": bool(play.get("completed")),
                "comment": str(play.get("comment", "")).strip(),
            }
        )
    return f"{PLAYS_PREFIX}{json.dumps(cleaned, ensure_ascii=False)}"


def _collect_play_entries(request) -> list[dict]:
    names = request.POST.getlist("play_name")
    comments = request.POST.getlist("play_comment")
    completed_indexes = set()
    for value in request.POST.getlist("play_completed"):
        try:
            completed_indexes.add(int(value))
        except (TypeError, ValueError):
            continue
    plays = []
    for index, raw_name in enumerate(names):
        name = (raw_name or "").strip()
        comment = (comments[index] if index < len(comments) else "").strip()
        if not name:
            continue
        plays.append(
            {
                "name": name,
                "completed": index in completed_indexes,
                "comment": comment,
            }
        )
    return plays


def _collect_schedule_rows(post_data) -> list[dict]:
    weekdays = post_data.getlist("weekday")
    lesson_numbers = post_data.getlist("lesson_number")
    start_times = post_data.getlist("start_time")
    duration_minutes = post_data.getlist("duration_minutes")
    total = max(len(weekdays), len(lesson_numbers), len(start_times), len(duration_minutes), 1)
    rows = []
    for index in range(total):
        rows.append(
            {
                "weekday": (weekdays[index] if index < len(weekdays) else "").strip(),
                "lesson_number": (lesson_numbers[index] if index < len(lesson_numbers) else "").strip(),
                "start_time": (start_times[index] if index < len(start_times) else "").strip(),
                "duration_minutes": (duration_minutes[index] if index < len(duration_minutes) else "").strip(),
                "errors": {},
            }
        )
    return rows


def _plays_to_summary(plays: list[dict]) -> str:
    if not plays:
        return ""
    return "; ".join(
        f"{play['name']}{' ✓' if play.get('completed') else ''}" for play in plays
    )


def _build_topic_from_plays(plays: list[dict]) -> str:
    names = [play["name"] for play in plays if play.get("name")]
    if not names:
        return "Композиции"
    return ", ".join(names)[:200]


def _active_plays_for_student(student) -> list[dict]:
    latest_entry = (
        LessonStudent.objects.filter(student=student)
        .select_related("lesson")
        .order_by("-lesson__date", "-lesson_id")
        .first()
    )
    if not latest_entry:
        return []
    plays = _parse_play_entries(latest_entry.result)
    return [{"name": play["name"], "completed": False, "comment": ""} for play in plays if not play.get("completed")]


def _active_plays_for_slot(slot: LessonSlot) -> list[dict]:
    if slot.lesson_id:
        current_entry = LessonStudent.objects.filter(lesson=slot.lesson, student=slot.student).first()
        if current_entry:
            current_plays = _parse_play_entries(current_entry.result)
            if current_plays:
                return current_plays

    latest_done_slot = (
        LessonSlot.objects.filter(
            teacher=slot.teacher,
            student=slot.student,
            status=LessonSlot.Status.DONE,
            lesson__isnull=False,
        )
        .exclude(id=slot.id)
        .order_by("-scheduled_date", "-start_time", "-id")
        .first()
    )
    if not latest_done_slot:
        return []

    latest_entry = LessonStudent.objects.filter(
        lesson=latest_done_slot.lesson,
        student=slot.student,
    ).first()
    if not latest_entry:
        return []

    previous_plays = _parse_play_entries(latest_entry.result)
    return [{"name": play["name"], "completed": False, "comment": ""} for play in previous_plays if not play.get("completed")]


def _slot_attended_bool(attendance_status: str) -> bool:
    return attendance_status in (
        LessonSlot.AttendanceStatus.PRESENT,
        LessonSlot.AttendanceStatus.LATE,
    )


@login_required
def lesson_list(request):
    role = request.user.profile.role
    course_id = request.GET.get("course")
    student_id = request.GET.get("student")
    no_class_message = ""
    select_mode = request.GET.get("select") == "1"

    if role != Profile.Role.ADMIN:
        class_resolution = get_user_single_class(request.user)
        if class_resolution.status == "none":
            no_class_message = "Класс не назначен. Обратитесь к администратору."
        elif class_resolution.status == "single":
            course_id = str(class_resolution.course.id)

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
    if no_class_message:
        lessons_qs = Lesson.objects.none()
    elif role == Profile.Role.ADMIN:
        lessons_qs = Lesson.objects.all().select_related("course", "created_by")
        student_ids = Enrollment.objects.values_list("student_id", flat=True).distinct()
        students = list(
            user_model.objects.filter(id__in=student_ids).select_related("profile").order_by("first_name", "last_name", "username")
        )
    elif role == Profile.Role.TEACHER:
        lessons_qs = Lesson.objects.filter(course__teacher=request.user).select_related("course", "created_by")
        student_ids = (
            Enrollment.objects.filter(course__teacher=request.user).values_list("student_id", flat=True).distinct()
        )
        students = list(
            user_model.objects.filter(id__in=student_ids).select_related("profile").order_by("first_name", "last_name", "username")
        )
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
                user_model.objects.filter(id__in=student_ids)
                .select_related("profile")
                .order_by("first_name", "last_name", "username")
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
                "result": _plays_to_summary(_parse_play_entries(entry.result))
                or student_report_map.get(entry.lesson_id)
                or general_report_map.get(entry.lesson_id)
                or "",
                "can_delete": _can_delete_lesson(request.user, role, entry.lesson),
            }
            for entry in entries_qs.order_by("-lesson__date", "-lesson_id")
        ]
    else:
        ordered_lessons = list(lessons_qs.order_by("-date", "-id"))
        lesson_entries = (
            LessonStudent.objects.filter(lesson__in=ordered_lessons)
            .select_related("lesson")
            .order_by("lesson_id", "id")
        )
        summary_by_lesson = {}
        for entry in lesson_entries:
            if entry.lesson_id in summary_by_lesson:
                continue
            summary = _plays_to_summary(_parse_play_entries(entry.result))
            if summary:
                summary_by_lesson[entry.lesson_id] = summary
        rows = [
            {
                "lesson": lesson,
                "attendance": None,
                "result": summary_by_lesson.get(lesson.id, ""),
                "can_delete": _can_delete_lesson(request.user, role, lesson),
            }
            for lesson in ordered_lessons
        ]

    base_url = _build_lessons_url(course_id=course_id, student_id=student_id)
    select_url = f"{base_url}{'&' if '?' in base_url else '?'}select=1"

    return render(
        request,
        "lessons/lesson_list.html",
        {
            "lessons": rows,
            "course_id": course_id,
            "students": students,
            "student_id": str(student_id) if student_id else "",
            "selected_student": selected_student,
            "no_class_message": no_class_message,
            "can_bulk_delete": role in (Profile.Role.TEACHER, Profile.Role.ADMIN),
            "select_mode": select_mode,
            "select_url": select_url,
            "cancel_select_url": base_url,
        },
    )


@require_POST
@role_required(Profile.Role.TEACHER, Profile.Role.ADMIN)
def lesson_bulk_delete(request):
    role = request.user.profile.role
    selected_ids = []
    for raw_id in request.POST.getlist("selected_ids"):
        try:
            selected_ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue

    course_id = request.POST.get("course") or ""
    student_id = request.POST.get("student") or ""
    redirect_url = _build_lessons_url(course_id=course_id, student_id=student_id)

    if not selected_ids:
        messages.info(request, "Ничего не выбрано для удаления.")
        return redirect(redirect_url)

    lessons = list(Lesson.objects.filter(id__in=selected_ids).select_related("course", "created_by"))
    unauthorized = [lesson.id for lesson in lessons if not _can_delete_lesson(request.user, role, lesson)]
    if unauthorized:
        return HttpResponseForbidden("Нет доступа к удалению выбранных уроков.")

    deleted_count = 0
    for lesson in lessons:
        lesson.delete()
        deleted_count += 1

    messages.success(request, f"Удалено уроков: {deleted_count}.")
    return redirect(redirect_url)


@login_required
def attendance_journal(request):
    role = request.user.profile.role
    course_id = request.GET.get("course")
    course_id_int = None
    selected_course = None
    show_course_selector = False
    no_class_message = ""
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
        show_course_selector = True
    else:
        class_resolution = get_user_single_class(request.user)
        if class_resolution.status == "none":
            no_class_message = "Класс не назначен. Обратитесь к администратору."
        elif class_resolution.status == "single":
            selected_course = class_resolution.course
            course_id_int = selected_course.id
            allowed_courses = Course.objects.filter(id=selected_course.id)
        else:
            show_course_selector = True
            if role == Profile.Role.TEACHER:
                allowed_courses = Course.objects.filter(teacher=request.user)
            else:
                student_ids = _student_ids_for_user(request)
                allowed_courses = Course.objects.filter(enrollments__student_id__in=student_ids).distinct()

    allowed_courses = allowed_courses.order_by("name")
    allowed_course_ids = set(allowed_courses.values_list("id", flat=True))

    if show_course_selector and course_id:
        try:
            course_id_int = int(course_id)
        except ValueError:
            course_id_int = None

    if course_id_int and course_id_int not in allowed_course_ids:
        return HttpResponseForbidden("Нет доступа.")

    if course_id_int:
        if role in (Profile.Role.ADMIN, Profile.Role.TEACHER):
            student_ids = Enrollment.objects.filter(course_id=course_id_int).values_list("student_id", flat=True).distinct()
        else:
            allowed_student_ids = _student_ids_for_user(request)
            student_ids = Enrollment.objects.filter(course_id=course_id_int, student_id__in=allowed_student_ids).values_list("student_id", flat=True).distinct()
        students = list(
            user_model.objects.filter(id__in=student_ids).select_related("profile").order_by("first_name", "last_name", "username")
        )

    slots_qs = LessonSlot.objects.none()
    if course_id_int:
        slots_qs = LessonSlot.objects.filter(
            course_id=course_id_int,
            scheduled_date__gte=month_start,
            scheduled_date__lt=month_end,
            student__in=students,
        ).select_related("student", "teacher", "course")

    slot_dates = list(slots_qs.order_by("scheduled_date").values_list("scheduled_date", flat=True).distinct())

    attendance_map = {}
    for slot in slots_qs.order_by("scheduled_date", "start_time", "id"):
        value = None if slot.status == LessonSlot.Status.PLANNED else slot.attendance_status
        attendance_map.setdefault(slot.scheduled_date, {})[slot.student_id] = value

    done_counts = (
        slots_qs.filter(status=LessonSlot.Status.DONE)
        .values("student_id")
        .annotate(total=Count("id"))
    )
    total_lessons_by_student = {row["student_id"]: row["total"] for row in done_counts}
    overall_done_slots = sum(total_lessons_by_student.values())

    rows = []
    for slot_date in slot_dates:
        cells = []
        for student in students:
            attendance_status = attendance_map.get(slot_date, {}).get(student.id)
            cells.append({"student": student, "attendance_status": attendance_status})
        rows.append({"date": slot_date, "cells": cells})

    totals = [
        {
            "student": student,
            "done_slots": total_lessons_by_student.get(student.id, 0),
            "label": str(total_lessons_by_student.get(student.id, 0)),
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
            "overall_total_label": str(overall_done_slots),
            "show_course_selector": show_course_selector,
            "selected_course": selected_course,
            "no_class_message": no_class_message,
        },
    )


@role_required(Profile.Role.TEACHER, Profile.Role.ADMIN)
def lesson_create(request):
    if request.user.profile.role == Profile.Role.TEACHER:
        messages.info(request, "Сначала выберите ученика в разделе «Класс».")
        return redirect("/teacher/class/")

    fixed_course = None
    if request.user.profile.role == Profile.Role.TEACHER:
        class_resolution = get_user_single_class(request.user)
        if class_resolution.status == "none":
            messages.error(request, "Класс не назначен. Обратитесь к администратору.")
            return redirect("/lessons/")
        if class_resolution.status == "single":
            fixed_course = class_resolution.course

    course_queryset = Course.objects.filter(id=fixed_course.id) if fixed_course else None
    initial_plays = [{"name": "", "completed": False, "comment": ""}]
    play_errors = []

    if request.method == "POST":
        initial_plays = _collect_play_entries(request) or [{"name": "", "completed": False, "comment": ""}]
        form = LessonCreateForm(
            request.POST,
            request.FILES,
            teacher_user=(request.user if request.user.profile.role == Profile.Role.TEACHER else None),
            course_queryset=course_queryset,
        )
        if form.is_valid():
            plays = _collect_play_entries(request)
            if not plays:
                play_errors = ["Добавьте хотя бы одну композицию."]
            if play_errors:
                return render(
                    request,
                    "lessons/lesson_create.html",
                    {
                        "form": form,
                        "fixed_course": fixed_course,
                        "initial_plays": initial_plays,
                        "play_errors": play_errors,
                    },
                )
            course = fixed_course or form.cleaned_data["course"]
            if request.user.profile.role == Profile.Role.TEACHER and course.teacher_id != request.user.id:
                return HttpResponseForbidden("Нельзя создавать уроки для чужого курса.")

            lesson = Lesson.objects.create(
                course=course,
                date=form.cleaned_data["date"],
                topic=_build_topic_from_plays(plays),
                created_by=request.user,
                attachment=form.cleaned_data.get("attachment"),
            )

            enrollments = Enrollment.objects.filter(course=course).select_related("student")
            result = _serialize_play_entries(plays)
            LessonStudent.objects.bulk_create(
                [
                    LessonStudent(lesson=lesson, student=enrollment.student, attended=True, result=result)
                    for enrollment in enrollments
                ]
            )

            media = (form.cleaned_data.get("media_url") or "").strip()
            if media:
                LessonReport.objects.create(lesson=lesson, student=None, text="", media_url=media)

            messages.success(request, "Урок создан.")
            return redirect(f"/lessons/{lesson.id}/")
    else:
        form = LessonCreateForm(
            teacher_user=(request.user if request.user.profile.role == Profile.Role.TEACHER else None),
            course_queryset=course_queryset,
        )
        if fixed_course:
            form.initial["course"] = fixed_course

    return render(
        request,
        "lessons/lesson_create.html",
        {
            "form": form,
            "fixed_course": fixed_course,
            "initial_plays": initial_plays,
            "play_errors": play_errors,
        },
    )


@role_required(Profile.Role.TEACHER)
def lesson_create_for_student(request, student_id: int):
    messages.info(request, "Создание урока перенесено в расписание. Заполните отчёт в слоте занятия.")
    return redirect(f"/teacher/students/{student_id}/schedule/")


@role_required(Profile.Role.TEACHER)
def student_schedule_manage(request, student_id: int):
    student = get_teacher_student_or_404(request.user, student_id)
    course, status = resolve_teacher_course_for_student(request.user, student)
    if status == "none":
        messages.error(request, "Ученик не назначен на ваш курс.")
        return redirect(f"/teacher/students/{student.id}/")
    show_course_notice = status == "multiple"

    today = timezone.localdate()
    form = StudentScheduleForm()
    default_duration = str(form.fields["duration_minutes"].initial or 45)
    schedule_input_rows = [
        {
            "weekday": "",
            "lesson_number": "",
            "start_time": "",
            "duration_minutes": default_duration,
            "errors": {},
        }
    ]
    schedule_form_error = ""

    if request.method == "POST":
        action = request.POST.get("action", "add")

        if action == "toggle":
            schedule = get_object_or_404(
                StudentSchedule,
                id=request.POST.get("schedule_id"),
                teacher=request.user,
                student=student,
            )
            schedule.active = not schedule.active
            schedule.save(update_fields=["active", "updated_at"])
            if schedule.active:
                created_slots = generate_slots_for_schedule(schedule)
                messages.success(request, f"Расписание активировано. Новых слотов: {created_slots}.")
            else:
                messages.success(request, "Расписание деактивировано.")
            return redirect(f"/teacher/students/{student.id}/schedule/")

        schedule_input_rows = _collect_schedule_rows(request.POST)
        valid_rows = []
        has_filled_rows = False
        has_errors = False

        for index, row in enumerate(schedule_input_rows):
            row_data = {
                "weekday": row["weekday"],
                "lesson_number": row["lesson_number"],
                "start_time": row["start_time"],
                "duration_minutes": row["duration_minutes"],
            }
            is_empty = not any(
                [
                    row_data["weekday"],
                    row_data["lesson_number"],
                    row_data["start_time"],
                ]
            )
            if is_empty:
                row["duration_minutes"] = default_duration
                continue
            has_filled_rows = True
            row_data["duration_minutes"] = row_data["duration_minutes"] or default_duration
            row["duration_minutes"] = row_data["duration_minutes"]

            row_form = StudentScheduleForm(row_data)
            if row_form.is_valid():
                valid_rows.append((index, row_form.cleaned_data))
                continue

            has_errors = True
            row["errors"] = {
                field: " ".join(str(error) for error in errors)
                for field, errors in row_form.errors.items()
            }

        seen_pairs = {}
        for index, cleaned_data in valid_rows:
            pair = (int(cleaned_data["weekday"]), cleaned_data["start_time"])
            previous_index = seen_pairs.get(pair)
            if previous_index is None:
                seen_pairs[pair] = index
                continue
            has_errors = True
            duplicate_error = "Дубликат дня и времени в форме."
            schedule_input_rows[index]["errors"]["start_time"] = duplicate_error
            schedule_input_rows[previous_index]["errors"]["start_time"] = duplicate_error

        if not has_filled_rows:
            has_errors = True
            schedule_form_error = "Добавьте хотя бы один день и время."

        if not has_errors:
            saved_rows = 0
            created_slots_total = 0
            for _, cleaned_data in valid_rows:
                weekday = int(cleaned_data["weekday"])
                start_time = cleaned_data["start_time"]
                lesson_number = cleaned_data.get("lesson_number")
                duration_minutes = cleaned_data["duration_minutes"]
                schedule, created = StudentSchedule.objects.get_or_create(
                    teacher=request.user,
                    student=student,
                    weekday=weekday,
                    start_time=start_time,
                    defaults={
                        "course": course,
                        "lesson_number": lesson_number,
                        "duration_minutes": duration_minutes,
                        "active": True,
                    },
                )
                if not created:
                    schedule.course = course
                    schedule.lesson_number = lesson_number
                    schedule.duration_minutes = duration_minutes
                    schedule.active = True
                    schedule.save(update_fields=["course", "lesson_number", "duration_minutes", "active", "updated_at"])

                created_slots_total += generate_slots_for_schedule(schedule)
                saved_rows += 1

            messages.success(request, f"Шаблонов сохранено: {saved_rows}. Слотов создано: {created_slots_total}.")
            return redirect(f"/teacher/students/{student.id}/schedule/")

    schedules = list(
        StudentSchedule.objects.filter(teacher=request.user, student=student)
        .select_related("course")
        .order_by("weekday", "start_time", "id")
    )
    upcoming_slots = list(
        LessonSlot.objects.filter(teacher=request.user, student=student, scheduled_date__gte=today)
        .select_related("course")
        .order_by("scheduled_date", "start_time", "id")[:30]
    )

    return render(
        request,
        "lessons/student_schedule.html",
        {
            "student": student,
            "course": course,
            "show_course_notice": show_course_notice,
            "form": form,
            "weekday_choices": StudentSchedule.Weekday.choices,
            "schedule_input_rows": schedule_input_rows,
            "schedule_form_error": schedule_form_error,
            "schedules": schedules,
            "upcoming_slots": upcoming_slots,
            "today": today,
        },
    )


@role_required(Profile.Role.TEACHER)
def slot_report_fill(request, slot_id: int):
    slot = get_object_or_404(
        LessonSlot.objects.select_related("student", "course", "teacher", "lesson"),
        id=slot_id,
        teacher=request.user,
    )
    if slot.scheduled_date > timezone.localdate() and slot.status == LessonSlot.Status.PLANNED:
        messages.error(request, "Отчёт можно заполнить в день занятия.")
        return redirect("/calendar/")

    existing_report = (
        LessonReport.objects.filter(lesson=slot.lesson, student=slot.student).order_by("-created_at").first()
        if slot.lesson_id
        else None
    )
    initial_plays = _active_plays_for_slot(slot) or [{"name": "", "completed": False, "comment": ""}]
    play_errors = []

    if request.method == "POST":
        form = SlotReportForm(request.POST, request.FILES)
        posted_plays = _collect_play_entries(request)
        if posted_plays:
            initial_plays = posted_plays

        if form.is_valid():
            attendance_status = form.cleaned_data["attendance_status"]
            result_note = (form.cleaned_data.get("result_note") or "").strip()
            report_comment = (form.cleaned_data.get("report_comment") or "").strip()
            media_url = (form.cleaned_data.get("media_url") or "").strip()
            attachment = form.cleaned_data.get("attachment")
            plays = _collect_play_entries(request)

            requires_plays = attendance_status in (
                LessonSlot.AttendanceStatus.PRESENT,
                LessonSlot.AttendanceStatus.LATE,
            )
            if requires_plays and not plays:
                play_errors = ["Добавьте хотя бы одну композицию."]

            if not play_errors:
                if requires_plays:
                    lesson = slot.lesson
                    if not lesson:
                        lesson = Lesson.objects.create(
                            course=slot.course,
                            date=slot.scheduled_date,
                            topic=_build_topic_from_plays(plays),
                            created_by=request.user,
                            attachment=attachment,
                        )
                    else:
                        lesson.topic = _build_topic_from_plays(plays)
                        lesson.course = slot.course
                        lesson.date = slot.scheduled_date
                        if attachment:
                            lesson.attachment = attachment
                        fields = ["topic", "course", "date"]
                        if attachment:
                            fields.append("attachment")
                        lesson.save(update_fields=fields)

                    lesson_entry, _ = LessonStudent.objects.get_or_create(
                        lesson=lesson,
                        student=slot.student,
                        defaults={"attended": True, "result": _serialize_play_entries(plays)},
                    )
                    lesson_entry.attended = _slot_attended_bool(attendance_status)
                    lesson_entry.result = _serialize_play_entries(plays)
                    lesson_entry.save(update_fields=["attended", "result"])

                    report = LessonReport.objects.filter(lesson=lesson, student=slot.student).order_by("-created_at").first()
                    if report:
                        report.text = report_comment
                        report.media_url = media_url
                        report.save(update_fields=["text", "media_url"])
                    elif media_url or report_comment:
                        LessonReport.objects.create(
                            lesson=lesson,
                            student=slot.student,
                            text=report_comment,
                            media_url=media_url,
                        )

                    slot.lesson = lesson
                    slot.status = LessonSlot.Status.DONE
                else:
                    slot.status = LessonSlot.Status.MISSED

                slot.attendance_status = attendance_status
                slot.result_note = result_note
                slot.report_comment = report_comment
                slot.filled_at = timezone.now()
                slot.save(
                    update_fields=[
                        "lesson",
                        "status",
                        "attendance_status",
                        "result_note",
                        "report_comment",
                        "filled_at",
                        "updated_at",
                    ]
                )

                messages.success(request, "Отчёт по слоту сохранён.")
                return redirect("/calendar/")
    else:
        form = SlotReportForm(
            initial={
                "attendance_status": slot.attendance_status,
                "result_note": slot.result_note,
                "report_comment": slot.report_comment or (existing_report.text if existing_report else ""),
                "media_url": existing_report.media_url if existing_report else "",
            }
        )

    return render(
        request,
        "lessons/slot_report_fill.html",
        {
            "slot": slot,
            "student": slot.student,
            "course": slot.course,
            "form": form,
            "initial_plays": initial_plays,
            "play_errors": play_errors,
            "today": timezone.localdate(),
        },
    )


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
    student_entries = (
        LessonStudent.objects.filter(lesson=lesson)
        .select_related("student")
        .order_by("student__first_name", "student__last_name", "student__username", "id")
    )
    play_blocks = []
    for entry in student_entries:
        plays = _parse_play_entries(entry.result)
        if not plays:
            continue
        play_blocks.append({"student": entry.student, "plays": plays})

    return render(
        request,
        "lessons/lesson_detail.html",
        {"lesson": lesson, "reports": reports, "play_blocks": play_blocks},
    )
