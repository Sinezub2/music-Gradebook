# apps/accounts/views.py
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare

from .decorators import role_required
from .forms import InviteRegistrationForm, LoginForm, StudentInviteCreateForm, UsernameChangeForm
from .models import Profile, StudentInvitation
from .utils import get_user_display_name
from apps.school.models import ParentChild, Course, Enrollment
from apps.school.utils import get_user_single_class


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
        children_links = (
            ParentChild.objects.filter(parent=request.user)
            .select_related("child")
            .order_by("child__first_name", "child__last_name", "child__username")
        )
        ctx["children_links"] = children_links
        return render(request, "accounts/dashboard.html", ctx)

    if profile.role == Profile.Role.TEACHER:
        courses = Course.objects.filter(teacher=request.user).order_by("name")
        ctx["courses"] = courses
        return render(request, "accounts/dashboard.html", ctx)

    return render(request, "accounts/dashboard.html", ctx)


def _get_invitation_by_token(raw_token: str):
    token_hash = StudentInvitation.hash_token(raw_token)
    invitation = StudentInvitation.objects.select_related("course", "teacher").filter(token=token_hash).first()
    if not invitation:
        return None
    if not constant_time_compare(invitation.token, token_hash):
        return None
    return invitation


@role_required(Profile.Role.TEACHER)
def teacher_student_invite_create(request):
    class_resolution = get_user_single_class(request.user)
    if class_resolution.status == "none":
        messages.error(request, "Класс не назначен. Обратитесь к администратору.")
        return redirect("/teacher/class/")
    if class_resolution.status == "multiple":
        messages.error(request, "Для приглашений должен быть назначен один класс.")
        return redirect("/teacher/class/")

    course = class_resolution.course
    registration_url = ""
    created_invitation = None

    if request.method == "POST":
        form = StudentInviteCreateForm(request.POST)
        if form.is_valid():
            raw_token = StudentInvitation.generate_raw_token()
            created_invitation = StudentInvitation.objects.create(
                teacher=request.user,
                course=course,
                first_name=form.cleaned_data["first_name"].strip(),
                last_name=form.cleaned_data["last_name"].strip(),
                school_grade=form.cleaned_data.get("school_grade", "").strip(),
                token=StudentInvitation.hash_token(raw_token),
            )
            registration_url = request.build_absolute_uri(
                reverse("register_by_invite", kwargs={"token": raw_token})
            )
            messages.success(request, "Ссылка-приглашение создана.")
            form = StudentInviteCreateForm()
    else:
        form = StudentInviteCreateForm()

    return render(
        request,
        "accounts/student_invite_create.html",
        {
            "form": form,
            "course": course,
            "registration_url": registration_url,
            "created_invitation": created_invitation,
        },
    )


def register_by_invite(request, token: str):
    if request.user.is_authenticated:
        return redirect("/dashboard")

    invitation = _get_invitation_by_token(token)
    if not invitation or invitation.is_used or invitation.is_expired:
        return render(
            request,
            "accounts/register_by_invite.html",
            {"invite_invalid": True},
            status=404,
        )

    if request.method == "POST":
        form = InviteRegistrationForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    locked_invitation = (
                        StudentInvitation.objects.select_for_update()
                        .select_related("course")
                        .get(id=invitation.id)
                    )
                    token_hash = StudentInvitation.hash_token(token)
                    if (
                        not constant_time_compare(locked_invitation.token, token_hash)
                        or locked_invitation.is_used
                        or locked_invitation.is_expired
                    ):
                        messages.error(request, "Ссылка приглашения недействительна.")
                        return redirect(request.path)

                    user = form.save(commit=False)
                    user.first_name = locked_invitation.first_name
                    user.last_name = locked_invitation.last_name
                    user.save()

                    Profile.objects.create(
                        user=user,
                        role=Profile.Role.STUDENT,
                        school_grade=locked_invitation.school_grade,
                    )
                    Enrollment.objects.get_or_create(course=locked_invitation.course, student=user)

                    locked_invitation.is_used = True
                    locked_invitation.used_at = timezone.now()
                    locked_invitation.save(update_fields=["is_used", "used_at"])
            except IntegrityError:
                form.add_error("username", "Этот логин уже занят.")
            else:
                messages.success(request, "Регистрация завершена. Войдите под новым логином.")
                return redirect("/login")
    else:
        form = InviteRegistrationForm()

    return render(
        request,
        "accounts/register_by_invite.html",
        {
            "invite_invalid": False,
            "form": form,
            "invitation": invitation,
        },
    )


@login_required
def profile_view(request):
    return render(
        request,
        "accounts/profile.html",
        {
            "display_name": get_user_display_name(request.user),
            "username_form": UsernameChangeForm(request.user),
            "password_form": PasswordChangeForm(request.user),
        },
    )


@login_required
def profile_change_username(request):
    if request.method != "POST":
        return redirect("/profile/")

    username_form = UsernameChangeForm(request.user, request.POST)
    password_form = PasswordChangeForm(request.user)
    if username_form.is_valid():
        username_form.save()
        messages.success(request, "Логин обновлён.")
        return redirect("/profile/")

    return render(
        request,
        "accounts/profile.html",
        {
            "display_name": get_user_display_name(request.user),
            "username_form": username_form,
            "password_form": password_form,
        },
        status=400,
    )


@login_required
def profile_change_password(request):
    if request.method != "POST":
        return redirect("/profile/")

    username_form = UsernameChangeForm(request.user)
    password_form = PasswordChangeForm(request.user, request.POST)
    if password_form.is_valid():
        user = password_form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Пароль обновлён.")
        return redirect("/profile/")

    return render(
        request,
        "accounts/profile.html",
        {
            "display_name": get_user_display_name(request.user),
            "username_form": username_form,
            "password_form": password_form,
        },
        status=400,
    )
