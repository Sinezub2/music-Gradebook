from django.conf import settings
from django.shortcuts import render
from django.utils.http import url_has_allowed_host_and_scheme


def csrf_failure(request, reason=""):
    fallback_url = "/dashboard" if request.user.is_authenticated else "/login"
    raw_return_url = (request.META.get("HTTP_REFERER") or "").strip()
    if raw_return_url and url_has_allowed_host_and_scheme(
        raw_return_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return_url = raw_return_url
    else:
        return_url = fallback_url

    return render(
        request,
        "errors/csrf_failure.html",
        {
            "return_url": return_url,
            "reason": reason if settings.DEBUG else "",
        },
        status=403,
    )
