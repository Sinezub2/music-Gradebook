# apps/accounts/decorators.py
from functools import wraps
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden


def role_required(*roles: str):
    """
    Usage: @role_required('TEACHER') or @role_required('PARENT','STUDENT')
    """
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            profile = getattr(request.user, "profile", None)
            if not profile:
                return HttpResponseForbidden("Профиль не найден.")
            if profile.role not in roles:
                return HttpResponseForbidden("Доступ запрещён.")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
