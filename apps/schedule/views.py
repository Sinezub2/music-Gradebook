from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.models import Profile
from apps.school.models import Course, Enrollment, ParentChild
from .models import Event


@login_required
def calendar_list(request):
    profile = request.user.profile

    qs = Event.objects.all().select_related("course", "created_by").prefetch_related("participants")

    if profile.role == Profile.Role.ADMIN:
        events = qs
        ctx = {"events": events, "mode": "admin"}
        return render(request, "schedule/calendar_list.html", ctx)

    if profile.role == Profile.Role.TEACHER:
        teacher_courses = Course.objects.filter(teacher=request.user)
        events = qs.filter(Q(course__in=teacher_courses) | Q(created_by=request.user)).distinct()
        ctx = {"events": events, "mode": "teacher"}
        return render(request, "schedule/calendar_list.html", ctx)

    if profile.role == Profile.Role.STUDENT:
        enrolled_courses = Course.objects.filter(enrollments__student=request.user)
        events = qs.filter(participants=request.user).distinct()
        registration_events = (
            qs.filter(Q(course__in=enrolled_courses) | Q(course__isnull=True))
            .exclude(participants=request.user)
            .distinct()
        )
        ctx = {
            "events": events,
            "registration_events": registration_events,
            "mode": "student",
        }
        return render(request, "schedule/calendar_list.html", ctx)

    if profile.role == Profile.Role.PARENT:
        children = ParentChild.objects.filter(parent=request.user).select_related("child")
        child_ids = [c.child_id for c in children]
        enrolled_courses = Course.objects.filter(enrollments__student_id__in=child_ids).distinct()
        events = qs.filter(Q(course__in=enrolled_courses) | Q(participants__in=child_ids)).distinct()
        ctx = {"events": events, "mode": "parent", "children": children}
        return render(request, "schedule/calendar_list.html", ctx)

    return render(request, "schedule/calendar_list.html", {"events": [], "mode": "unknown"})


@login_required
def register_event(request, event_id: int):
    if request.user.profile.role != Profile.Role.STUDENT:
        return HttpResponseForbidden("Только ученики могут регистрироваться.")

    if request.method != "POST":
        return HttpResponseForbidden("Требуется POST.")

    event = get_object_or_404(Event.objects.select_related("course"), id=event_id)
    if event.course_id:
        if not Enrollment.objects.filter(course=event.course, student=request.user).exists():
            return HttpResponseForbidden("Нет доступа к этому событию.")

    event.participants.add(request.user)
    messages.success(request, "Вы зарегистрированы на событие.")
    return redirect("/calendar/?tab=registration")
