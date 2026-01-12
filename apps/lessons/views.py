from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.decorators import role_required
from apps.accounts.models import Profile
from apps.school.models import Course, Enrollment, ParentChild
from .forms import LessonCreateForm
from .models import Lesson, LessonReport


def _student_ids_for_user(request):
    role = request.user.profile.role
    if role == Profile.Role.STUDENT:
        return [request.user.id]
    if role == Profile.Role.PARENT:
        return list(ParentChild.objects.filter(parent=request.user).values_list("child_id", flat=True))
    return []


@login_required
def lesson_list(request):
    role = request.user.profile.role
    course_id = request.GET.get("course")

    if role == Profile.Role.ADMIN:
        qs = Lesson.objects.all().select_related("course", "created_by")
    elif role == Profile.Role.TEACHER:
        qs = Lesson.objects.filter(course__teacher=request.user).select_related("course", "created_by")
    else:
        student_ids = _student_ids_for_user(request)
        course_ids = Enrollment.objects.filter(student_id__in=student_ids).values_list("course_id", flat=True)
        qs = Lesson.objects.filter(course_id__in=course_ids).select_related("course", "created_by")

    if course_id:
        qs = qs.filter(course_id=course_id)

    return render(request, "lessons/lesson_list.html", {"lessons": qs.order_by("-date"), "course_id": course_id})


@role_required(Profile.Role.TEACHER, Profile.Role.ADMIN)
def lesson_create(request):
    if request.method == "POST":
        form = LessonCreateForm(request.POST, teacher_user=(request.user if request.user.profile.role == Profile.Role.TEACHER else None))
        if form.is_valid():
            course = form.cleaned_data["course"]
            if request.user.profile.role == Profile.Role.TEACHER and course.teacher_id != request.user.id:
                return HttpResponseForbidden("Нельзя создавать уроки для чужого курса.")

            lesson = Lesson.objects.create(
                course=course,
                date=form.cleaned_data["date"],
                topic=form.cleaned_data["topic"],
                created_by=request.user,
            )

            text = (form.cleaned_data.get("report_text") or "").strip()
            media = (form.cleaned_data.get("media_url") or "").strip()
            if text or media:
                LessonReport.objects.create(lesson=lesson, student=None, text=text, media_url=media)

            messages.success(request, "Урок создан.")
            return redirect(f"/lessons/{lesson.id}/")
    else:
        form = LessonCreateForm(teacher_user=(request.user if request.user.profile.role == Profile.Role.TEACHER else None))

    return render(request, "lessons/lesson_create.html", {"form": form})


@login_required
def lesson_detail(request, lesson_id: int):
    lesson = get_object_or_404(Lesson.objects.select_related("course", "created_by"), id=lesson_id)

    role = request.user.profile.role
    if role == Profile.Role.TEACHER:
        if lesson.course.teacher_id != request.user.id:
            return HttpResponseForbidden("Нет доступа.")
    elif role in (Profile.Role.STUDENT, Profile.Role.PARENT):
        student_ids = _student_ids_for_user(request)
        if not Enrollment.objects.filter(course=lesson.course, student_id__in=student_ids).exists():
            return HttpResponseForbidden("Нет доступа.")
    # admin ok

    reports = LessonReport.objects.filter(lesson=lesson).select_related("student").order_by("-created_at")
    return render(request, "lessons/lesson_detail.html", {"lesson": lesson, "reports": reports})
