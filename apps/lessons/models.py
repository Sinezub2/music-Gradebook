from django.conf import settings
from django.db import models

from apps.school.models import Course


class Lesson(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lessons")
    date = models.DateField()
    topic = models.CharField(max_length=200)
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
