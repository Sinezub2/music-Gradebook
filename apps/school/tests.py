from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Profile

from .models import Course, CourseType, Enrollment


class TeacherStudentWorkspaceTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.course_type = CourseType.objects.create(name="Фортепиано")
        self.teacher = self._create_user("teacher_workspace", Profile.Role.TEACHER)
        self.student = self._create_user("student_workspace", Profile.Role.STUDENT, cycle=Profile.Cycle.GENERAL)
        self.course = Course.objects.create(name="Фортепиано 1", course_type=self.course_type, teacher=self.teacher)
        Enrollment.objects.create(course=self.course, student=self.student)

    def _create_user(self, username: str, role: str, cycle: str = Profile.Cycle.GENERAL):
        user = self.user_model.objects.create_user(
            username=username,
            password="pass12345",
            first_name=username,
            last_name="User",
        )
        Profile.objects.create(user=user, role=role, cycle=cycle)
        return user

    def test_individual_teacher_still_uses_existing_class_list(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse("teacher_class_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Мои занятия")
        self.assertContains(response, "Открыть карточку")

    def test_teacher_can_change_student_cycle_from_workspace(self):
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse("teacher_student_workspace", args=[self.student.id]),
            data={"cycle": Profile.Cycle.ACCELERATED},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.student.profile.refresh_from_db()
        self.assertEqual(self.student.profile.cycle, Profile.Cycle.ACCELERATED)

    def test_workspace_does_not_show_redundant_goal_create_button(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse("teacher_student_workspace", args=[self.student.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Полугодовой план")
        self.assertNotContains(response, "Добавить в полугодовой план")


class TeacherGroupFlowTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.course_type = CourseType.objects.create(name="Сольфеджио")
        self.group_teacher = self._create_user(
            "teacher_group",
            Profile.Role.TEACHER,
            teacher_mode=Profile.TeacherMode.GROUP,
        )
        self.student = self._create_user("student_group", Profile.Role.STUDENT)
        self.group = Course.objects.create(name="Теория 5А", course_type=self.course_type, teacher=self.group_teacher)
        Enrollment.objects.create(course=self.group, student=self.student)

    def _create_user(
        self,
        username: str,
        role: str,
        cycle: str = Profile.Cycle.GENERAL,
        teacher_mode: str = Profile.TeacherMode.INDIVIDUAL,
    ):
        user = self.user_model.objects.create_user(
            username=username,
            password="pass12345",
            first_name=username,
            last_name="User",
        )
        Profile.objects.create(user=user, role=role, cycle=cycle, teacher_mode=teacher_mode)
        return user

    def test_group_teacher_old_class_url_redirects_to_group_list(self):
        self.client.force_login(self.group_teacher)

        response = self.client.get(reverse("teacher_class_list"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/teacher/groups/")

    def test_group_teacher_can_open_group_pages(self):
        self.client.force_login(self.group_teacher)

        list_response = self.client.get(reverse("teacher_group_list"))
        detail_response = self.client.get(reverse("teacher_group_detail", args=[self.group.id]))

        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "Мои группы")
        self.assertContains(list_response, self.group.name)
        self.assertContains(list_response, "Группы")
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "План / темы")
        self.assertContains(detail_response, self.student.get_full_name())
