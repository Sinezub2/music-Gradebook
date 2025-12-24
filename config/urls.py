# config/urls.py
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect


def root_redirect(_request):
    return redirect("/dashboard")


urlpatterns = [
    path("", root_redirect),
    path("admin/", admin.site.urls),
    path("", include("apps.accounts.urls")),
    path("", include("apps.school.urls")),
    path("", include("apps.gradebook.urls")),
]
