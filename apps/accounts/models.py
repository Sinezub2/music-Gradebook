# apps/accounts/models.py
from datetime import timedelta
import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.school.models import Course


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
        full_name = (self.user.get_full_name() or "").strip() or "Без имени"
        return f"{full_name} ({self.role})"


def _default_invitation_expiry():
    return timezone.now() + timedelta(days=14)


class StudentInvitation(models.Model):
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student_invitations")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="student_invitations")
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    school_grade = models.CharField(max_length=20, blank=True, default="")
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=_default_invitation_expiry)
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    @staticmethod
    def generate_raw_token() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name} -> {self.course.name}"
