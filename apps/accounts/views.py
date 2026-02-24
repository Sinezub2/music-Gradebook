# apps/accounts/views.py
from datetime import datetime, time, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare

from apps.gradebook.models import Grade
from apps.homework.models import AssignmentTarget
from apps.lessons.models import Lesson
from apps.schedule.models import Event
from apps.school.models import ParentChild, Course, Enrollment
from apps.school.utils import get_user_single_class, get_teacher_students

from .decorators import role_required
from .forms import InviteRegistrationForm, LoginForm, StudentInviteCreateForm, UsernameChangeForm
from .library_service import LIBRARY_CATEGORIES, build_library_items_for_student
from .models import Profile, StudentInvitation
from .utils import get_user_display_name


DEFAULT_SCHOOL_LIFE_ITEMS = [
    {
        "title": "Зимний концерт 2024",
        "description": "Приглашаем вас на ежегодный зимний концерт, где выступят артисты всех уровней.",
        "date_label": "15 февраля",
        "type_label": "Концерт",
    },
    {
        "title": "Промежуточные экзамены",
        "description": "Экзамены пройдут с 20 по 25 февраля. Пожалуйста, подготовьтесь заранее.",
        "date_label": "20 февраля",
        "type_label": "Экзамен",
    },
    {
        "title": "Мастер-класс с профессором Волковым",
        "description": "Известный пианист проведет мастер-класс для учеников продвинутого уровня.",
        "date_label": "28 февраля",
        "type_label": "Событие",
    },
]


def _display_name(user) -> str:
    return (user.get_full_name() or "").strip() or user.username or "Без имени"


def _today_bounds():
    today = timezone.localdate()
    local_tz = timezone.get_current_timezone()
    day_start = timezone.make_aware(datetime.combine(today, time.min), local_tz)
    day_end = day_start + timedelta(days=1)
    return today, day_start, day_end


def _announcements_for_events(events_qs, limit: int = 6):
    rows = []
    for event in events_qs.order_by("start_datetime")[:limit]:
        rows.append(
            {
                "title": event.title,
                "description": event.description or "Подробности доступны в расписании.",
                "date_label": timezone.localtime(event.start_datetime).strftime("%d %B"),
                "type_label": event.get_event_type_display(),
                "external_url": event.external_url,
            }
        )
    return rows


def _build_teacher_schedule(user):
    courses = Course.objects.filter(teacher=user).order_by("name")
    today, day_start, day_end = _today_bounds()
    rows = []

    events = (
        Event.objects.filter(course__in=courses, start_datetime__gte=day_start, start_datetime__lt=day_end)
        .select_related("course")
        .order_by("start_datetime")
    )
    for event in events:
        rows.append(
            {
                "time_label": timezone.localtime(event.start_datetime).strftime("%H:%M"),
                "title": event.title,
                "subtitle": event.course.name if event.course else event.get_event_type_display(),
                "action_url": f"/attendance/?course={event.course_id}&month={today:%Y-%m}" if event.course_id else "/attendance/",
            }
        )

    if rows:
        return rows

    lessons = Lesson.objects.filter(course__in=courses, date=today).select_related("course").order_by("id")
    for idx, lesson in enumerate(lessons):
        rows.append(
            {
                "time_label": f"{9 + idx:02d}:00",
                "title": lesson.topic,
                "subtitle": lesson.course.name,
                "action_url": f"/attendance/?course={lesson.course_id}&month={today:%Y-%m}",
            }
        )
    return rows


def _countdown_parts(target_dt):
    diff_seconds = int((target_dt - timezone.now()).total_seconds())
    if diff_seconds <= 0:
        return {"days": 0, "hours": 0, "minutes": 0}
    total_minutes = diff_seconds // 60
    days, remainder = divmod(total_minutes, 60 * 24)
    hours, minutes = divmod(remainder, 60)
    return {"days": days, "hours": hours, "minutes": minutes}


