from django.urls import path
from .views import assignment_list, mark_done

urlpatterns = [
    path("assignments/", assignment_list, name="assignment_list"),
    path("assignments/<int:assignment_id>/done/", mark_done, name="assignment_mark_done"),
]
