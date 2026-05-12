from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Profile
from apps.gradebook.models import Assessment, Grade
from apps.lessons.models import Lesson
from apps.schedule.models import Event

from .models import Course, CourseInternalGroup, CourseType, Enrollment


class TeacherStudentWorkspaceTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.course_type = CourseType.objects.create(name="Фортепиано")
        self.teacher = self._create_user("teacher_workspace", Profile.Role.TEACHER)
        self.student = self._create_user("student_workspace", Profile.Role.STUDENT, cycle=Profile.Cycle.GENERAL)
        self.student.profile.school_grade = "4Б"
        self.student.profile.save(update_fields=["school_grade"])
        self.course = Course.objects.create(name="Фортепиано 1", course_type=self.course_type, teacher=self.teacher)
        Enrollment.objects.create(course=self.course, student=self.student)
        self.group_teacher = self._create_user(
            "teacher_group_shared",
            Profile.Role.TEACHER,
            teacher_mode=Profile.TeacherMode.GROUP,
        )
        self.group_course_type = CourseType.objects.create(name="Сольфеджио")
        self.group_course = Course.objects.create(
            name="Сольфеджио 4Б",
            course_type=self.group_course_type,
            teacher=self.group_teacher,
        )
        Enrollment.objects.create(course=self.group_course, student=self.student)

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

    def test_workspace_shows_other_group_course_context(self):
        Lesson.objects.create(
            course=self.group_course,
            date=timezone.localdate(),
            topic="Лад и интервалы",
            created_by=self.group_teacher,
        )
        assessment = Assessment.objects.create(
            course=self.group_course,
            title="Диагностика",
            assessment_type=Assessment.AssessmentType.THEORY_TEST,
        )
        Grade.objects.create(assessment=assessment, student=self.student, score=91)
        Event.objects.create(
            title="Контрольная четверти",
            event_type=Event.EventType.CONTROL,
            start_datetime=timezone.now() + timedelta(days=2),
            end_datetime=timezone.now() + timedelta(days=2, hours=1),
            description="Проверка по теории.",
            course=self.group_course,
            created_by=self.group_teacher,
        )

        self.client.force_login(self.teacher)
        response = self.client.get(reverse("teacher_student_workspace", args=[self.student.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Общий учебный контекст")
        self.assertContains(response, "Сольфеджио 4Б")
        self.assertContains(response, "Лад и интервалы")
        self.assertContains(response, "Диагностика")
        self.assertContains(response, "Контрольная четверти")


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

    def test_group_detail_derives_classrooms_and_can_create_internal_group(self):
        self.student.profile.school_grade = "5А"
        self.student.profile.save(update_fields=["school_grade"])
        student_two = self._create_user("student_group_two", Profile.Role.STUDENT)
        student_two.profile.school_grade = "5Б"
        student_two.profile.save(update_fields=["school_grade"])
        Enrollment.objects.create(course=self.group, student=student_two)

        self.client.force_login(self.group_teacher)
        detail_response = self.client.get(reverse("teacher_group_detail", args=[self.group.id]))
        self.assertContains(detail_response, "5А")
        self.assertContains(detail_response, "5Б")

        create_response = self.client.post(
            reverse("teacher_group_detail", args=[self.group.id]),
            data={
                "action": "create_internal_group",
                "group_type": CourseInternalGroup.GroupType.REMEDIAL,
                "name": "",
                "students": [str(self.student.id)],
            },
        )

        self.assertEqual(create_response.status_code, 302)
        internal_group = CourseInternalGroup.objects.get(course=self.group)
        self.assertEqual(internal_group.name, "Нужна поддержка")
        self.assertEqual(set(internal_group.students.values_list("id", flat=True)), {self.student.id})
