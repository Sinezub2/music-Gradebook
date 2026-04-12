# apps/accounts/urls.py
from django.urls import path
from .views import (
    communication_view,
    dashboard,
    library_view,
    login_view,
    logout_view,
    profile_add_course,
    profile_add_child,
    profile_change_student_details,
    profile_change_password,
    profile_change_username,
    profile_view,
    register_view,
    school_life_view,
    teacher_activation_code_create,
)

urlpatterns = [
    path("login", login_view, name="login"),
    path("logout", logout_view, name="logout"),
    path("register/", register_view, name="register"),
    path("dashboard", dashboard, name="dashboard"),
    path("communication/", communication_view, name="communication"),
    path("school-life/", school_life_view, name="school_life"),
    path("library/", library_view, name="library"),
    path("teacher/invite-code/create/", teacher_activation_code_create, name="teacher_activation_code_create"),
    path("profile/", profile_view, name="profile"),
    path("profile/add-course/", profile_add_course, name="profile_add_course"),
    path("profile/add-child/", profile_add_child, name="profile_add_child"),
    path("profile/student-details/", profile_change_student_details, name="profile_change_student_details"),
    path("profile/change-username/", profile_change_username, name="profile_change_username"),
    path("profile/change-password/", profile_change_password, name="profile_change_password"),
]
