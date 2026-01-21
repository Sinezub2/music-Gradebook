# apps/school/models.py
from django.conf import settings
from django.db import models


class CourseType(models.Model):
    name = models.CharField(max_length=120, unique=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Course(models.Model):
    name = models.CharField(max_length=200)
    course_type = models.ForeignKey(CourseType, on_delete=models.PROTECT, related_name="courses")
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
