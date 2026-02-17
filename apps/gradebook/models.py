from django.conf import settings
from django.db import models
from apps.school.models import Course


class Assessment(models.Model):
    class AssessmentType(models.TextChoices):
        HOMEWORK = "HOMEWORK", "Домашнее задание"
        PERFORMANCE = "PERFORMANCE", "Выступление"
        JURY = "JURY", "Жюри"
        THEORY_TEST = "THEORY_TEST", "Тест по теории"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="assessments")
    title = models.CharField(max_length=200)
    assessment_type = models.CharField(max_length=32, choices=AssessmentType.choices)
    max_score = models.DecimalField(max_digits=6, decimal_places=2, default=100)
    weight = models.DecimalField(max_digits=6, decimal_places=2, default=1)

    # NEW: связь с homework.Assignment (один Assessment на одно Assignment)
    source_assignment = models.OneToOneField(
        "homework.Assignment",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assessment",
    )

    class Meta:
        unique_together = ("course", "title")
        ordering = ("id",)

    def __str__(self) -> str:
        return f"{self.course.name}: {self.title}"


class Grade(models.Model):
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="grades")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="grades")
    score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    comment = models.TextField(blank=True, default="")

    class Meta:
        unique_together = ("assessment", "student")

    def __str__(self) -> str:
        student_name = (self.student.get_full_name() or "").strip() or "Без имени"
        return f"{student_name} - {self.assessment.title}: {self.score}"
