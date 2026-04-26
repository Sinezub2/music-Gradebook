from datetime import date

from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Profile
from apps.homework.services import create_assignment_with_targets_and_gradebook
from apps.school.models import Course, CourseType, Enrollment

from .models import Grade


class TeacherGroupGradesTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.course_type = CourseType.objects.create(name="Теория")
        self.teacher = self._create_user(
            "teacher_group_grades",
            Profile.Role.TEACHER,
            teacher_mode=Profile.TeacherMode.GROUP,
        )
        self.student = self._create_user("group_grade_student", Profile.Role.STUDENT)
        self.group = Course.objects.create(name="Теория 4", course_type=self.course_type, teacher=self.teacher)
        Enrollment.objects.create(course=self.group, student=self.student)
        self.assignment = create_assignment_with_targets_and_gradebook(
            teacher=self.teacher,
            course=self.group,
            title="Тест по нотам",
            task_text="Письменная работа",
            due_date=date(2026, 4, 28),
            attachment=None,
            student_ids=[self.student.id],
        )

    def _create_user(self, username: str, role: str, teacher_mode: str = Profile.TeacherMode.INDIVIDUAL):
        user = self.user_model.objects.create_user(
            username=username,
            password="pass12345",
            first_name=username,
            last_name="User",
        )
        Profile.objects.create(user=user, role=role, teacher_mode=teacher_mode)
        return user

    def test_group_teacher_can_view_and_update_group_grades_page(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse("teacher_group_grades", args=[self.group.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Тест по нотам")

        assessment = self.assignment.assessment
        post_response = self.client.post(
            reverse("teacher_group_grades", args=[self.group.id]),
            data={
                f"grade-{self.student.id}-{assessment.id}": "88",
                f"comment-{self.student.id}-{assessment.id}": "Хорошо",
            },
        )

        self.assertEqual(post_response.status_code, 302)
        grade = Grade.objects.get(assessment=assessment, student=self.student)
        self.assertEqual(float(grade.score), 88.0)
        self.assertEqual(grade.comment, "Хорошо")


class SeedDemoCommandTests(TestCase):
    def test_seed_demo_sets_teacher_mode_and_group_ready_data(self):
        call_command("seed_demo")

        teacher = get_user_model().objects.get(username="teacher1")
        theory_course = Course.objects.get(name="Теория музыки")
        student_two = get_user_model().objects.get(username="student2")

        self.assertEqual(teacher.profile.teacher_mode, Profile.TeacherMode.BOTH)
        self.assertTrue(Enrollment.objects.filter(course=theory_course, student=student_two).exists())
