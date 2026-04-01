import shutil
import tempfile
from datetime import date
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.accounts.models import LibraryVideo, Profile
from apps.goals.models import Goal
from apps.school.models import Course, CourseType, Enrollment, ParentChild

from .models import Assignment, AssignmentTarget
from .services import create_assignment_with_targets_and_gradebook


class HomeworkFlowTests(TestCase):
    def setUp(self):
        self.media_root_base = Path(__file__).resolve().parents[2] / "tmp_test_media"
        self.media_root_base.mkdir(exist_ok=True)
        self.media_root = tempfile.mkdtemp(dir=self.media_root_base)
        self.addCleanup(lambda: shutil.rmtree(self.media_root, ignore_errors=True))

        self.user_model = get_user_model()
        self.course_type = CourseType.objects.create(name="Фортепиано")
        self.teacher = self._create_user("teacher_homework", Profile.Role.TEACHER)
        self.student = self._create_user("student_homework", Profile.Role.STUDENT)
        self.parent = self._create_user("parent_homework", Profile.Role.PARENT)
        self.course = Course.objects.create(name="Фортепиано 1", course_type=self.course_type, teacher=self.teacher)
        Enrollment.objects.create(course=self.course, student=self.student)
        ParentChild.objects.create(parent=self.parent, child=self.student)

    def _create_user(self, username: str, role: str):
        user = self.user_model.objects.create_user(
            username=username,
            password="pass12345",
            first_name=username,
            last_name="User",
        )
        Profile.objects.create(user=user, role=role)
        return user

    def test_student_homework_create_prefills_active_titles_and_deduplicates_half_year_plan_titles(self):
        create_assignment_with_targets_and_gradebook(
            teacher=self.teacher,
            course=self.course,
            title="Этюд №1",
            description="",
            due_date=date(2026, 4, 10),
            attachment=None,
            student_ids=[self.student.id],
        )
        Goal.objects.create(student=self.student, teacher=self.teacher, month=date(2026, 1, 1), title="Прелюдия До мажор")

        self.client.force_login(self.teacher)
        response = self.client.get(f"/teacher/students/{self.student.id}/assignments/create/?half_year=H1")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Этюд №1"', html=False)
        self.assertContains(response, "Прелюдия До мажор")

        post_response = self.client.post(
            f"/teacher/students/{self.student.id}/assignments/create/",
            data={
                "title": "",
                "description": "Повторить программу",
                "due_date": "2026-04-20",
                "composition_name": ["Этюд №1", "Прелюдия До мажор"],
                "plan_compositions": ["Прелюдия До мажор"],
                "half_year": "H1",
            },
        )

        self.assertEqual(post_response.status_code, 302)
        created_titles = list(
            Assignment.objects.filter(course=self.course, due_date=date(2026, 4, 20))
            .order_by("title")
            .values_list("title", flat=True)
        )
        self.assertEqual(created_titles, ["Прелюдия До мажор", "Этюд №1"])

    def test_student_submission_saves_text_video_and_appears_in_library_and_teacher_results(self):
        assignment = create_assignment_with_targets_and_gradebook(
            teacher=self.teacher,
            course=self.course,
            title="Пьеса для зачёта",
            description="",
            due_date=date(2026, 4, 10),
            attachment=None,
            student_ids=[self.student.id],
        )
        target = AssignmentTarget.objects.get(assignment=assignment, student=self.student)

        with self.settings(
            MEDIA_ROOT=self.media_root,
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
                "staticfiles": settings.STORAGES["staticfiles"],
            },
        ):
            self.client.force_login(self.student)
            upload = SimpleUploadedFile("submission.mp4", b"video-bytes", content_type="video/mp4")
            response = self.client.post(
                f"/assignments/targets/{target.id}/submit/",
                data={
                    "student_comment": "Готово, записал обе части.",
                    "video": upload,
                },
            )

            self.assertEqual(response.status_code, 302)
            target.refresh_from_db()
            self.assertEqual(target.status, AssignmentTarget.Status.DONE)
            self.assertEqual(target.student_comment, "Готово, записал обе части.")

            library_video = LibraryVideo.objects.get(assignment_target=target)
            self.assertEqual(library_video.student_id, self.student.id)
            self.assertEqual(library_video.course_id, self.course.id)

            student_library = self.client.get("/library/")
            self.assertContains(student_library, "Домашнее задание / Ответ ученика")
            self.assertContains(student_library, "Пьеса для зачёта")

            self.client.force_login(self.parent)
            parent_library = self.client.get(f"/library/?student={self.student.id}")
            self.assertContains(parent_library, "Домашнее задание / Ответ ученика")

            self.client.force_login(self.teacher)
            teacher_results = self.client.get(f"/teacher/students/{self.student.id}/results/")
            self.assertContains(teacher_results, "Готово, записал обе части.")
            self.assertContains(teacher_results, "Видео ответа")
