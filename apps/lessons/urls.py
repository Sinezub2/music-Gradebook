from django.urls import path
from .views import lesson_list, lesson_create, lesson_detail

urlpatterns = [
    path("lessons/", lesson_list, name="lesson_list"),
    path("lessons/create/", lesson_create, name="lesson_create"),
    path("lessons/<int:lesson_id>/", lesson_detail, name="lesson_detail"),
]
