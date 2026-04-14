from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Profile
from apps.school.models import Course, CourseType, Enrollment

from .models import Goal


class GoalManagementTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.course_type = CourseType.objects.create(name="Фортепиано")
        self.teacher = self._create_user("teacher_goals", Profile.Role.TEACHER)
        self.other_teacher = self._create_user("teacher_goals_other", Profile.Role.TEACHER)
        self.student = self._create_user("student_goals", Profile.Role.STUDENT)
        self.course = Course.objects.create(name="Фортепиано 1", course_type=self.course_type, teacher=self.teacher)
        Enrollment.objects.create(course=self.course, student=self.student)

    def _create_user(self, username: str, role: str):
        user = self.user_model.objects.create_user(
            username=username,
            password="pass12345",
            first_name=username,
            last_name="User",
        )
        Profile.objects.create(user=user, role=role)
        return user

    def test_goal_list_shows_edit_link_and_delete_mode_for_teacher(self):
        Goal.objects.create(student=self.student, teacher=self.teacher, month=date(2026, 1, 1), title="Гамма До мажор")

        self.client.force_login(self.teacher)
        response = self.client.get(reverse("goal_list"), {"student": self.student.id, "half_year": "H1"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Изменить")
        self.assertContains(response, "Режим удаления")
        self.assertContains(response, 'action="/goals/bulk-delete/"', html=False)

    def test_teacher_can_edit_goal_title_and_half_year_without_losing_status(self):
        goal = Goal.objects.create(
            student=self.student,
            teacher=self.teacher,
            month=date(2026, 1, 1),
            title="Старая цель",
            details="__status__:DONE\nКомментарий",
        )

        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse("goal_edit", args=[goal.id]),
            data={
                "student": str(self.student.id),
                "half_year": "H2",
                "title": "Новая цель",
            },
        )

        self.assertRedirects(
            response,
            f"/goals/?student={self.student.id}&half_year=H2",
            fetch_redirect_response=False,
        )
        goal.refresh_from_db()
        self.assertEqual(goal.title, "Новая цель")
        self.assertEqual(goal.month, date(2026, 7, 1))
        self.assertEqual(goal.details, "__status__:DONE\nКомментарий")

    def test_teacher_can_bulk_delete_goal_from_goal_list(self):
        goal = Goal.objects.create(student=self.student, teacher=self.teacher, month=date(2026, 1, 1), title="Этюд")

        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse("goal_bulk_delete"),
            data={
                "selected_ids": [str(goal.id)],
                "student": str(self.student.id),
                "half_year": "H1",
            },
        )

        self.assertRedirects(
            response,
            f"/goals/?student={self.student.id}&half_year=H1",
            fetch_redirect_response=False,
        )
        self.assertFalse(Goal.objects.filter(id=goal.id).exists())

    def test_other_teacher_cannot_edit_or_delete_goal(self):
        goal = Goal.objects.create(student=self.student, teacher=self.teacher, month=date(2026, 1, 1), title="Пьеса")

        self.client.force_login(self.other_teacher)

        edit_response = self.client.get(reverse("goal_edit", args=[goal.id]))
        self.assertEqual(edit_response.status_code, 403)

        delete_response = self.client.post(reverse("goal_bulk_delete"), data={"selected_ids": [str(goal.id)]})
        self.assertEqual(delete_response.status_code, 403)
        self.assertTrue(Goal.objects.filter(id=goal.id).exists())
