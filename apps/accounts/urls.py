# apps/accounts/urls.py
from django.urls import path
from .views import (
    communication_view,
    dashboard,
    library_view,
    login_view,
    logout_view,
    profile_change_password,
    profile_change_username,
    profile_view,
    register_by_invite,
    school_life_view,
    teacher_student_invite_create,
)

urlpatterns = [
    path("login", login_view, name="login"),
    path("logout", logout_view, name="logout"),
    path("dashboard", dashboard, name="dashboard"),
    path("communication/", communication_view, name="communication"),
    path("school-life/", school_life_view, name="school_life"),
    path("library/", library_view, name="library"),
    path("teacher/students/invite/", teacher_student_invite_create, name="teacher_student_invite_create"),
    path("register/invite/<str:token>/", register_by_invite, name="register_by_invite"),
    path("profile/", profile_view, name="profile"),
    path("profile/change-username/", profile_change_username, name="profile_change_username"),
    path("profile/change-password/", profile_change_password, name="profile_change_password"),
]
