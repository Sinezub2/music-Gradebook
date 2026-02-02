from django.urls import path

from .views import goal_create, goal_list

urlpatterns = [
    path("goals/", goal_list, name="goal_list"),
    path("goals/create/", goal_create, name="goal_create"),
]
