from django.urls import path
from .views import assignment_list, assignment_create, mark_done, assignment_bulk_delete

urlpatterns = [
    path("assignments/", assignment_list, name="assignment_list"),
    path("assignments/bulk-delete/", assignment_bulk_delete, name="assignment_bulk_delete"),
    path("assignments/create/", assignment_create, name="assignment_create"),
    path("assignments/targets/<int:target_id>/mark_done/", mark_done, name="assignment_mark_done"),
]
