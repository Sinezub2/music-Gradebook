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
        student_name = (self.student.get_full_name() or "").strip() or "Без имени"
        return f"{student_name} -> {self.course.name}"


class CourseInternalGroup(models.Model):
    class GroupType(models.TextChoices):
        SPLIT = "SPLIT", "Подгруппа"
        REMEDIAL = "REMEDIAL", "Нужна поддержка"
        ADVANCED = "ADVANCED", "Продвинутые"
        CUSTOM = "CUSTOM", "Своя группа"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="internal_groups")
    name = models.CharField(max_length=120)
    group_type = models.CharField(max_length=16, choices=GroupType.choices, default=GroupType.CUSTOM)
    students = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="course_internal_groups")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")
        unique_together = ("course", "name")

    def __str__(self) -> str:
        return f"{self.course.name} / {self.name}"


class ParentChild(models.Model):
    parent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="children_links")
    child = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="parent_links")

    class Meta:
        unique_together = ("parent", "child")

    def __str__(self) -> str:
        parent_name = (self.parent.get_full_name() or "").strip() or "Без имени"
        child_name = (self.child.get_full_name() or "").strip() or "Без имени"
        return f"{parent_name} -> {child_name}"