def _next_lesson_for_student(student):
    now = timezone.now()
    today = timezone.localdate()
    courses = Course.objects.filter(enrollments__student=student).distinct()

    next_event = (
        Event.objects.filter(Q(participants=student) | Q(course__in=courses), start_datetime__gte=now)
        .select_related("course")
        .distinct()
        .order_by("start_datetime")
        .first()
    )
    if next_event:
        starts = timezone.localtime(next_event.start_datetime)
        return {
            "starts_at": next_event.start_datetime,
            "starts_label": starts.strftime("%A, %d %B в %H:%M"),
            "title": next_event.title,
            "subtitle": next_event.course.name if next_event.course else next_event.get_event_type_display(),
        }

    next_lesson = (
        Lesson.objects.filter(course__in=courses, date__gte=today)
        .select_related("course")
        .order_by("date", "id")
        .first()
    )
    if next_lesson:
        local_tz = timezone.get_current_timezone()
        starts_at = timezone.make_aware(datetime.combine(next_lesson.date, time(hour=9)), local_tz)
        return {
            "starts_at": starts_at,
            "starts_label": starts_at.strftime("%A, %d %B в %H:%M"),
            "title": next_lesson.topic,
            "subtitle": next_lesson.course.name,
        }

    return None


def _student_dashboard_payload(student):
    today = timezone.localdate()
    courses = Course.objects.filter(enrollments__student=student).distinct()
    next_lesson = _next_lesson_for_student(student)

    latest_target = (
        AssignmentTarget.objects.filter(student=student)
        .select_related("assignment")
        .order_by("-assignment__due_date")
        .first()
    )
    if latest_target:
        if latest_target.status == AssignmentTarget.Status.DONE:
            homework_status = "Выполнено"
        elif latest_target.assignment.due_date < today:
            homework_status = "Просрочено"
        else:
            homework_status = "В работе"
        homework_hint = f"{latest_target.assignment.title} · до {latest_target.assignment.due_date:%d.%m.%Y}"
    else:
        homework_status = "Нет активных заданий"
        homework_hint = ""

    progress_points = []
    grade_rows = list(
        Grade.objects.filter(student=student, score__isnull=False)
        .select_related("assessment")
        .order_by("-id")[:6]
    )
    grade_rows.reverse()
    for grade in grade_rows:
        score = float(grade.score)
        progress_points.append(
            {
                "label": grade.assessment.title[:28],
                "score": round(score, 1),
                "percent": max(0, min(100, round(score))),
            }
        )

    announcement_qs = (
        Event.objects.exclude(event_type=Event.EventType.LESSON)
        .filter(Q(course__isnull=True) | Q(course__in=courses) | Q(participants=student))
        .distinct()
    )
    announcements = _announcements_for_events(announcement_qs, limit=3) or DEFAULT_SCHOOL_LIFE_ITEMS

    return {
        "next_lesson": next_lesson,
        "next_lesson_countdown": _countdown_parts(next_lesson["starts_at"]) if next_lesson else {"days": 0, "hours": 0, "minutes": 0},
        "homework_status": homework_status,
        "homework_hint": homework_hint,
        "progress_points": progress_points,
        "announcements": announcements,
    }


def _teacher_threads(user):
    today = timezone.localdate()
    threads = []
    students = (
        get_user_model()
        .objects.filter(enrollments__course__teacher=user, profile__role=Profile.Role.STUDENT)
        .select_related("profile")
        .distinct()
        .order_by("first_name", "last_name", "username")[:20]
    )
    for student in students:
        next_target = (
            AssignmentTarget.objects.filter(student=student, assignment__course__teacher=user)
            .select_related("assignment")
            .order_by("assignment__due_date")
            .first()
        )
        overdue = AssignmentTarget.objects.filter(
            student=student,
            assignment__course__teacher=user,
            status=AssignmentTarget.Status.TODO,
            assignment__due_date__lt=today,
        ).count()
        preview = next_target.assignment.title if next_target else "Учебных обновлений пока нет."
        threads.append(
            {
                "id": f"student-{student.id}",
                "title": _display_name(student),
                "subtitle": student.profile.get_cycle_display(),
                "preview": preview,
                "unread": overdue,
                "time_label": "Сегодня",
            }
        )

    threads.insert(
        0,
        {
            "id": "admin",
            "title": "Администрация школы",
            "subtitle": "Служебный канал",
            "preview": "Напоминание: ближайшие экзамены и концерты в разделе «Школьная жизнь».",
            "unread": 1,
            "time_label": "Вчера",
        },
    )
    return threads


