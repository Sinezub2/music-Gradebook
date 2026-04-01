
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from urllib.parse import urlencode

from apps.accounts.decorators import role_required
from apps.accounts.models import LibraryVideo, Profile
from apps.gradebook.models import Assessment
from apps.goals.models import Goal
from apps.school.models import Course, ParentChild
from apps.school.utils import get_teacher_student_or_404, get_user_single_class, resolve_teacher_course_for_student
from .forms import AssignmentCreateForm, AssignmentSubmissionForm, StudentAssignmentCreateForm
from .models import Assignment, AssignmentTarget
from .services import create_assignment_with_targets_and_gradebook

HALF_YEAR_I = "H1"
HALF_YEAR_II = "H2"


def _effective_status(assignment: Assignment, target: AssignmentTarget | None) -> str:
    """
    Display logic:
    DONE stays DONE
    else if due_date < today -> LATE (computed)
    else TODO
    """
    if target and target.status == AssignmentTarget.Status.DONE:
        return "DONE"
    if assignment.due_date < date.today():
        return "LATE"
    return "TODO"


def _can_delete_assignment(user, role: str, assignment: Assignment) -> bool:
    if role == Profile.Role.ADMIN:
        return True
    if role != Profile.Role.TEACHER:
        return False
    return assignment.created_by_id == user.id or assignment.course.teacher_id == user.id


def _build_assignments_url(cycle: str) -> str:
    params = {}
    if cycle:
        params["cycle"] = cycle
    return f"/assignments/?{urlencode(params)}" if params else "/assignments/"


def _collect_compositions(post_data) -> list[str]:
    items = []
    seen = set()
    for raw_value in post_data.getlist("composition_name"):
        value = (raw_value or "").strip()
        if not value or value in seen:
            continue
        items.append(value)
        seen.add(value)
    return items


def _normalize_title_key(value: str) -> str:
    return " ".join((value or "").split()).strip().casefold()


def _merge_unique_titles(*groups) -> list[str]:
    items = []
    seen = set()
    for group in groups:
        for raw_value in group:
            value = " ".join((raw_value or "").split()).strip()
            if not value:
                continue
            key = _normalize_title_key(value)
            if key in seen:
                continue
            items.append(value)
            seen.add(key)
    return items


def _current_half_year_code() -> str:
    return HALF_YEAR_I if date.today().month <= 6 else HALF_YEAR_II


def _normalize_half_year(raw_value: str) -> str:
    value = (raw_value or "").strip()
    if value in (HALF_YEAR_I, HALF_YEAR_II):
        return value
    return _current_half_year_code()


def _build_student_assignment_create_url(student_id: int, half_year: str = "") -> str:
    params = {}
    if half_year:
        params["half_year"] = half_year
    query = urlencode(params)
    base_url = f"/teacher/students/{student_id}/assignments/create/"
    return f"{base_url}?{query}" if query else base_url


def _get_carried_over_compositions(*, student, course: Course) -> list[str]:
    titles = AssignmentTarget.objects.filter(
        student=student,
        assignment__course=course,
        status=AssignmentTarget.Status.TODO,
    ).values_list("assignment__title", flat=True)
    return _merge_unique_titles(titles)


def _get_half_year_plan_titles(*, student, selected_half_year: str) -> list[str]:
    goals = Goal.objects.filter(student=student).order_by("month", "created_at")
    if selected_half_year == HALF_YEAR_I:
        goals = goals.filter(month__month__lte=6)
    else:
        goals = goals.filter(month__month__gte=7)
    return _merge_unique_titles(goals.values_list("title", flat=True))


def _filter_selected_plan_titles(raw_values: list[str], plan_titles: list[str]) -> list[str]:
    plan_lookup = {_normalize_title_key(title): title for title in plan_titles}
    selected = []
    seen = set()
    for raw_value in raw_values:
        key = _normalize_title_key(raw_value)
        if not key or key not in plan_lookup or key in seen:
            continue
        selected.append(plan_lookup[key])
        seen.add(key)
    return selected


def _sync_submission_video(*, target: AssignmentTarget, video_file):
    if not video_file:
        return None

    title = f"{target.assignment.title} — ответ ученика"
    existing_video = getattr(target, "submission_video", None)
    if existing_video:
        if existing_video.video and existing_video.video.name != getattr(video_file, "name", ""):
            existing_video.video.delete(save=False)
        existing_video.teacher = target.assignment.created_by
        existing_video.student = target.student
        existing_video.course = target.assignment.course
        existing_video.title = title
        existing_video.video = video_file
        existing_video.save()
        return existing_video

    return LibraryVideo.objects.create(
        teacher=target.assignment.created_by,
        student=target.student,
        course=target.assignment.course,
        assignment_target=target,
        title=title,
        video=video_file,
    )


