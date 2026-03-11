from django import forms
from django.contrib.auth import get_user_model

from apps.accounts.models import Profile
from apps.school.models import Course, Enrollment

from .models import Event


class TeacherEventCreateForm(forms.Form):
    event_type = forms.ChoiceField(label="Тип события", choices=Event.EventType.choices)
    event_date = forms.DateField(label="Дата", widget=forms.DateInput(attrs={"type": "date"}))
    title = forms.CharField(label="Название события", max_length=200)
    description = forms.CharField(label="Описание", widget=forms.Textarea(attrs={"rows": 4}))
    external_url = forms.URLField(label="Ссылка (опционально)", required=False)
    course = forms.ModelChoiceField(label="Пригласить курс целиком (опционально)", queryset=Course.objects.none(), required=False)
    students = forms.ModelMultipleChoiceField(
        label="Пригласить отдельных учеников (опционально)",
        required=False,
        queryset=get_user_model().objects.none(),
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, teacher_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.teacher_user = teacher_user
        user_model = get_user_model()

        if teacher_user is None:
            self.fields["course"].queryset = Course.objects.none()
            self.fields["students"].queryset = user_model.objects.none()
            return

        self.fields["course"].queryset = Course.objects.filter(teacher=teacher_user).order_by("name")
        self.fields["students"].queryset = (
            user_model.objects.filter(
                profile__role=Profile.Role.STUDENT,
                enrollments__course__teacher=teacher_user,
            )
            .select_related("profile")
            .distinct()
            .order_by("first_name", "last_name", "username")
        )

    def clean_title(self):
        value = (self.cleaned_data.get("title") or "").strip()
        if not value:
            raise forms.ValidationError("Введите название события.")
        return value

    def clean_description(self):
        value = (self.cleaned_data.get("description") or "").strip()
        if not value:
            raise forms.ValidationError("Введите описание события.")
        return value

    def clean_external_url(self):
        value = (self.cleaned_data.get("external_url") or "").strip()
        return value

    def clean(self):
        cleaned_data = super().clean()
        course = cleaned_data.get("course")
        students = cleaned_data.get("students")

        if not course and (students is None or not students.exists()):
            raise forms.ValidationError("Выберите курс, учеников или оба варианта.")

        if self.teacher_user is None:
            raise forms.ValidationError("Недоступно без преподавателя.")

        if course and course.teacher_id != self.teacher_user.id:
            self.add_error("course", "Можно выбрать только ваш курс.")

        if students and students.exclude(enrollments__course__teacher=self.teacher_user).exists():
            self.add_error("students", "Можно выбрать только учеников из ваших курсов.")

        if course and (students is None or not students.exists()):
            has_students = Enrollment.objects.filter(
                course=course,
                student__profile__role=Profile.Role.STUDENT,
            ).exists()
            if not has_students:
                self.add_error("course", "В выбранном курсе пока нет учеников.")

        return cleaned_data
