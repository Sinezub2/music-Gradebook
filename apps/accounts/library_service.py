from __future__ import annotations

import mimetypes
from pathlib import Path

from django.db.models import Q

from apps.homework.models import AssignmentTarget
from apps.lessons.models import LessonReport, LessonStudent


CATEGORY_SHEET = "Ноты/табы"
CATEGORY_VIDEO = "Видео"
CATEGORY_AUDIO = "Аудио"
CATEGORY_DOCUMENT = "Документы"
CATEGORY_PHOTO = "Фото"

LIBRARY_CATEGORIES = [
    CATEGORY_SHEET,
    CATEGORY_VIDEO,
    CATEGORY_AUDIO,
    CATEGORY_DOCUMENT,
    CATEGORY_PHOTO,
]

_SHEET_EXTENSIONS = {
    ".gp",
    ".gp3",
    ".gp4",
    ".gp5",
    ".gpx",
    ".ptb",
    ".mscz",
    ".mscx",
    ".mxl",
    ".musicxml",
    ".xml",
}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac"}
_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic"}
_DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".txt",
    ".rtf",
    ".odt",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
}


def _display_name(user) -> str:
    return (user.get_full_name() or "").strip() or user.username or "Без имени"


def categorize_library_item(raw_name: str, mime_type: str = "") -> str:
    filename = (raw_name or "").lower()
    extension = Path(filename).suffix
    guessed_mime = mime_type or mimetypes.guess_type(filename)[0] or ""
    guessed_mime = guessed_mime.lower()

    if extension in _SHEET_EXTENSIONS or any(token in filename for token in ("таб", "tabs", "tab", "нот", "sheet")):
        return CATEGORY_SHEET
    if extension in _VIDEO_EXTENSIONS or guessed_mime.startswith("video/"):
        return CATEGORY_VIDEO
    if extension in _AUDIO_EXTENSIONS or guessed_mime.startswith("audio/"):
        return CATEGORY_AUDIO
    if extension in _PHOTO_EXTENSIONS or guessed_mime.startswith("image/"):
        return CATEGORY_PHOTO
    if extension in _DOCUMENT_EXTENSIONS or guessed_mime in {"application/pdf", "application/msword"}:
        return CATEGORY_DOCUMENT
    return CATEGORY_DOCUMENT


def build_library_items_for_student(student, *, teacher=None) -> list[dict]:
    items = []
    seen = set()

    assignment_targets = (
        AssignmentTarget.objects.filter(student=student)
        .select_related("assignment", "assignment__course", "assignment__created_by")
        .exclude(assignment__attachment="")
        .order_by("-assignment__created_at")
    )
    if teacher is not None:
        assignment_targets = assignment_targets.filter(assignment__course__teacher=teacher)

    for target in assignment_targets:
        assignment = target.assignment
        if not assignment.attachment:
            continue
        url = assignment.attachment.url
        dedupe_key = ("assignment", assignment.id, url)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        raw_name = assignment.attachment.name or assignment.title
        items.append(
            {
                "title": assignment.title,
                "category": categorize_library_item(raw_name),
                "source": "Домашнее задание",
                "course_name": assignment.course.name,
                "uploaded_by": _display_name(assignment.created_by),
                "created_at": assignment.created_at,
                "date_label": assignment.created_at.strftime("%d.%m.%Y"),
                "url": url,
                "is_external": False,
            }
        )

    lesson_entries = (
        LessonStudent.objects.filter(student=student)
        .select_related("lesson", "lesson__course", "lesson__created_by")
        .exclude(lesson__attachment="")
        .order_by("-lesson__date", "-lesson_id")
    )
    if teacher is not None:
        lesson_entries = lesson_entries.filter(lesson__course__teacher=teacher)

    for entry in lesson_entries:
        lesson = entry.lesson
        if not lesson.attachment:
            continue
        url = lesson.attachment.url
        dedupe_key = ("lesson", lesson.id, url)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        raw_name = lesson.attachment.name or lesson.topic
        items.append(
            {
                "title": lesson.topic or f"Урок {lesson.date:%d.%m.%Y}",
                "category": categorize_library_item(raw_name),
                "source": "Урок",
                "course_name": lesson.course.name,
                "uploaded_by": _display_name(lesson.created_by),
                "created_at": lesson.date,
                "date_label": lesson.date.strftime("%d.%m.%Y"),
                "url": url,
                "is_external": False,
            }
        )

    report_qs = (
        LessonReport.objects.filter(lesson__student_entries__student=student)
        .filter(Q(student=student) | Q(student__isnull=True))
        .exclude(media_url="")
        .select_related("lesson", "lesson__course", "lesson__created_by")
        .distinct()
        .order_by("-created_at")
    )
    if teacher is not None:
        report_qs = report_qs.filter(lesson__course__teacher=teacher)

    for report in report_qs:
        url = (report.media_url or "").strip()
        if not url:
            continue
        dedupe_key = ("report", report.id, url)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        items.append(
            {
                "title": report.lesson.topic or f"Урок {report.lesson.date:%d.%m.%Y}",
                "category": categorize_library_item(url),
                "source": "Отчёт урока",
                "course_name": report.lesson.course.name,
                "uploaded_by": _display_name(report.lesson.created_by),
                "created_at": report.created_at,
                "date_label": report.created_at.strftime("%d.%m.%Y"),
                "url": url,
                "is_external": True,
            }
        )

    items.sort(key=lambda row: row["created_at"], reverse=True)
    return items
