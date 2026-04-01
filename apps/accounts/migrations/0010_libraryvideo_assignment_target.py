from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("homework", "0004_assignment_attachment"),
        ("accounts", "0009_activationcode_cycle_profile_class_curator_phone_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="libraryvideo",
            name="assignment_target",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="submission_video",
                to="homework.assignmenttarget",
            ),
        ),
    ]