def _create_assignments(
    *,
    teacher,
    course: Course,
    titles: list[str],
    description: str,
    due_date,
    attachment,
    student_ids: list[int],
) -> int:
    copied_attachment_bytes = None
    copied_attachment_name = ""
    if attachment and len(titles) > 1:
        copied_attachment_bytes = attachment.read()
        copied_attachment_name = attachment.name

    created_count = 0
    for title in titles:
        prepared_attachment = attachment
        if copied_attachment_bytes is not None:
            prepared_attachment = ContentFile(copied_attachment_bytes, name=copied_attachment_name)

        create_assignment_with_targets_and_gradebook(
            teacher=teacher,
            course=course,
            title=title,
            description=description,
            due_date=due_date,
            attachment=prepared_attachment,
            student_ids=student_ids,
        )
        created_count += 1
    return created_count


def _validate_homework_titles(titles: list[str]) -> list[str]:
    errors = []
    if any(len(title) > 200 for title in titles):
        errors.append("Название композиции должно быть не длиннее 200 символов.")
    return errors


@login_required
def assignment_list(request):
    profile = request.user.profile
    cycle = request.GET.get("cycle") or ""
    select_mode = request.GET.get("select") == "1"

    if profile.role == Profile.Role.TEACHER:
        qs = Assignment.objects.filter(created_by=request.user).select_related("course")
        if cycle:
            qs = qs.filter(targets__student__profile__cycle=cycle).distinct()
        qs = qs.order_by("due_date", "id")
        rows = []
        for a in qs:
            targets_qs = a.targets.all()
            if cycle:
                targets_qs = targets_qs.filter(student__profile__cycle=cycle)
            count_targets = targets_qs.count()
            rows.append(
                {
                    "assignment": a,
                    "count_targets": count_targets,
                    "can_delete": _can_delete_assignment(request.user, profile.role, a),
                }
            )
        base_url = _build_assignments_url(cycle)
        return render(
            request,
            "homework/assignment_list.html",
            {
                "mode": "TEACHER",
                "rows": rows,
                "cycle": cycle,
                "cycle_options": Profile.Cycle.choices,
                "select_mode": select_mode,
                "can_bulk_delete": True,
                "select_url": f"{base_url}{'&' if '?' in base_url else '?'}select=1",
                "cancel_select_url": base_url,
            },
        )

    if profile.role == Profile.Role.ADMIN:
        qs = Assignment.objects.all().select_related("course", "created_by")
        if cycle:
            qs = qs.filter(targets__student__profile__cycle=cycle).distinct()
        qs = qs.order_by("due_date", "id")
        assignments = []
        for assignment in qs:
            assignments.append(
                {"assignment": assignment, "can_delete": _can_delete_assignment(request.user, profile.role, assignment)}
            )
        base_url = _build_assignments_url(cycle)
        return render(
            request,
            "homework/assignment_list.html",
            {
                "mode": "ADMIN",
                "assignments": assignments,
                "cycle": cycle,
                "cycle_options": Profile.Cycle.choices,
                "select_mode": select_mode,
                "can_bulk_delete": True,
                "select_url": f"{base_url}{'&' if '?' in base_url else '?'}select=1",
                "cancel_select_url": base_url,
            },
        )

    if profile.role == Profile.Role.STUDENT:
        targets = (
            AssignmentTarget.objects.filter(student=request.user)
            .select_related("assignment", "assignment__course", "submission_video")
            .order_by("assignment__due_date", "assignment_id")
        )
        rows = []
        for t in targets:
            a = t.assignment
            rows.append({"target": t, "assignment": a, "status": _effective_status(a, t)})
        return render(request, "homework/assignment_list.html", {"mode": "STUDENT", "rows": rows, "student": request.user})

    if profile.role == Profile.Role.PARENT:
        children = (
            ParentChild.objects.filter(parent=request.user)
            .select_related("child")
            .order_by("child__first_name", "child__last_name", "child__username")
        )

        child_blocks = []
        for link in children:
            child = link.child
            targets = (
                AssignmentTarget.objects.filter(student=child)
                .select_related("assignment", "assignment__course", "submission_video")
                .order_by("assignment__due_date", "assignment_id")
            )
            rows = []
            for t in targets:
                a = t.assignment
                rows.append({"target": t, "assignment": a, "status": _effective_status(a, t)})
            child_blocks.append({"child": child, "rows": rows})

        return render(request, "homework/assignment_list.html", {"mode": "PARENT", "child_blocks": child_blocks})

    return render(request, "homework/assignment_list.html", {"mode": "UNKNOWN"})