def _student_threads(user):
    today = timezone.localdate()
    threads = []
    teachers = (
        get_user_model()
        .objects.filter(teaching_courses__enrollments__student=user, profile__role=Profile.Role.TEACHER)
        .distinct()
        .order_by("first_name", "last_name", "username")
    )
    for teacher in teachers:
        due = (
            AssignmentTarget.objects.filter(student=user, assignment__course__teacher=teacher, status=AssignmentTarget.Status.TODO)
            .select_related("assignment")
            .order_by("assignment__due_date")
            .first()
        )
        preview = due.assignment.title if due else "Новых заданий нет."
        is_overdue = bool(due and due.assignment.due_date < today)
        threads.append(
            {
                "id": f"teacher-{teacher.id}",
                "title": _display_name(teacher),
                "subtitle": "Преподаватель",
                "preview": preview,
                "unread": 1 if is_overdue else 0,
                "time_label": "Сегодня",
            }
        )
    threads.insert(
        0,
        {
            "id": "admin",
            "title": "Администрация школы",
            "subtitle": "Служебный канал",
            "preview": "Проверьте раздел «Школьная жизнь» для новых объявлений.",
            "unread": 0,
            "time_label": "Сегодня",
        },
    )
    return threads


def _parent_threads(user):
    today = timezone.localdate()
    threads = []
    children_links = ParentChild.objects.filter(parent=user).select_related("child")
    for link in children_links:
        child = link.child
        teachers = (
            get_user_model()
            .objects.filter(teaching_courses__enrollments__student=child, profile__role=Profile.Role.TEACHER)
            .distinct()
            .order_by("first_name", "last_name", "username")
        )
        for teacher in teachers:
            due = (
                AssignmentTarget.objects.filter(
                    student=child,
                    assignment__course__teacher=teacher,
                    status=AssignmentTarget.Status.TODO,
                )
                .select_related("assignment")
                .order_by("assignment__due_date")
                .first()
            )
            overdue = 1 if due and due.assignment.due_date < today else 0
            threads.append(
                {
                    "id": f"child-{child.id}-teacher-{teacher.id}",
                    "title": f"{_display_name(teacher)} / {_display_name(child)}",
                    "subtitle": "Преподаватель и родитель",
                    "preview": due.assignment.title if due else "Новых задач нет.",
                    "unread": overdue,
                    "time_label": "Сегодня",
                }
            )

    threads.insert(
        0,
        {
            "id": "admin",
            "title": "Администрация школы",
            "subtitle": "Информационные рассылки",
            "preview": "Календарь школы обновлен. Проверьте экзамены и концерты.",
            "unread": 0,
            "time_label": "Сегодня",
        },
    )
    return threads


def _admin_threads():
    teachers = (
        get_user_model()
        .objects.filter(profile__role=Profile.Role.TEACHER)
        .order_by("first_name", "last_name", "username")[:20]
    )
    threads = [
        {
            "id": f"teacher-{teacher.id}",
            "title": _display_name(teacher),
            "subtitle": "Преподаватель",
            "preview": "Сводка учебной недели доступна в аналитике.",
            "unread": 0,
            "time_label": "Сегодня",
        }
        for teacher in teachers
    ]
    return threads or [
        {
            "id": "admin",
            "title": "Администрация школы",
            "subtitle": "Служебный канал",
            "preview": "Нет активных диалогов.",
            "unread": 0,
            "time_label": "Сегодня",
        }
    ]


def _build_communication_threads(user, role):
    if role == Profile.Role.TEACHER:
        return _teacher_threads(user)
    if role == Profile.Role.STUDENT:
        return _student_threads(user)
    if role == Profile.Role.PARENT:
        return _parent_threads(user)
    if role == Profile.Role.ADMIN:
        return _admin_threads()
    return []


