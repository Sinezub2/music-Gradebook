# apps/gradebook/urls.py
from django.urls import path
from .views import teacher_course_grades, student_course_grades

urlpatterns = [
    path("teacher/courses/<int:course_id>/grades/", teacher_course_grades, name="teacher_course_grades"),
    path("courses/<int:course_id>/grades/", student_course_grades, name="student_course_grades"),
]