@require_POST
@role_required(Profile.Role.TEACHER, Profile.Role.ADMIN)
def assignment_bulk_delete(request):
    role = request.user.profile.role
    selected_ids = []
    for raw_id in request.POST.getlist("selected_ids"):
        try:
            selected_ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue

    cycle = request.POST.get("cycle") or ""
    redirect_url = _build_assignments_url(cycle)

    if not selected_ids:
        messages.info(request, "Ничего не выбрано для удаления.")
        return redirect(redirect_url)

    assignments = list(Assignment.objects.filter(id__in=selected_ids).select_related("course", "created_by"))
    unauthorized = [a.id for a in assignments if not _can_delete_assignment(request.user, role, a)]
    if unauthorized:
        return HttpResponseForbidden("Нет доступа к удалению выбранных заданий.")

    Assessment.objects.filter(source_assignment__in=assignments).delete()
    deleted_count = 0
    for assignment in assignments:
        assignment.delete()
        deleted_count += 1

    messages.success(request, f"Удалено заданий: {deleted_count}.")
    return redirect(redirect_url)


@role_required(Profile.Role.TEACHER)
def assignment_create(request):
    """
    Без JS:
    - при одном классе у преподавателя курс подставляется автоматически
    - при нескольких классах сохраняется fallback-выбор курса
    - POST: создаём Assignment + Assessment + Targets + Grades
    """

    if request.user.profile.role == Profile.Role.TEACHER:
        messages.info(request, "Сначала выберите ученика в разделе «Класс».")
        return redirect("/teacher/class/")

    selected_course = None
    fixed_course = None
    class_resolution = get_user_single_class(request.user)
    if class_resolution.status == "none":
        messages.error(request, "Класс не назначен. Обратитесь к администратору.")
        return redirect("/assignments/")
    if class_resolution.status == "single":
        fixed_course = class_resolution.course
        selected_course = fixed_course
    else:
        course_id = request.GET.get("course") or request.POST.get("course")
        if course_id:
            try:
                selected_course = Course.objects.get(id=course_id, teacher=request.user)
            except Course.DoesNotExist:
                selected_course = None

    course_queryset = Course.objects.filter(id=fixed_course.id) if fixed_course else None
    initial_compositions = [""]
    composition_errors = []

    if request.method == "POST":
        initial_compositions = request.POST.getlist("composition_name") or [""]
        form = AssignmentCreateForm(
            request.POST,
            request.FILES,
            teacher_user=request.user,
            course_for_students=selected_course,
            course_queryset=course_queryset,
        )
        if form.is_valid():
            course = fixed_course or form.cleaned_data["course"]
            title = (form.cleaned_data.get("title") or "").strip()
            compositions = _collect_compositions(request.POST)
            titles = compositions or ([title] if title else [])
            description = form.cleaned_data.get("description", "")
            due_date = form.cleaned_data["due_date"]
            attachment = form.cleaned_data.get("attachment")
            student_ids = [int(x) for x in form.cleaned_data.get("students", [])]

            if not titles:
                composition_errors = ["Укажите название задания или добавьте хотя бы одну композицию."]
            else:
                composition_errors = _validate_homework_titles(titles)

            if not composition_errors:
                created_count = _create_assignments(
                    teacher=request.user,
                    course=course,
                    titles=titles,
                    description=description,
                    due_date=due_date,
                    attachment=attachment,
                    student_ids=student_ids,
                )
                messages.success(request, f"Создано заданий: {created_count}.")
                return redirect("/assignments/")
    else:
        form = AssignmentCreateForm(
            teacher_user=request.user,
            course_for_students=selected_course,
            course_queryset=course_queryset,
        )
        # If course selected via GET, prefill it in the form
        if selected_course:
            form.initial["course"] = selected_course

    return render(
        request,
        "homework/assignment_create.html",
        {
            "form": form,
            "selected_course": selected_course,
            "fixed_course": fixed_course,
            "initial_compositions": initial_compositions,
            "composition_errors": composition_errors,
        },
    )


