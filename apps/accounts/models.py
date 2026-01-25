# apps/accounts/models.py
from django.conf import settings
from django.db import models


class Profile(models.Model):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Администратор"
        TEACHER = "TEACHER", "Преподаватель"
        STUDENT = "STUDENT", "Ученик"
        PARENT = "PARENT", "Родитель"

    class Cycle(models.TextChoices):
        GENERAL = "GENERAL", "Общий"
        ACCELERATED = "ACCELERATED", "Ускоренный"
        EXTRA = "EXTRA", "Дополнительный"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=16, choices=Role.choices)
    cycle = models.CharField(max_length=16, choices=Cycle.choices, default=Cycle.GENERAL)
    school_grade = models.CharField(max_length=20, blank=True, default="")

    def __str__(self) -> str:
        return f"{self.user.username} ({self.role})"
