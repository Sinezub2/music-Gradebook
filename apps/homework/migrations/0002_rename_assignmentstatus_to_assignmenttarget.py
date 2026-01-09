from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("homework", "0001_initial"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="AssignmentStatus",
            new_name="AssignmentTarget",
        ),
        migrations.RenameField(
            model_name="assignmenttarget",
            old_name="comment",
            new_name="student_comment",
        ),
    ]
