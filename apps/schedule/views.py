from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

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
        events = qs.filter(Q(course__in=enrolled_courses) | Q(participants=request.user)).distinct()
        ctx = {"events": events, "mode": "student"}
        return render(request, "schedule/calendar_list.html", ctx)

    if profile.role == Profile.Role.PARENT:
        children = ParentChild.objects.filter(parent=request.user).select_related("child")
        child_ids = [c.child_id for c in children]
        enrolled_courses = Course.objects.filter(enrollments__student_id__in=child_ids).distinct()
        events = qs.filter(Q(course__in=enrolled_courses) | Q(participants__in=child_ids)).distinct()
        ctx = {"events": events, "mode": "parent", "children": children}
        return render(request, "schedule/calendar_list.html", ctx)

    return render(request, "schedule/calendar_list.html", {"events": [], "mode": "unknown"})
