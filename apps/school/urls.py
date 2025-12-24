# apps/school/urls.py
from django.urls import path
from .views import course_list, course_detail

urlpatterns = [
    path("courses/", course_list, name="course_list"),
    path("courses/<int:course_id>/", course_detail, name="course_detail"),
]
