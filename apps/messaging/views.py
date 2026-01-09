from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.models import Profile
from apps.school.models import Course, ParentChild
from .forms import MessageForm
from .models import Thread, Message


@login_required
def inbox(request):
    role = request.user.profile.role
    if role == Profile.Role.ADMIN:
        threads = Thread.objects.all().select_related("teacher", "parent", "student")
    elif role == Profile.Role.TEACHER:
        threads = Thread.objects.filter(teacher=request.user).select_related("teacher", "parent", "student")
    elif role == Profile.Role.PARENT:
        threads = Thread.objects.filter(parent=request.user).select_related("teacher", "parent", "student")
    elif role == Profile.Role.STUDENT:
        threads = Thread.objects.filter(student=request.user).select_related("teacher", "parent", "student")
    else:
        threads = Thread.objects.none()

    return render(request, "messaging/inbox.html", {"threads": threads})


@login_required
def thread_detail(request, thread_id: int):
    thread = get_object_or_404(Thread.objects.select_related("teacher", "parent", "student"), id=thread_id)

    if request.user.profile.role != Profile.Role.ADMIN and request.user.id not in (thread.teacher_id, thread.parent_id, thread.student_id):
        return HttpResponseForbidden("Нет доступа к этому чату.")

    if request.method == "POST":
        form = MessageForm(request.POST)
        if form.is_valid():
            Message.objects.create(thread=thread, sender=request.user, text=form.cleaned_data["text"])
            return redirect(f"/messages/{thread.id}/")
    else:
        form = MessageForm()

    msgs = Message.objects.filter(thread=thread).select_related("sender").order_by("created_at")
    return render(request, "messaging/thread_detail.html", {"thread": thread, "messages": msgs, "form": form})


@login_required
def start_for_student(request, student_id: int):
    if request.user.profile.role != Profile.Role.PARENT:
        return HttpResponseForbidden("Доступно только родителю.")

    # parent can only start for own child
    get_object_or_404(ParentChild, parent=request.user, child_id=student_id)

    teacher_ids = list(
        Course.objects.filter(enrollments__student_id=student_id)
        .exclude(teacher_id=None)
        .values_list("teacher_id", flat=True)
        .distinct()
    )
    teacher_ids = [tid for tid in teacher_ids if tid]

    if not teacher_ids:
        return redirect("/messages/")

    # minimal: take first teacher
    thread, _ = Thread.objects.get_or_create(teacher_id=teacher_ids[0], parent=request.user, student_id=student_id)
    return redirect(f"/messages/{thread.id}/")
