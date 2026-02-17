# apps/school/urls.py
from django.urls import path
from .views import course_list, course_detail, teacher_class_list, teacher_student_workspace

urlpatterns = [
    path("teacher/class/", teacher_class_list, name="teacher_class_list"),
    path("teacher/students/<int:student_id>/", teacher_student_workspace, name="teacher_student_workspace"),
    path("courses/", course_list, name="course_list"),
    path("courses/<int:course_id>/", course_detail, name="course_detail"),
]
