# apps/gradebook/urls.py
from django.urls import path
from .views import teacher_course_grades, student_course_grades, teacher_course_grades_bulk_clear

urlpatterns = [
    path("teacher/courses/<int:course_id>/grades/", teacher_course_grades, name="teacher_course_grades"),
    path(
        "teacher/courses/<int:course_id>/grades/bulk-clear/",
        teacher_course_grades_bulk_clear,
        name="teacher_course_grades_bulk_clear",
    ),
    path("courses/<int:course_id>/grades/", student_course_grades, name="student_course_grades"),
]
