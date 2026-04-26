from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_libraryvideo_assignment_target"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="teacher_mode",
            field=models.CharField(
                choices=[
                    ("INDIVIDUAL", "Индивидуальный"),
                    ("GROUP", "Групповой"),
                    ("BOTH", "Оба режима"),
                ],
                default="INDIVIDUAL",
                max_length=16,
            ),
        ),
    ]
