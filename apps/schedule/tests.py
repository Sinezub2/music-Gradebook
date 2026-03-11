from datetime import datetime, time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Profile
from apps.school.models import Course, CourseType, Enrollment

from .models import Event


class TeacherEventCreateTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.teacher = self._create_user("teacher_events", Profile.Role.TEACHER)
        self.teacher_other = self._create_user("teacher_other", Profile.Role.TEACHER)
        self.student_a = self._create_user("student_a", Profile.Role.STUDENT)
        self.student_b = self._create_user("student_b", Profile.Role.STUDENT)
        self.student_other = self._create_user("student_other", Profile.Role.STUDENT)
        self.parent = self._create_user("parent_events", Profile.Role.PARENT)
        self.admin = self._create_user("admin_events", Profile.Role.ADMIN)

        course_type = CourseType.objects.create(name="Фортепиано")
        self.course = Course.objects.create(name="Курс преподавателя", course_type=course_type, teacher=self.teacher)
        self.course_other = Course.objects.create(
            name="Чужой курс",
            course_type=course_type,
            teacher=self.teacher_other,
        )

        Enrollment.objects.create(course=self.course, student=self.student_a)
        Enrollment.objects.create(course=self.course, student=self.student_b)
        Enrollment.objects.create(course=self.course_other, student=self.student_other)

    def _create_user(self, username: str, role: str):
        user = self.user_model.objects.create_user(username=username, password="pass12345")
        Profile.objects.create(user=user, role=role)
        return user

    def _today_payload_base(self, **extra):
        data = {
            "event_type": Event.EventType.EXAM,
            "event_date": timezone.localdate().isoformat(),
            "title": "Контрольный концерт",
            "description": "Проверка программы.",
            "external_url": "",
        }
        data.update(extra)
        return data

    def _event_start(self):
        local_tz = timezone.get_current_timezone()
        return timezone.make_aware(datetime.combine(timezone.localdate(), time(hour=9, minute=0)), local_tz)

    def _event_end(self):
        local_tz = timezone.get_current_timezone()
        return timezone.make_aware(datetime.combine(timezone.localdate(), time(hour=10, minute=0)), local_tz)

    def test_teacher_can_open_event_create_page(self):
        self.client.force_login(self.teacher)
        response = self.client.get("/calendar/create/")
        self.assertEqual(response.status_code, 200)

    def test_non_teachers_cannot_open_event_create_page(self):
        for user in (self.student_a, self.parent, self.admin):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get("/calendar/create/")
                self.assertEqual(response.status_code, 403)

    def test_teacher_creates_event_for_whole_course(self):
        self.client.force_login(self.teacher)
        payload = self._today_payload_base(course=str(self.course.id))

        response = self.client.post("/calendar/create/", data=payload)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/calendar/")

        event = Event.objects.get(title="Контрольный концерт")
        self.assertEqual(event.course_id, self.course.id)
        self.assertEqual(event.created_by_id, self.teacher.id)
        self.assertEqual(event.external_url, "")
        self.assertEqual(set(event.participants.values_list("id", flat=True)), {self.student_a.id, self.student_b.id})
        self.assertEqual(event.start_datetime, self._event_start())
        self.assertEqual(event.end_datetime, self._event_end())

    def test_teacher_creates_event_for_individual_students_only(self):
        self.client.force_login(self.teacher)
        payload = self._today_payload_base(title="Индивидуальное событие", students=[str(self.student_a.id)])

        response = self.client.post("/calendar/create/", data=payload)

        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(title="Индивидуальное событие")
        self.assertIsNone(event.course_id)
        self.assertEqual(set(event.participants.values_list("id", flat=True)), {self.student_a.id})

    def test_teacher_deduplicates_participants_from_course_and_manual_selection(self):
        self.client.force_login(self.teacher)
        payload = self._today_payload_base(
            title="Событие без дублей",
            course=str(self.course.id),
            students=[str(self.student_a.id)],
        )

        response = self.client.post("/calendar/create/", data=payload)

        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(title="Событие без дублей")
        self.assertEqual(set(event.participants.values_list("id", flat=True)), {self.student_a.id, self.student_b.id})

    def test_teacher_cannot_submit_empty_participants(self):
        self.client.force_login(self.teacher)
        payload = self._today_payload_base(title="Пустые участники")

        response = self.client.post("/calendar/create/", data=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Event.objects.filter(title="Пустые участники").count(), 0)

    def test_teacher_cannot_invite_unauthorized_student(self):
        self.client.force_login(self.teacher)
        payload = self._today_payload_base(
            title="Попытка чужого ученика",
            students=[str(self.student_other.id)],
        )

        response = self.client.post("/calendar/create/", data=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Event.objects.filter(title="Попытка чужого ученика").count(), 0)

    def test_calendar_shows_events_for_teacher_and_participant_student(self):
        event = Event.objects.create(
            title="Виден в календаре",
            event_type=Event.EventType.CONCERT,
            start_datetime=self._event_start(),
            end_datetime=self._event_end(),
            description="Публичный показ.",
            course=None,
            created_by=self.teacher,
        )
        event.participants.add(self.student_a)

        self.client.force_login(self.teacher)
        teacher_response = self.client.get("/calendar/")
        self.assertEqual(teacher_response.status_code, 200)
        self.assertContains(teacher_response, "Виден в календаре")

        self.client.force_login(self.student_a)
        student_response = self.client.get("/calendar/")
        self.assertEqual(student_response.status_code, 200)
        self.assertContains(student_response, "Виден в календаре")

        self.client.force_login(self.student_other)
        outsider_response = self.client.get("/calendar/")
        self.assertEqual(outsider_response.status_code, 200)
        self.assertNotContains(outsider_response, "Виден в календаре")
