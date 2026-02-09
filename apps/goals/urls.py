from django.urls import path

from .views import goal_create, goal_list, goal_bulk_delete

urlpatterns = [
    path("goals/", goal_list, name="goal_list"),
    path("goals/bulk-delete/", goal_bulk_delete, name="goal_bulk_delete"),
    path("goals/create/", goal_create, name="goal_create"),
]
