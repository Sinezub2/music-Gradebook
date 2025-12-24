# apps/school/models.py
from django.conf import settings
from django.db import models


class Course(models.Model):
    class CourseType(models.TextChoices):
        INSTRUMENT = "INSTRUMENT", "Инструмент"
        ENSEMBLE = "ENSEMBLE", "Ансамбль"
        THEORY = "THEORY", "Теория"

    name = models.CharField(max_length=200)
    course_type = models.CharField(max_length=32, choices=CourseType.choices)
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teaching_courses",
    )

    def __str__(self) -> str:
        return self.name


class Enrollment(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enrollments")

    class Meta:
        unique_together = ("course", "student")

    def __str__(self) -> str:
        return f"{self.student.username} -> {self.course.name}"


class ParentChild(models.Model):
    parent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="children_links")
    child = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="parent_links")

    class Meta:
        unique_together = ("parent", "child")

    def __str__(self) -> str:
        return f"{self.parent.username} -> {self.child.username}"
