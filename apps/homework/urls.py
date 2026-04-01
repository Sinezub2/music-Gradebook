from django.urls import path
from .views import (
    assignment_bulk_delete,
    assignment_create,
    assignment_create_for_student,
    assignment_list,
    mark_done,
    submit_assignment,
)

urlpatterns = [
    path("assignments/", assignment_list, name="assignment_list"),
    path("assignments/bulk-delete/", assignment_bulk_delete, name="assignment_bulk_delete"),
    path("assignments/create/", assignment_create, name="assignment_create"),
    path(
        "teacher/students/<int:student_id>/assignments/create/",
        assignment_create_for_student,
        name="teacher_student_assignment_create",
    ),
    path("assignments/targets/<int:target_id>/mark_done/", mark_done, name="assignment_mark_done"),
    path("assignments/targets/<int:target_id>/submit/", submit_assignment, name="assignment_submit"),
]
