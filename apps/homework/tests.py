import shutil
import tempfile
from datetime import date
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.accounts.models import LibraryVideo, Profile
from apps.gradebook.models import Assessment, Grade
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
        self.second_student = self._create_user("student_homework_two", Profile.Role.STUDENT)
        self.parent = self._create_user("parent_homework", Profile.Role.PARENT)
        self.course = Course.objects.create(name="Фортепиано 1", course_type=self.course_type, teacher=self.teacher)
        Enrollment.objects.create(course=self.course, student=self.student)
        Enrollment.objects.create(course=self.course, student=self.second_student)
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
            task_text="Старое задание не переносится",
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
        self.assertNotContains(response, "Старое задание не переносится")

        post_response = self.client.post(
            f"/teacher/students/{self.student.id}/assignments/create/",
            data={
                "due_date": "2026-04-20",
                "composition_name": ["Этюд №1", "Прелюдия До мажор"],
                "composition_task": ["Новый штрих", "Разобрать левую руку"],
                "plan_compositions": ["Прелюдия До мажор"],
                "plan_composition_task_0": "",
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
        task_by_title = dict(
            Assignment.objects.filter(course=self.course, due_date=date(2026, 4, 20)).values_list("title", "description")
        )
        self.assertEqual(task_by_title["Этюд №1"], "Новый штрих")
        self.assertEqual(task_by_title["Прелюдия До мажор"], "Разобрать левую руку")

        next_create = self.client.get(f"/teacher/students/{self.student.id}/assignments/create/")
        self.assertContains(next_create, 'value="Этюд №1"', html=False)
        self.assertNotContains(next_create, "Новый штрих")

    def test_homework_task_text_allows_100_characters_but_rejects_101(self):
        self.client.force_login(self.teacher)
        valid_task = "А" * 100
        too_long_task = "Б" * 101

        valid_response = self.client.post(
            f"/teacher/students/{self.student.id}/assignments/create/",
            data={
                "due_date": "2026-04-20",
                "composition_name": ["Этюд №2"],
                "composition_task": [valid_task],
                "half_year": "H1",
            },
        )

        self.assertEqual(valid_response.status_code, 302)
        self.assertTrue(Assignment.objects.filter(targets__student=self.student, description=valid_task).exists())

        invalid_response = self.client.post(
            f"/teacher/students/{self.student.id}/assignments/create/",
            data={
                "due_date": "2026-04-21",
                "composition_name": ["Этюд №3"],
                "composition_task": [too_long_task],
                "half_year": "H1",
            },
        )

        self.assertEqual(invalid_response.status_code, 200)
        self.assertContains(invalid_response, "Введите значение не длиннее 100 символов.")
        self.assertFalse(Assignment.objects.filter(title="Этюд №3").exists())

    def test_student_submission_saves_text_video_and_appears_in_library_and_teacher_results(self):
        assignment = create_assignment_with_targets_and_gradebook(
            teacher=self.teacher,
            course=self.course,
            title="Пьеса для зачёта",
            task_text="Записать исполнение",
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

    def test_teacher_can_view_edit_and_delete_student_homework_history(self):
        first = create_assignment_with_targets_and_gradebook(
            teacher=self.teacher,
            course=self.course,
            title="Этюд №1",
            task_text="Разобрать первую страницу",
            due_date=date(2026, 4, 10),
            attachment=None,
            student_ids=[self.student.id],
        )
        second = create_assignment_with_targets_and_gradebook(
            teacher=self.teacher,
            course=self.course,
            title="Сонатина",
            task_text="Повторить экспозицию",
            due_date=date(2026, 4, 17),
            attachment=None,
            student_ids=[self.student.id],
        )

        self.client.force_login(self.teacher)
        list_response = self.client.get(f"/teacher/students/{self.student.id}/assignments/")
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "Этюд №1")
        self.assertContains(list_response, "Разобрать первую страницу")
        self.assertContains(list_response, "Сонатина")

        edit_response = self.client.post(
            f"/teacher/students/{self.student.id}/assignments/{first.id}/edit/",
            data={
                "composition_name": "Этюд №2",
                "task_text": "Исправить аппликатуру",
                "due_date": "2026-04-12",
            },
        )
        self.assertEqual(edit_response.status_code, 302)
        first.refresh_from_db()
        self.assertEqual(first.title, "Этюд №2")
        self.assertEqual(first.description, "Исправить аппликатуру")
        self.assertEqual(first.due_date, date(2026, 4, 12))
        first.assessment.refresh_from_db()
        self.assertEqual(first.assessment.title, "Этюд №2")

        assessment_id = second.assessment.id
        delete_response = self.client.post(f"/teacher/students/{self.student.id}/assignments/{second.id}/delete/")
        self.assertEqual(delete_response.status_code, 302)
        self.assertFalse(Assignment.objects.filter(id=second.id).exists())
        self.assertFalse(Assessment.objects.filter(id=assessment_id).exists())

    def test_group_assignment_create_fans_out_targets_for_all_group_students(self):
        self.teacher.profile.teacher_mode = Profile.TeacherMode.GROUP
        self.teacher.profile.save(update_fields=["teacher_mode"])
        self.client.force_login(self.teacher)

        response = self.client.post(
            f"/teacher/groups/{self.course.id}/assignments/create/",
            data={
                "title": "Контрольная по ритму",
                "description": "Подготовить письменный разбор.",
                "due_date": "2026-04-30",
            },
        )

        self.assertEqual(response.status_code, 302)
        assignment = Assignment.objects.get(title="Контрольная по ритму")
        target_student_ids = set(AssignmentTarget.objects.filter(assignment=assignment).values_list("student_id", flat=True))
        self.assertEqual(target_student_ids, {self.student.id, self.second_student.id})
        grade_student_ids = set(Grade.objects.filter(assessment=assignment.assessment).values_list("student_id", flat=True))
        self.assertEqual(grade_student_ids, {self.student.id, self.second_student.id})
