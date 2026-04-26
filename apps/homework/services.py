from django.db import transaction

from apps.gradebook.models import Assessment, Grade
from apps.school.models import Course, Enrollment
from .models import Assignment, AssignmentTarget


def build_unique_assessment_title(*, course: Course, base_title: str, due_date, exclude_assessment_id=None) -> str:
    normalized_title = (base_title or "").strip() or "Домашнее задание"
    qs = Assessment.objects.filter(course=course)
    if exclude_assessment_id:
        qs = qs.exclude(id=exclude_assessment_id)

    if not qs.filter(title=normalized_title).exists():
        return normalized_title

    dated_title = f"{normalized_title} ({due_date:%d.%m.%Y})"
    if not qs.filter(title=dated_title).exists():
        return dated_title

    suffix = 2
    while True:
        candidate = f"{dated_title} #{suffix}"
        if not qs.filter(title=candidate).exists():
            return candidate
        suffix += 1


@transaction.atomic
def create_assignment_with_targets_and_gradebook(
    *,
    teacher,
    course: Course,
    title: str,
    task_text: str,
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
        description=task_text or "",
        due_date=due_date,
        attachment=attachment,
        created_by=teacher,
    )

    assessment_title = build_unique_assessment_title(course=course, base_title=assignment.title, due_date=due_date)

    # One Assessment per Assignment
    assessment, _ = Assessment.objects.get_or_create(
        source_assignment=assignment,
        defaults={
            "course": course,
            "title": assessment_title,
            "assessment_type": Assessment.AssessmentType.HOMEWORK,
            "max_score": 100,
            "weight": 1,
        },
    )

    # Keep shared assessment metadata aligned without breaking the per-course title uniqueness rule.
    fields_to_update = []
    if assessment.course_id != course.id:
        assessment.course = course
        fields_to_update.append("course")
    if assessment.assessment_type != Assessment.AssessmentType.HOMEWORK:
        assessment.assessment_type = Assessment.AssessmentType.HOMEWORK
        fields_to_update.append("assessment_type")
    if assessment.max_score != 100:
        assessment.max_score = 100
        fields_to_update.append("max_score")
    if assessment.weight != 1:
        assessment.weight = 1
        fields_to_update.append("weight")
    if not assessment.title:
        assessment.title = assessment_title
        fields_to_update.append("title")
    if fields_to_update:
        assessment.save(update_fields=fields_to_update)

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
