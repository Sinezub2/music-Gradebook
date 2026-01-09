from django.conf import settings
from django.db import models


class Achievement(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="achievements")
    title = models.CharField(max_length=200)
    date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("-date", "-id")

    def __str__(self) -> str:
        return f"{self.student.username}: {self.title}"


class MediaLink(models.Model):
    class MediaType(models.TextChoices):
        PHOTO = "PHOTO", "Фото"
        VIDEO = "VIDEO", "Видео"
        AUDIO = "AUDIO", "Аудио"

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="media_links")
    title = models.CharField(max_length=200)
    url = models.URLField()
    media_type = models.CharField(max_length=16, choices=MediaType.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return f"{self.student.username}: {self.title}"
