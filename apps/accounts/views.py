# apps/accounts/views.py
from django.contrib import messages
from django.contrib.auth import login, logout
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

from .forms import LoginForm
from .models import Profile
from apps.school.models import ParentChild, Course, Enrollment


def login_view(request):
    if request.user.is_authenticated:
        return redirect("/dashboard")

    form = LoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return redirect("/dashboard")

    return render(request, "accounts/login.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("/login")


@login_required
def dashboard(request):
    profile = getattr(request.user, "profile", None)
    if not profile:
        messages.error(request, "Профиль не найден. Обратитесь к администратору.")
        return redirect("/login")

    ctx = {"role": profile.role}

    if profile.role == Profile.Role.ADMIN:
        return render(request, "accounts/dashboard.html", ctx)

    if profile.role == Profile.Role.STUDENT:
        courses = Course.objects.filter(enrollments__student=request.user).distinct().order_by("name")
        ctx["courses"] = courses
        return render(request, "accounts/dashboard.html", ctx)

    if profile.role == Profile.Role.PARENT:
        children_links = ParentChild.objects.filter(parent=request.user).select_related("child").order_by("child__username")
        ctx["children_links"] = children_links
        return render(request, "accounts/dashboard.html", ctx)

    if profile.role == Profile.Role.TEACHER:
        courses = Course.objects.filter(teacher=request.user).order_by("name")
        ctx["courses"] = courses
        return render(request, "accounts/dashboard.html", ctx)

    return render(request, "accounts/dashboard.html", ctx)
