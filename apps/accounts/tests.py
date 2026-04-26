import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.school.models import Course, CourseType, Enrollment, ParentChild

from .models import ActivationCode, LibraryVideo, Profile


class RegistrationAndActivationCodeTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.course_type = CourseType.objects.create(name="Фортепиано")
        self.teacher = self._create_user("teacher_codes", Profile.Role.TEACHER)
        self.student = self._create_user("student_codes", Profile.Role.STUDENT)
        self.parent = self._create_user("parent_codes", Profile.Role.PARENT)
        self.child = self._create_user("child_codes", Profile.Role.STUDENT)
        self.course_a = Course.objects.create(name="Фортепиано A", course_type=self.course_type, teacher=self.teacher)
        self.course_b = Course.objects.create(name="Фортепиано B", course_type=self.course_type, teacher=self.teacher)
        Enrollment.objects.create(course=self.course_a, student=self.student)
        Enrollment.objects.create(course=self.course_a, student=self.child)

    def _create_user(self, username: str, role: str):
        user = self.user_model.objects.create_user(
            username=username,
            password="pass12345",
            first_name=username,
            last_name="User",
        )
        Profile.objects.create(user=user, role=role)
        return user

    def test_teacher_registration_creates_profile_and_logs_in(self):
        response = self.client.post(
            "/register/",
            data={
                "username": "new_teacher",
                "first_name": "New",
                "last_name": "Teacher",
                "role": Profile.Role.TEACHER,
                "password1": "ComplexPass123",
                "password2": "ComplexPass123",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard")
        user = self.user_model.objects.get(username="new_teacher")
        self.assertEqual(user.first_name, "New")
        self.assertEqual(user.last_name, "Teacher")
        self.assertEqual(user.profile.role, Profile.Role.TEACHER)

        dashboard_response = self.client.get("/dashboard")
        self.assertEqual(dashboard_response.status_code, 200)

    def test_student_registration_redirects_to_add_course(self):
        response = self.client.post(
            "/register/",
            data={
                "username": "new_student",
                "first_name": "New",
                "last_name": "Student",
                "role": Profile.Role.STUDENT,
                "password1": "ComplexPass123",
                "password2": "ComplexPass123",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/profile/add-course/")
        user = self.user_model.objects.get(username="new_student")
        self.assertEqual(user.profile.role, Profile.Role.STUDENT)

    def test_teacher_can_create_student_activation_code(self):
        self.client.force_login(self.teacher)

        response = self.client.post(
            "/teacher/invite-code/create/",
            data={
                "target_role": ActivationCode.TargetRole.STUDENT,
                "course": str(self.course_a.id),
                "cycle": Profile.Cycle.BASIC,
            },
        )

        self.assertEqual(response.status_code, 200)
        code = ActivationCode.objects.get(course=self.course_a, target_role=ActivationCode.TargetRole.STUDENT)
        self.assertTrue(code.code.startswith("MUSIC-"))
        self.assertEqual(code.cycle, Profile.Cycle.BASIC)
        self.assertContains(response, code.code)

    def test_student_can_apply_code_and_dashboard_shows_multiple_courses(self):
        code = ActivationCode.objects.create(
            code="MUSIC-AB12CD",
            created_by_teacher=self.teacher,
            target_role=ActivationCode.TargetRole.STUDENT,
            course=self.course_b,
            cycle=Profile.Cycle.ACCELERATED,
        )
        self.client.force_login(self.student)

        response = self.client.post("/profile/add-course/", data={"code": code.code}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Enrollment.objects.filter(course=self.course_b, student=self.student).exists())
        self.student.profile.refresh_from_db()
        self.assertEqual(self.student.profile.cycle, Profile.Cycle.ACCELERATED)
        code.refresh_from_db()
        self.assertTrue(code.is_used)
        self.assertEqual(code.used_by_id, self.student.id)
        self.assertContains(response, "Фортепиано A")
        self.assertContains(response, "Фортепиано B")

    def test_parent_can_apply_code_and_link_child(self):
        code = ActivationCode.objects.create(
            code="MUSIC-PA12NT",
            created_by_teacher=self.teacher,
            target_role=ActivationCode.TargetRole.PARENT,
            course=self.course_a,
            target_student=self.child,
        )
        self.client.force_login(self.parent)

        response = self.client.post("/profile/add-course/", data={"code": code.code})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard")
        self.assertTrue(ParentChild.objects.filter(parent=self.parent, child=self.child).exists())
        code.refresh_from_db()
        self.assertTrue(code.is_used)
        self.assertEqual(code.used_by_id, self.parent.id)

    def test_old_invite_routes_are_not_available(self):
        self.client.force_login(self.teacher)

        teacher_invite_response = self.client.get("/teacher/students/invite/")
        register_invite_response = self.client.get("/register/invite/some-token/")

        self.assertEqual(teacher_invite_response.status_code, 404)
        self.assertEqual(register_invite_response.status_code, 404)


class LibraryAndStudentProfileTests(TestCase):
    def setUp(self):
        self.media_root_base = Path(__file__).resolve().parents[2] / "tmp_test_media"
        self.media_root_base.mkdir(exist_ok=True)
        self.media_root = tempfile.mkdtemp(dir=self.media_root_base)
        self.addCleanup(lambda: shutil.rmtree(self.media_root, ignore_errors=True))
        self.user_model = get_user_model()
        self.course_type = CourseType.objects.create(name="Скрипка")
        self.teacher = self._create_user("teacher_library", Profile.Role.TEACHER)
        self.student = self._create_user("student_library", Profile.Role.STUDENT)
        self.parent = self._create_user("parent_library", Profile.Role.PARENT)
        self.second_child = self._create_user("student_second", Profile.Role.STUDENT)
        self.course = Course.objects.create(name="Скрипка 1", course_type=self.course_type, teacher=self.teacher)
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

    def test_teacher_can_upload_library_video_and_student_parent_can_view_it(self):
        with self.settings(
            MEDIA_ROOT=self.media_root,
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
                "staticfiles": settings.STORAGES["staticfiles"],
            },
        ):
            self.client.force_login(self.teacher)
            upload = SimpleUploadedFile("practice.mp4", b"video-bytes", content_type="video/mp4")
            response = self.client.post(
                f"/library/?student={self.student.id}&upload=1",
                data={
                    "title": "Домашнее видео",
                    "video": upload,
                    "upload_video": "1",
                },
            )

            self.assertEqual(response.status_code, 302)
            self.assertEqual(LibraryVideo.objects.count(), 1)

            self.client.force_login(self.student)
            student_library = self.client.get("/library/")
            self.assertContains(student_library, "Домашнее видео")
            self.assertContains(student_library, "<video", html=False)
            self.assertNotContains(student_library, "Загрузить видео")

            self.client.force_login(self.parent)
            parent_library = self.client.get(f"/library/?student={self.student.id}")
            self.assertContains(parent_library, "Домашнее видео")
            self.assertNotContains(parent_library, "Загрузить видео")

    def test_teacher_upload_form_is_student_based_without_course_field(self):
        self.client.force_login(self.teacher)
        response = self.client.get(f"/library/?student={self.student.id}&upload=1")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Курс")
        self.assertContains(response, "Родитель: parent_library User")
        self.assertContains(response, "Видео будет доступно только выбранному ученику, его родителю и вам.")

    def test_uploaded_library_video_file_is_served_with_debug_disabled_when_media_serving_enabled(self):
        with self.settings(
            DEBUG=False,
            SERVE_MEDIA=True,
            MEDIA_ROOT=self.media_root,
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": settings.STORAGES["staticfiles"],
            },
        ):
            self.client.force_login(self.teacher)
            upload = SimpleUploadedFile("practice.mp4", b"video-bytes", content_type="video/mp4")
            response = self.client.post(
                f"/library/?student={self.student.id}&upload=1",
                data={
                    "title": "Проверка доступа",
                    "video": upload,
                    "upload_video": "1",
                },
            )

            self.assertEqual(response.status_code, 302)
            saved_video = LibraryVideo.objects.get()
            self.assertTrue(Path(saved_video.video.path).exists())

            media_response = self.client.get(saved_video.video.url)
            self.assertEqual(media_response.status_code, 200)
            self.assertEqual(b"".join(media_response.streaming_content), b"video-bytes")

    def test_student_can_update_school_details_and_teacher_sees_them(self):
        self.client.force_login(self.student)
        response = self.client.post(
            "/profile/student-details/",
            data={
                "school_grade": "7Б",
                "class_curator_phone": "+7 777 123 45 67",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.student.profile.refresh_from_db()
        self.assertEqual(self.student.profile.school_grade, "7Б")
        self.assertEqual(self.student.profile.class_curator_phone, "+7 777 123 45 67")

        self.client.force_login(self.teacher)
        class_list_response = self.client.get("/teacher/class/")
        self.assertContains(class_list_response, "Класс: 7Б")
        self.assertContains(class_list_response, "Номер классного руководителя: +7 777 123 45 67")

        workspace_response = self.client.get(f"/teacher/students/{self.student.id}/")
        self.assertContains(workspace_response, "Класс: 7Б")
        self.assertContains(workspace_response, "Номер классного руководителя: +7 777 123 45 67")

    def test_parent_profile_shows_child_link_form(self):
        self.client.force_login(self.parent)

        response = self.client.get("/profile/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Подключить ребёнка")
        self.assertContains(response, "Логин ребёнка")
        self.assertContains(response, "Пароль ребёнка")

    def test_parent_can_link_second_child_from_profile_using_student_credentials(self):
        self.client.force_login(self.parent)

        response = self.client.post(
            "/profile/add-child/",
            data={
                "child_username": self.second_child.username,
                "child_password": "pass12345",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(ParentChild.objects.filter(parent=self.parent, child=self.second_child).exists())
        self.assertContains(response, "student_second User")
