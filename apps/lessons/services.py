from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from .models import LessonSlot, StudentSchedule


SLOT_GENERATION_DAYS = 60


def generate_slots_for_schedule(
    schedule: StudentSchedule,
    *,
    start_date=None,
    days: int = SLOT_GENERATION_DAYS,
) -> int:
    if not schedule.active:
        return 0

    created_count = 0
    today = start_date or timezone.localdate()
    end_date = today + timedelta(days=days)

    for offset in range(days + 1):
        slot_date = today + timedelta(days=offset)
        if slot_date > end_date or slot_date.weekday() != schedule.weekday:
            continue
        _, created = LessonSlot.objects.get_or_create(
            teacher=schedule.teacher,
            student=schedule.student,
            scheduled_date=slot_date,
            start_time=schedule.start_time,
            defaults={
                "course": schedule.course,
                "schedule": schedule,
                "duration_minutes": schedule.duration_minutes,
            },
        )
        if created:
            created_count += 1
    return created_count


def generate_slots_for_teacher(teacher, *, days: int = SLOT_GENERATION_DAYS) -> int:
    schedules = StudentSchedule.objects.filter(teacher=teacher, active=True).select_related("student", "course")
    created_count = 0
    for schedule in schedules:
        created_count += generate_slots_for_schedule(schedule, days=days)
    return created_count
