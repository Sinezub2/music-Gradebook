import re
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib import admin
from django.http import Http404
from django.urls import path, include, re_path
from django.shortcuts import redirect
from django.views.static import serve as serve_static_file


def root_redirect(_request):
    return redirect("/dashboard")


def serve_media(request, path):
    if not settings.DEBUG and not settings.SERVE_MEDIA:
        raise Http404()
    return serve_static_file(request, path, document_root=settings.MEDIA_ROOT, show_indexes=False)


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
    

    path("", include("apps.lessons.urls")),
    path("", include("apps.portfolio.urls")),
    path("", include("apps.goals.urls")),




]

if settings.MEDIA_URL and not urlsplit(settings.MEDIA_URL).netloc:
    urlpatterns += [
        path(
            f"{settings.MEDIA_URL.lstrip('/')}" if settings.MEDIA_URL.endswith("/") else settings.MEDIA_URL.lstrip("/"),
            root_redirect,
        )
    ]
    urlpatterns += [
        re_path(
            r"^%s(?P<path>.*)$" % re.escape(settings.MEDIA_URL.lstrip("/")),
            serve_media,
        )
    ]