def _conversation_from_thread(thread):
    if not thread:
        return []
    return [
        {
            "outgoing": False,
            "author": thread["title"],
            "text": thread["preview"],
            "time_label": thread["time_label"],
        },
        {
            "outgoing": True,
            "author": "Вы",
            "text": "Принято. Спасибо, информацию зафиксировал(а).",
            "time_label": "только что",
        },
    ]


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
    today = timezone.localdate()

    if profile.role == Profile.Role.ADMIN:
        user_model = get_user_model()
        ctx.update(
            {
                "dashboard_mode": "admin",
                "dashboard_stats": [
                    {"label": "Педагоги", "value": user_model.objects.filter(profile__role=Profile.Role.TEACHER).count()},
                    {"label": "Ученики", "value": user_model.objects.filter(profile__role=Profile.Role.STUDENT).count()},
                    {"label": "Курсы", "value": Course.objects.count()},
                    {"label": "События (месяц)", "value": Event.objects.filter(start_datetime__month=today.month).count()},
                ],
                "announcements": _announcements_for_events(
                    Event.objects.exclude(event_type=Event.EventType.LESSON),
                    limit=4,
                )
                or DEFAULT_SCHOOL_LIFE_ITEMS,
            }
        )
        return render(request, "accounts/dashboard.html", ctx)

    if profile.role == Profile.Role.TEACHER:
        courses = Course.objects.filter(teacher=request.user).order_by("name")
        student_ids = list(
            Enrollment.objects.filter(course__in=courses)
            .values_list("student_id", flat=True)
            .distinct()
        )
        schedule_rows = _build_teacher_schedule(request.user)
        pending_targets = AssignmentTarget.objects.filter(
            assignment__course__in=courses,
            status=AssignmentTarget.Status.TODO,
            assignment__due_date__lte=today,
        ).count()
        ctx.update(
            {
                "dashboard_mode": "teacher",
                "today_label": today.strftime("%A, %d %B"),
                "today_schedule": schedule_rows,
                "dashboard_stats": [
                    {"label": "Всего учеников", "value": len(student_ids)},
                    {"label": "Уроков сегодня", "value": len(schedule_rows)},
                    {"label": "Активные курсы", "value": courses.count()},
                    {"label": "Задач к проверке", "value": pending_targets},
                ],
            }
        )
        return render(request, "accounts/dashboard.html", ctx)

    if profile.role == Profile.Role.STUDENT:
        ctx.update({"dashboard_mode": "student", **_student_dashboard_payload(request.user)})
        return render(request, "accounts/dashboard.html", ctx)

    if profile.role == Profile.Role.PARENT:
        children_links = list(
            ParentChild.objects.filter(parent=request.user)
            .select_related("child", "child__profile")
            .order_by("child__first_name", "child__last_name", "child__username")
        )
        selected_child = None
        selected_child_param = request.GET.get("student")
        if selected_child_param:
            for link in children_links:
                if str(link.child_id) == str(selected_child_param):
                    selected_child = link.child
                    break
        if not selected_child and children_links:
            selected_child = children_links[0].child

        ctx.update(
            {
                "dashboard_mode": "parent",
                "children_links": children_links,
                "selected_child": selected_child,
            }
        )
        if selected_child:
            ctx.update(_student_dashboard_payload(selected_child))
        return render(request, "accounts/dashboard.html", ctx)

    return render(request, "accounts/dashboard.html", ctx)


@login_required
def communication_view(request):
    role = request.user.profile.role
    work_mode = request.GET.get("work", "1") != "0"
    threads = _build_communication_threads(request.user, role)
    selected_chat_id = request.GET.get("chat") or (threads[0]["id"] if threads else "")
    selected_thread = next((thread for thread in threads if thread["id"] == selected_chat_id), None)
    if not selected_thread and threads:
        selected_thread = threads[0]
    conversation = _conversation_from_thread(selected_thread)

    return render(
        request,
        "accounts/communication.html",
        {
            "threads": threads,
            "selected_chat_id": selected_chat_id,
            "selected_thread": selected_thread,
            "conversation": conversation,
            "work_mode": work_mode,
        },
    )


