from django.urls import path

from .views import goal_list

urlpatterns = [
    path("goals/", goal_list, name="goal_list"),
]
