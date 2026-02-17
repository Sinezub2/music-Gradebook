from django.urls import path
from .views import (
    lesson_list,
    lesson_create,
    lesson_create_for_student,
    lesson_detail,
    attendance_journal,
    lesson_bulk_delete,
)

urlpatterns = [
    path("lessons/", lesson_list, name="lesson_list"),
    path("lessons/bulk-delete/", lesson_bulk_delete, name="lesson_bulk_delete"),
    path("lessons/create/", lesson_create, name="lesson_create"),
    path(
        "teacher/students/<int:student_id>/lessons/create/",
        lesson_create_for_student,
        name="teacher_student_lesson_create",
    ),
    path("lessons/<int:lesson_id>/", lesson_detail, name="lesson_detail"),
    path("attendance/", attendance_journal, name="attendance_journal"),
]
