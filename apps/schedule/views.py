from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.models import Profile
from apps.lessons.models import LessonSlot
from apps.lessons.services import generate_slots_for_teacher
from apps.school.models import Course, Enrollment, ParentChild
from .models import Event


WEEKDAY_LABELS = [
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье",
]


def _events_for_role(request, qs):
    role = request.user.profile.role
    registration_events = qs.none()
    children = []

    if role == Profile.Role.ADMIN:
        return qs, registration_events, children, "admin"

    if role == Profile.Role.TEACHER:
        teacher_courses = Course.objects.filter(teacher=request.user)
        events = qs.filter(Q(course__in=teacher_courses) | Q(created_by=request.user)).distinct()
        return events, registration_events, children, "teacher"

    if role == Profile.Role.STUDENT:
        enrolled_courses = Course.objects.filter(enrollments__student=request.user)
        events = qs.filter(participants=request.user).distinct()
        registration_events = (
            qs.filter(Q(course__in=enrolled_courses) | Q(course__isnull=True))
            .exclude(participants=request.user)
            .distinct()
        )
        return events, registration_events, children, "student"

    if role == Profile.Role.PARENT:
        children = list(ParentChild.objects.filter(parent=request.user).select_related("child"))
        child_ids = [child.child_id for child in children]
        enrolled_courses = Course.objects.filter(enrollments__student_id__in=child_ids).distinct()
        events = qs.filter(Q(course__in=enrolled_courses) | Q(participants__id__in=child_ids)).distinct()
        return events, registration_events, children, "parent"

    return qs.none(), registration_events, children, "unknown"


@login_required
def calendar_list(request):
    try:
        week_offset = int(request.GET.get("week", "0"))
    except ValueError:
        week_offset = 0

    profile = request.user.profile
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    week_end = week_start + timedelta(days=7)

    mode = "unknown"
    children = []
    registration_events = Event.objects.none()
    events_by_day = {}
    slots_by_day = {}

    if profile.role == Profile.Role.ADMIN:
        mode = "admin"
        base_qs = Event.objects.all().select_related("course", "created_by").prefetch_related("participants")
        events, registration_events, children, _ = _events_for_role(request, base_qs)
        week_events = (
            events.filter(start_datetime__date__gte=week_start, start_datetime__date__lt=week_end)
            .select_related("course")
            .order_by("start_datetime")
        )
        for event in week_events:
            local_start = timezone.localtime(event.start_datetime)
            day_key = local_start.date()
            events_by_day.setdefault(day_key, []).append(
                {
                    "id": event.id,
                    "time_label": local_start.strftime("%H:%M"),
                    "title": event.title,
                    "subtitle": event.course.name if event.course else event.get_event_type_display(),
                    "type_label": event.get_event_type_display(),
                    "description": event.description,
                    "external_url": event.external_url,
                    "can_register": False,
                }
            )
    else:
        if profile.role == Profile.Role.TEACHER:
            mode = "teacher"
            generate_slots_for_teacher(request.user)
            slot_qs = LessonSlot.objects.filter(
                teacher=request.user,
                scheduled_date__gte=week_start,
                scheduled_date__lt=week_end,
            ).select_related("student", "course")
        elif profile.role == Profile.Role.STUDENT:
            mode = "student"
            slot_qs = LessonSlot.objects.filter(
                student=request.user,
                scheduled_date__gte=week_start,
                scheduled_date__lt=week_end,
            ).select_related("teacher", "course")
        elif profile.role == Profile.Role.PARENT:
            mode = "parent"
            children = list(ParentChild.objects.filter(parent=request.user).select_related("child"))
            child_ids = [row.child_id for row in children]
            slot_qs = LessonSlot.objects.filter(
                student_id__in=child_ids,
                scheduled_date__gte=week_start,
                scheduled_date__lt=week_end,
            ).select_related("student", "teacher", "course")
        else:
            slot_qs = LessonSlot.objects.none()

        for slot in slot_qs.order_by("scheduled_date", "start_time", "id"):
            if mode == "teacher":
                title = (slot.student.get_full_name() or "").strip() or slot.student.username
                subtitle = slot.course.name
            elif mode == "student":
                teacher_name = (slot.teacher.get_full_name() or "").strip() or slot.teacher.username
                title = slot.course.name
                subtitle = f"Педагог: {teacher_name}"
            else:
                student_name = (slot.student.get_full_name() or "").strip() or slot.student.username
                title = student_name
                subtitle = slot.course.name

            slots_by_day.setdefault(slot.scheduled_date, []).append(
                {
                    "id": slot.id,
                    "time_label": slot.start_time.strftime("%H:%M"),
                    "title": title,
                    "subtitle": subtitle,
                    "status_label": slot.get_status_display(),
                    "status": slot.status,
                    "attendance_label": slot.get_attendance_status_display() if slot.status != LessonSlot.Status.PLANNED else "",
                    "report_url": f"/slots/{slot.id}/report/",
                    "can_fill_report": mode == "teacher" and (slot.scheduled_date <= today or slot.status != LessonSlot.Status.PLANNED),
                }
            )

    week_columns = []
    for day_index in range(7):
        day = week_start + timedelta(days=day_index)
        week_columns.append(
            {
                "date": day,
                "weekday_label": WEEKDAY_LABELS[day_index],
                "date_label": day.strftime("%d %B"),
                "events": events_by_day.get(day, []),
                "slots": slots_by_day.get(day, []),
                "is_today": day == today,
            }
        )

    available_registration = []

    return render(
        request,
        "schedule/calendar_list.html",
        {
            "mode": mode,
            "children": children,
            "week_offset": week_offset,
            "week_start": week_start,
            "week_end": week_end - timedelta(days=1),
            "week_columns": week_columns,
            "available_registration": available_registration,
        },
    )


@login_required
def register_event(request, event_id: int):
    if request.user.profile.role != Profile.Role.STUDENT:
        return HttpResponseForbidden("Только ученики могут регистрироваться.")

    if request.method != "POST":
        return HttpResponseForbidden("Требуется POST.")

    event = get_object_or_404(Event.objects.select_related("course"), id=event_id)
    if event.course_id:
        if not Enrollment.objects.filter(course=event.course, student=request.user).exists():
            return HttpResponseForbidden("Нет доступа к этому событию.")

    event.participants.add(request.user)
    messages.success(request, "Вы зарегистрированы на событие.")
    return redirect("/calendar/")
