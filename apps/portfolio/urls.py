from django.urls import path
from .views import student_profile, my_portfolio

urlpatterns = [
    path("portfolio/", my_portfolio, name="my_portfolio"),
    path("students/<int:student_id>/profile/", student_profile, name="student_profile"),
]
