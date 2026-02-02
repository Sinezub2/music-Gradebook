# apps/gradebook/management/commands/seed_demo.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction

from apps.accounts.models import Profile
from apps.school.models import Course, CourseType, Enrollment, ParentChild
from apps.gradebook.models import Assessment, Grade


class Command(BaseCommand):
    help = "Seed demo data for music-gradebook (idempotent)."

    def handle(self, *args, **options):
        with transaction.atomic():
            admin_user = self._get_or_create_user("admin", "adminpass", is_staff=True, is_superuser=True)
            self._ensure_profile(admin_user, Profile.Role.ADMIN)

            teacher = self._get_or_create_user("teacher1", "pass", is_staff=False, is_superuser=False)
            self._ensure_profile(teacher, Profile.Role.TEACHER)

            student = self._get_or_create_user("student1", "pass", is_staff=False, is_superuser=False)
            self._ensure_profile(student, Profile.Role.STUDENT)

            parent = self._get_or_create_user("parent1", "pass", is_staff=False, is_superuser=False)
            self._ensure_profile(parent, Profile.Role.PARENT)

            ParentChild.objects.get_or_create(parent=parent, child=student)

            instrument = self._get_or_create_course_type("Инструмент")
            ensemble = self._get_or_create_course_type("Ансамбль")
            theory = self._get_or_create_course_type("Теория")

            c1 = self._get_or_create_course("Фортепиано (инд.)", instrument, teacher)
            c2 = self._get_or_create_course("Ансамбль", ensemble, teacher)
            c3 = self._get_or_create_course("Теория музыки", theory, teacher)

            for c in (c1, c2, c3):
                Enrollment.objects.get_or_create(course=c, student=student)

            # Assessments per course
            self._seed_assessments_and_grades(course=c1, student=student, items=[
                ("Домашнее задание 1", Assessment.AssessmentType.HOMEWORK, "100", "1"),
                ("Выступление (класс)", Assessment.AssessmentType.PERFORMANCE, "100", "2"),
                ("Жюри №1", Assessment.AssessmentType.JURY, "100", "3"),
            ])

            self._seed_assessments_and_grades(course=c2, student=student, items=[
                ("Домашнее задание 1", Assessment.AssessmentType.HOMEWORK, "100", "1"),
                ("Выступление (концерт)", Assessment.AssessmentType.PERFORMANCE, "100", "3"),
                ("Жюри №1", Assessment.AssessmentType.JURY, "100", "2"),
                ("Домашнее задание 2", Assessment.AssessmentType.HOMEWORK, "100", "1"),
            ])

            self._seed_assessments_and_grades(course=c3, student=student, items=[
                ("Тест 1", Assessment.AssessmentType.THEORY_TEST, "20", "2"),
                ("Домашнее задание 1", Assessment.AssessmentType.HOMEWORK, "10", "1"),
                ("Тест 2", Assessment.AssessmentType.THEORY_TEST, "20", "2"),
                ("Домашнее задание 2", Assessment.AssessmentType.HOMEWORK, "10", "1"),
                ("Жюри (зачёт)", Assessment.AssessmentType.JURY, "100", "3"),
            ])

        self.stdout.write(self.style.SUCCESS("Demo data seeded (idempotent)."))

    def _get_or_create_user(self, username: str, password: str, is_staff: bool, is_superuser: bool) -> User:
        user, created = User.objects.get_or_create(username=username, defaults={
            "is_staff": is_staff,
            "is_superuser": is_superuser,
        })
        # Ensure flags are correct even if user existed
        if user.is_staff != is_staff or user.is_superuser != is_superuser:
            user.is_staff = is_staff
            user.is_superuser = is_superuser
            user.save()

        # Always set password deterministically for demo
        user.set_password(password)
        user.save()
        return user

    def _ensure_profile(self, user: User, role: str) -> None:
        profile, _ = Profile.objects.get_or_create(user=user, defaults={"role": role})
        if profile.role != role:
            profile.role = role
            profile.save()

    def _get_or_create_course_type(self, name: str) -> CourseType:
        course_type, _ = CourseType.objects.get_or_create(name=name)
        return course_type

    def _get_or_create_course(self, name: str, course_type: CourseType, teacher: User) -> Course:
        course, _ = Course.objects.get_or_create(name=name, defaults={"course_type": course_type, "teacher": teacher})
        changed = False
        if course.course_type_id != course_type.id:
            course.course_type = course_type
            changed = True
        if course.teacher_id != teacher.id:
            course.teacher = teacher
            changed = True
        if changed:
            course.save()
        return course

    def _seed_assessments_and_grades(self, course: Course, student: User, items: list[tuple[str, str, str, str]]) -> None:
        # Create assessments, then create grades with some sample scores/comments
        for idx, (title, a_type, max_score, weight) in enumerate(items, start=1):
            a, _ = Assessment.objects.get_or_create(
                course=course,
                title=title,
                defaults={
                    "assessment_type": a_type,
                    "max_score": max_score,
                    "weight": weight,
                },
            )
            # Ensure fields stable
            changed = False
            if a.assessment_type != a_type:
                a.assessment_type = a_type
                changed = True
            if str(a.max_score) != str(max_score):
                a.max_score = max_score
                changed = True
            if str(a.weight) != str(weight):
                a.weight = weight
                changed = True
            if changed:
                a.save()

            g, _ = Grade.objects.get_or_create(assessment=a, student=student)
            # Simple deterministic demo score pattern
            if g.score is None:
                # Put a plausible score within max_score
                try:
                    ms = float(a.max_score)
                except Exception:
                    ms = 100.0
                score = round(ms * (0.7 + 0.05 * (idx % 4)), 2)  # 0.70..0.85
                g.score = str(score)
                g.comment = "Демо-результат"
                g.save()
