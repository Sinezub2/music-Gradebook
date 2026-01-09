from django.urls import path
from .views import inbox, thread_detail, start_for_student

urlpatterns = [
    path("messages/", inbox, name="messages_inbox"),
    path("messages/<int:thread_id>/", thread_detail, name="messages_thread"),
    path("messages/start/<int:student_id>/", start_for_student, name="messages_start"),
]
