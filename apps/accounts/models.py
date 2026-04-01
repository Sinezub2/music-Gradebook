# apps/accounts/models.py
from datetime import timedelta
import hashlib
import secrets

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone

from apps.school.models import Course

LIBRARY_VIDEO_EXTENSIONS = ("mp4", "mov", "webm", "m4v")


class Profile(models.Model):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Администратор"
        TEACHER = "TEACHER", "Преподаватель"
        STUDENT = "STUDENT", "Ученик"
        PARENT = "PARENT", "Родитель"

    class Cycle(models.TextChoices):
        GENERAL = "GENERAL", "Общий"
        BASIC = "BASIC", "Базовый"
        ACCELERATED = "ACCELERATED", "Специальный"
        EXTRA = "EXTRA", "Дополнительный"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=16, choices=Role.choices)
    cycle = models.CharField(max_length=16, choices=Cycle.choices, default=Cycle.GENERAL)
    school_grade = models.CharField(max_length=20, blank=True, default="")
    class_curator_phone = models.CharField(max_length=50, blank=True, default="")

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


class ActivationCode(models.Model):
    class TargetRole(models.TextChoices):
        STUDENT = Profile.Role.STUDENT, "Ученик"
        PARENT = Profile.Role.PARENT, "Родитель"

    code = models.CharField(max_length=32, unique=True)
    created_by_teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_activation_codes",
    )
    target_role = models.CharField(max_length=16, choices=TargetRole.choices)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="activation_codes")
    cycle = models.CharField(max_length=16, choices=Profile.Cycle.choices, default=Profile.Cycle.GENERAL)
    target_student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="parent_activation_codes",
        null=True,
        blank=True,
    )
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)
    used_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="used_activation_codes",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ("-created_at",)

    @classmethod
    def generate_code(cls) -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        while True:
            candidate = "MUSIC-" + "".join(secrets.choice(alphabet) for _ in range(6))
            if not cls.objects.filter(code=candidate).exists():
                return candidate

    def __str__(self) -> str:
        return f"{self.code} -> {self.course.name}"


class LibraryVideo(models.Model):
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="uploaded_library_videos",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="library_videos",
    )
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="library_videos")
    assignment_target = models.OneToOneField(
        "homework.AssignmentTarget",
        on_delete=models.SET_NULL,
        related_name="submission_video",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=200, blank=True, default="")
    video = models.FileField(
        upload_to="library/videos/%Y/%m/",
        validators=[FileExtensionValidator(allowed_extensions=LIBRARY_VIDEO_EXTENSIONS)],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        title = self.title.strip() or self.video.name.rsplit("/", 1)[-1]
        return f"{title} -> {self.student_id}"
