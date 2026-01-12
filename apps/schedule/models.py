from django.conf import settings
from django.db import models

from apps.school.models import Course


class Event(models.Model):
    class EventType(models.TextChoices):
        LESSON = "LESSON", "Урок"
        EXAM = "EXAM", "Экзамен"
        CONCERT = "CONCERT", "Концерт"

    title = models.CharField(max_length=200)
    event_type = models.CharField(max_length=16, choices=EventType.choices)
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    description = models.TextField(blank=True, default="")
    external_url = models.URLField(blank=True, default="")

    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True, related_name="events")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_events",
    )

    # "Student" in this project == User with Profile role STUDENT
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="schedule_events",
    )

    class Meta:
        ordering = ("start_datetime",)

    def __str__(self) -> str:
        return f"{self.title} ({self.get_event_type_display()})"
