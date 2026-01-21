from django.conf import settings
from django.db import models


class Goal(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="goals",
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="goals_created",
        null=True,
        blank=True,
    )
    month = models.DateField()
    title = models.CharField(max_length=255)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["month", "student__username"]

    def __str__(self) -> str:
        return f"{self.student.username}: {self.title}"
