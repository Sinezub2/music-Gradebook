# apps/school/urls.py
from django.urls import path
from .views import (
    course_detail,
    course_list,
    teacher_class_list,
    teacher_group_detail,
    teacher_group_list,
    teacher_group_student_detail,
    teacher_student_workspace,
)

urlpatterns = [
    path("teacher/class/", teacher_class_list, name="teacher_class_list"),
    path("teacher/groups/", teacher_group_list, name="teacher_group_list"),
    path("teacher/groups/<int:group_id>/", teacher_group_detail, name="teacher_group_detail"),
    path(
        "teacher/groups/<int:group_id>/students/<int:student_id>/",
        teacher_group_student_detail,
        name="teacher_group_student_detail",
    ),
    path("teacher/students/<int:student_id>/", teacher_student_workspace, name="teacher_student_workspace"),
    path("courses/", course_list, name="course_list"),
    path("courses/<int:course_id>/", course_detail, name="course_detail"),
]
