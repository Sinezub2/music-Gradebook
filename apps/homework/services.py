from django.db import transaction

from apps.gradebook.models import Assessment, Grade
from apps.school.models import Course, Enrollment
from .models import Assignment, AssignmentTarget


@transaction.atomic
def create_assignment_with_targets_and_gradebook(
    *,
    teacher,
    course: Course,
    title: str,
    description: str,
    due_date,
    attachment,
    student_ids: list[int],
) -> Assignment:
    """
    При создании Assignment:
    - создаём Assignment
    - создаём или находим связанный Assessment (OneToOne через source_assignment)
    - для каждого выбранного студента:
        - get_or_create AssignmentTarget(status=TODO)
        - get_or_create Grade(score=None)
    Идемпотентность обеспечивается get_or_create + unique constraints.
    """

    assignment = Assignment.objects.create(
        course=course,
        title=title,
        description=description or "",
        due_date=due_date,
        attachment=attachment,
        created_by=teacher,
    )

    # One Assessment per Assignment
    assessment, _ = Assessment.objects.get_or_create(
        source_assignment=assignment,
        defaults={
            "course": course,
            "title": assignment.title,
            "assessment_type": Assessment.AssessmentType.HOMEWORK,
            "max_score": 100,
            "weight": 1,
        },
    )

    # If assignment title changed (not typical on create), keep assessment aligned
    # (optional safety)
    if assessment.title != assignment.title:
        assessment.title = assignment.title
        assessment.save()

    # Ensure student_ids belong to enrollments of this course
    enrolled_ids = set(
        Enrollment.objects.filter(course=course, student_id__in=student_ids).values_list("student_id", flat=True)
    )
    safe_student_ids = [sid for sid in student_ids if sid in enrolled_ids]

    for sid in safe_student_ids:
        target, _ = AssignmentTarget.objects.get_or_create(
            assignment=assignment,
            student_id=sid,
            defaults={"status": AssignmentTarget.Status.TODO},
        )
        # ensure status is at least TODO (if existed)
        if not target.status:
            target.status = AssignmentTarget.Status.TODO
            target.save()

        Grade.objects.get_or_create(
            assessment=assessment,
            student_id=sid,
            defaults={"score": None, "comment": ""},
        )

    return assignment
