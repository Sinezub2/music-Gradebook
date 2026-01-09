from django.conf import settings
from django.db import models

from apps.school.models import Course


class Assignment(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="assignments")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    due_date = models.DateField()

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_assignments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("due_date", "id")

    def __str__(self) -> str:
        return f"{self.course.name}: {self.title}"


class AssignmentTarget(models.Model):
    """
    Назначение задания конкретному ученику + его статус.
    (assignment, student) уникально.
    """

    class Status(models.TextChoices):
        TODO = "TODO", "TODO"
        DONE = "DONE", "DONE"
        # Можно добавить SUBMITTED позже, но сейчас оставляем минимально.
        # SUBMITTED = "SUBMITTED", "SUBMITTED"

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="targets")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assignment_targets")

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.TODO)

    student_comment = models.TextField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("assignment", "student")

    def __str__(self) -> str:
        return f"{self.student.username} - {self.assignment.title}: {self.status}"
