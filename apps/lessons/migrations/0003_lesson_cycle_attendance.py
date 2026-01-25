from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_profile_school_grade"),
        ("lessons", "0002_lessonstudent"),
    ]

    operations = [
        migrations.AddField(
            model_name="lesson",
            name="cycle",
            field=models.CharField(
                choices=[("GENERAL", "Общий"), ("ACCELERATED", "Ускоренный"), ("EXTRA", "Дополнительный")],
                default="GENERAL",
                max_length=16,
            ),
        ),
        migrations.CreateModel(
            name="AttendanceRecord",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("attended", models.BooleanField(default=False)),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attendance_records",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-date",),
                "unique_together": {("student", "date")},
            },
        ),
    ]
