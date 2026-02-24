from django.conf import settings
from django.db import models

from apps.school.models import Course


class Lesson(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lessons")
    date = models.DateField()
    topic = models.CharField(max_length=200)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_lessons")
    attachment = models.FileField(upload_to="lessons/", blank=True, null=True)

    class Meta:
        ordering = ("-date", "-id")

    def __str__(self) -> str:
        return f"{self.course.name} {self.date}: {self.topic}"


class LessonReport(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="reports")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="lesson_reports")

    text = models.TextField()
    media_url = models.URLField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"Report {self.lesson_id} ({self.student_id})"


class LessonStudent(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="student_entries")
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="lesson_entries",
    )
    attended = models.BooleanField(default=True)
    result = models.TextField(blank=True)

    class Meta:
        unique_together = ("lesson", "student")

    def __str__(self) -> str:
        return f"{self.lesson_id} -> {self.student_id}"


class StudentSchedule(models.Model):
    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Понедельник"
        TUESDAY = 1, "Вторник"
        WEDNESDAY = 2, "Среда"
        THURSDAY = 3, "Четверг"
        FRIDAY = 4, "Пятница"
        SATURDAY = 5, "Суббота"
        SUNDAY = 6, "Воскресенье"

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_schedules",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="lesson_schedules",
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="student_schedules",
    )
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    lesson_number = models.PositiveSmallIntegerField(null=True, blank=True)
    start_time = models.TimeField()
    duration_minutes = models.PositiveIntegerField(default=45)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("weekday", "start_time", "id")
        unique_together = ("teacher", "student", "weekday", "start_time")

    def __str__(self) -> str:
        return f"{self.student_id} {self.get_weekday_display()} {self.start_time:%H:%M}"


class LessonSlot(models.Model):
    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Запланирован"
        DONE = "DONE", "Проведен"
        MISSED = "MISSED", "Пропущен"

    class AttendanceStatus(models.TextChoices):
        PRESENT = "PRESENT", "Присутствовал"
        ABSENT = "ABSENT", "Отсутствовал"
        SICK = "SICK", "Болел"
        LATE = "LATE", "Опоздал"

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="lesson_slots",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_lesson_slots",
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="lesson_slots",
    )
    schedule = models.ForeignKey(
        StudentSchedule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="slots",
    )
    scheduled_date = models.DateField()
    start_time = models.TimeField()
    duration_minutes = models.PositiveIntegerField(default=45)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PLANNED)
    attendance_status = models.CharField(
        max_length=16,
        choices=AttendanceStatus.choices,
        default=AttendanceStatus.PRESENT,
    )
    result_note = models.CharField(max_length=120, blank=True, default="")
    report_comment = models.TextField(blank=True, default="")
    filled_at = models.DateTimeField(null=True, blank=True)
    lesson = models.OneToOneField(
        Lesson,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="slot",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("scheduled_date", "start_time", "id")
        unique_together = ("teacher", "student", "scheduled_date", "start_time")

    def __str__(self) -> str:
        return f"{self.student_id} {self.scheduled_date} {self.start_time:%H:%M}"
