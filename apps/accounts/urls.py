# apps/accounts/urls.py
from django.urls import path
from .views import (
    dashboard,
    login_view,
    logout_view,
    profile_change_password,
    profile_change_username,
    profile_view,
    register_by_invite,
    teacher_student_invite_create,
)

urlpatterns = [
    path("login", login_view, name="login"),
    path("logout", logout_view, name="logout"),
    path("dashboard", dashboard, name="dashboard"),
    path("teacher/students/invite/", teacher_student_invite_create, name="teacher_student_invite_create"),
    path("register/invite/<str:token>/", register_by_invite, name="register_by_invite"),
    path("profile/", profile_view, name="profile"),
    path("profile/change-username/", profile_change_username, name="profile_change_username"),
    path("profile/change-password/", profile_change_password, name="profile_change_password"),
]
