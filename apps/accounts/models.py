# apps/accounts/models.py
from django.conf import settings
from django.db import models


class Profile(models.Model):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Администратор"
        TEACHER = "TEACHER", "Преподаватель"
        STUDENT = "STUDENT", "Ученик"
        PARENT = "PARENT", "Родитель"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=16, choices=Role.choices)

    def __str__(self) -> str:
        return f"{self.user.username} ({self.role})"
