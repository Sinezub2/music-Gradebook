from django.urls import path
from .views import calendar_list, register_event

urlpatterns = [
    path("calendar/", calendar_list, name="calendar_list"),
    path("calendar/register/<int:event_id>/", register_event, name="calendar_register_event"),
]
