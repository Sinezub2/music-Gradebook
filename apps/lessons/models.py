from django.conf import settings
from django.db import models

from apps.accounts.models import Profile
from apps.school.models import Course


class Lesson(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lessons")
    date = models.DateField()
    topic = models.CharField(max_length=200)
    cycle = models.CharField(max_length=16, choices=Profile.Cycle.choices, default=Profile.Cycle.GENERAL)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_lessons")

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


class AttendanceRecord(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    date = models.DateField()
    attended = models.BooleanField(default=False)

    class Meta:
        ordering = ("-date",)
        unique_together = ("student", "date")

    def __str__(self) -> str:
        return f"{self.student_id} {self.date} ({'✓' if self.attended else '—'})"
