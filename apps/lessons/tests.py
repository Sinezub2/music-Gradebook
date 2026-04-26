from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Profile
from apps.school.models import Course, CourseType, Enrollment

from .models import Lesson, LessonStudent


class GroupAttendanceTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.course_type = CourseType.objects.create(name="Сольфеджио")
        self.teacher = self._create_user(
            "teacher_attendance_group",
            Profile.Role.TEACHER,
            teacher_mode=Profile.TeacherMode.GROUP,
        )
        self.student_a = self._create_user("attendance_student_a", Profile.Role.STUDENT)
        self.student_b = self._create_user("attendance_student_b", Profile.Role.STUDENT)
        self.group = Course.objects.create(name="Сольфеджио 3", course_type=self.course_type, teacher=self.teacher)
        Enrollment.objects.create(course=self.group, student=self.student_a)
        Enrollment.objects.create(course=self.group, student=self.student_b)

    def _create_user(self, username: str, role: str, teacher_mode: str = Profile.TeacherMode.INDIVIDUAL):
        user = self.user_model.objects.create_user(
            username=username,
            password="pass12345",
            first_name=username,
            last_name="User",
        )
        Profile.objects.create(user=user, role=role, teacher_mode=teacher_mode)
        return user

    def test_group_attendance_creates_lesson_and_per_student_rows(self):
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse("teacher_group_attendance", args=[self.group.id]),
            data={
                "date": "2026-04-21",
                "topic": "Интервалы и диктант",
                f"attendance-{self.student_a.id}": "PRESENT",
                f"attendance-{self.student_b.id}": "ABSENT",
            },
        )

        self.assertEqual(response.status_code, 302)
        lesson = Lesson.objects.get(course=self.group, topic="Интервалы и диктант")
        entries = {
            entry.student_id: entry.attended
            for entry in LessonStudent.objects.filter(lesson=lesson)
        }
        self.assertEqual(entries, {self.student_a.id: True, self.student_b.id: False})