@role_required(Profile.Role.TEACHER)
def assignment_create_for_student(request, student_id: int):
    student = get_teacher_student_or_404(request.user, student_id)
    course, status = resolve_teacher_course_for_student(request.user, student)
    if status == "none":
        messages.error(request, "Ученик не назначен на ваш курс.")
        return redirect(f"/teacher/students/{student.id}/")
    if status == "multiple":
        messages.error(request, "У ученика несколько ваших курсов. Уточните курс у администратора.")
        return redirect(f"/teacher/students/{student.id}/")

    selected_half_year = _normalize_half_year(request.GET.get("half_year") or request.POST.get("half_year") or "")
    carried_over_titles = _get_carried_over_compositions(student=student, course=course)
    plan_titles = _get_half_year_plan_titles(student=student, selected_half_year=selected_half_year)
    selected_plan_titles = []
    initial_compositions = carried_over_titles or [""]
    composition_errors = []

    if request.method == "POST":
        initial_compositions = request.POST.getlist("composition_name") or carried_over_titles or [""]
        selected_plan_titles = _filter_selected_plan_titles(request.POST.getlist("plan_compositions"), plan_titles)
        form = StudentAssignmentCreateForm(request.POST, request.FILES)
        if form.is_valid():
            title = (form.cleaned_data.get("title") or "").strip()
            compositions = _collect_compositions(request.POST)
            titles = _merge_unique_titles(compositions, selected_plan_titles) or ([title] if title else [])

            if not titles:
                composition_errors = ["Укажите название задания или добавьте хотя бы одну композицию."]
            else:
                composition_errors = _validate_homework_titles(titles)

            if not composition_errors:
                created_count = _create_assignments(
                    teacher=request.user,
                    course=course,
                    titles=titles,
                    description=form.cleaned_data.get("description", ""),
                    due_date=form.cleaned_data["due_date"],
                    attachment=form.cleaned_data.get("attachment"),
                    student_ids=[student.id],
                )
                messages.success(request, f"Создано заданий: {created_count}.")
                return redirect(f"/teacher/students/{student.id}/")
    else:
        form = StudentAssignmentCreateForm()

    return render(
        request,
        "homework/assignment_create_student.html",
        {
            "form": form,
            "student": student,
            "course": course,
            "initial_compositions": initial_compositions,
            "composition_errors": composition_errors,
            "carried_over_titles": carried_over_titles,
            "selected_half_year": selected_half_year,
            "half_year_options": [
                {
                    "value": HALF_YEAR_I,
                    "label": "I полугодие",
                    "url": _build_student_assignment_create_url(student.id, HALF_YEAR_I),
                    "active": selected_half_year == HALF_YEAR_I,
                },
                {
                    "value": HALF_YEAR_II,
                    "label": "II полугодие",
                    "url": _build_student_assignment_create_url(student.id, HALF_YEAR_II),
                    "active": selected_half_year == HALF_YEAR_II,
                },
            ],
            "plan_compositions": [
                {
                    "title": plan_title,
                    "checked": _normalize_title_key(plan_title) in {_normalize_title_key(value) for value in selected_plan_titles},
                }
                for plan_title in plan_titles
            ],
        },
    )


@require_POST
@role_required(Profile.Role.STUDENT)
def mark_done(request, target_id: int):
    """
    Student marks assigned homework as DONE.
    No grade auto-fill.
    """
    target = get_object_or_404(
        AssignmentTarget.objects.select_related("assignment", "assignment__course"),
        id=target_id,
        student=request.user,
    )
    target.status = AssignmentTarget.Status.DONE
    target.save()

    messages.success(request, "Отмечено как DONE (результат выставляется преподавателем отдельно).")
    return redirect("/assignments/")


@require_POST
@role_required(Profile.Role.STUDENT)
def submit_assignment(request, target_id: int):
    target = get_object_or_404(
        AssignmentTarget.objects.select_related("assignment", "assignment__course", "assignment__created_by"),
        id=target_id,
        student=request.user,
    )
    form = AssignmentSubmissionForm(request.POST, request.FILES)
    if not form.is_valid():
        for field_errors in form.errors.values():
            for error in field_errors:
                messages.error(request, error)
        return redirect("/assignments/")

    with transaction.atomic():
        target.student_comment = (form.cleaned_data.get("student_comment") or "").strip()
        target.status = AssignmentTarget.Status.DONE
        target.save(update_fields=["student_comment", "status", "updated_at"])
        _sync_submission_video(target=target, video_file=form.cleaned_data.get("video"))

    messages.success(request, "Ответ по заданию сохранён.")
    return redirect("/assignments/")
