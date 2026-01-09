from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.views.generic import TemplateView


def root_redirect(_request):
    return redirect("/dashboard")


urlpatterns = [
    path("", root_redirect),
    path("admin/", admin.site.urls),

    # existing apps
    path("", include("apps.accounts.urls")),
    path("", include("apps.school.urls")),
    path("", include("apps.gradebook.urls")),

    # new apps
    path("", include("apps.schedule.urls")),
    path("", include("apps.homework.urls")),

    # messages placeholder
    path("messages/", TemplateView.as_view(template_name="messages/placeholder.html"), name="messages_placeholder"),
]