@login_required
def school_life_view(request):
    role = request.user.profile.role
    events_qs = Event.objects.exclude(event_type=Event.EventType.LESSON).select_related("course")

    if role == Profile.Role.TEACHER:
        events_qs = events_qs.filter(Q(course__teacher=request.user) | Q(course__isnull=True)).distinct()
    elif role == Profile.Role.STUDENT:
        events_qs = events_qs.filter(
            Q(course__enrollments__student=request.user)
            | Q(participants=request.user)
            | Q(course__isnull=True)
        ).distinct()
    elif role == Profile.Role.PARENT:
        child_ids = ParentChild.objects.filter(parent=request.user).values_list("child_id", flat=True)
        events_qs = events_qs.filter(
            Q(course__enrollments__student_id__in=child_ids)
            | Q(participants__id__in=child_ids)
            | Q(course__isnull=True)
        ).distinct()

    announcements = _announcements_for_events(events_qs, limit=12)
    if not announcements:
        announcements = DEFAULT_SCHOOL_LIFE_ITEMS

    return render(
        request,
        "accounts/school_life.html",
        {"announcements": announcements},
    )


@login_required
def library_view(request):
    role = request.user.profile.role
    search_query = (request.GET.get("q") or "").strip()
    selected_student_id = request.GET.get("student") or ""
    selected_category = (request.GET.get("category") or "").strip()
    selected_student = None
    student_choices = []
    resources = []

    if role == Profile.Role.TEACHER:
        teacher_students = list(get_teacher_students(request.user))
        student_choices = [
            {"id": student.id, "label": _display_name(student)}
            for student in teacher_students
        ]
        if teacher_students:
            selected_student = next(
                (student for student in teacher_students if str(student.id) == str(selected_student_id)),
                teacher_students[0],
            )
            resources = build_library_items_for_student(selected_student, teacher=request.user)

    elif role == Profile.Role.STUDENT:
        selected_student = request.user
        resources = build_library_items_for_student(selected_student)

    elif role == Profile.Role.PARENT:
        children_links = list(
            ParentChild.objects.filter(parent=request.user)
            .select_related("child")
            .order_by("child__first_name", "child__last_name", "child__username")
        )
        children = [link.child for link in children_links]
        student_choices = [
            {"id": child.id, "label": _display_name(child)}
            for child in children
        ]
        if children:
            selected_student = next(
                (child for child in children if str(child.id) == str(selected_student_id)),
                children[0],
            )
            resources = build_library_items_for_student(selected_student)

    elif role == Profile.Role.ADMIN:
        user_model = get_user_model()
        all_students = list(
            user_model.objects.filter(profile__role=Profile.Role.STUDENT)
            .select_related("profile")
            .order_by("first_name", "last_name", "username")
        )
        student_choices = [
            {"id": student.id, "label": _display_name(student)}
            for student in all_students
        ]
        if all_students:
            selected_student = next(
                (student for student in all_students if str(student.id) == str(selected_student_id)),
                all_students[0],
            )
            resources = build_library_items_for_student(selected_student)

    if search_query:
        lowered = search_query.lower()
        resources = [
            row
            for row in resources
            if lowered in row["title"].lower()
            or lowered in row["category"].lower()
            or lowered in row["course_name"].lower()
            or lowered in row["source"].lower()
            or lowered in row["uploaded_by"].lower()
        ]

    category_counts = {category: 0 for category in LIBRARY_CATEGORIES}
    for row in resources:
        if row["category"] in category_counts:
            category_counts[row["category"]] += 1
    all_count = len(resources)

    if selected_category and selected_category in LIBRARY_CATEGORIES:
        resources = [row for row in resources if row["category"] == selected_category]
    else:
        selected_category = ""

    base_params = {}
    if search_query:
        base_params["q"] = search_query
    if selected_student:
        base_params["student"] = selected_student.id

    category_tabs = []
    all_query = urlencode(base_params)
    category_tabs.append(
        {
            "label": "Все",
            "value": "",
            "count": all_count,
            "active": not selected_category,
            "url": f"/library/?{all_query}" if all_query else "/library/",
        }
    )
    for category in LIBRARY_CATEGORIES:
        params = dict(base_params)
        params["category"] = category
        query = urlencode(params)
        category_tabs.append(
            {
                "label": category,
                "value": category,
                "count": category_counts.get(category, 0),
                "active": selected_category == category,
                "url": f"/library/?{query}",
            }
        )

    return render(
        request,
        "accounts/library.html",
        {
            "search_query": search_query,
            "resources": resources,
            "student_choices": student_choices,
            "selected_student": selected_student,
            "selected_category": selected_category,
            "category_tabs": category_tabs,
        },
    )


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
