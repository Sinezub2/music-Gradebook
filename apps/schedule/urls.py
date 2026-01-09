from django.urls import path
from .views import calendar_list

urlpatterns = [
    path("calendar/", calendar_list, name="calendar_list"),
]
