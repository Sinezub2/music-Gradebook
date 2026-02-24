from django import forms
from apps.school.models import Course
from .models import LessonSlot, StudentSchedule


class LessonCreateForm(forms.Form):
    max_input_length = 50
    course = forms.ModelChoiceField(label="Курс", queryset=Course.objects.none())
    date = forms.DateField(label="Дата", widget=forms.DateInput(attrs={"type": "date"}))
    attachment = forms.FileField(label="Прикрепить фото / видео", required=False)
    media_url = forms.URLField(label="Ссылка на медиа", required=False)

    def __init__(self, *args, teacher_user=None, course_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if course_queryset is not None:
            self.fields["course"].queryset = course_queryset
        elif teacher_user is not None:
            self.fields["course"].queryset = Course.objects.filter(teacher=teacher_user).order_by("name")
        else:
            self.fields["course"].queryset = Course.objects.all().order_by("name")

    def clean(self):
        cleaned_data = super().clean()
        value = cleaned_data.get("media_url")
        if value and len(value) >= self.max_input_length:
            self.add_error("media_url", "Введите значение короче 50 символов.")
        return cleaned_data


class StudentLessonCreateForm(forms.Form):
    max_input_length = 50
    date = forms.DateField(label="Дата", widget=forms.DateInput(attrs={"type": "date"}))
    attachment = forms.FileField(label="Прикрепить фото / видео", required=False)
    media_url = forms.URLField(label="Ссылка на медиа", required=False)

    def clean(self):
        cleaned_data = super().clean()
        value = cleaned_data.get("media_url")
        if value and len(value) >= self.max_input_length:
            self.add_error("media_url", "Введите значение короче 50 символов.")
        return cleaned_data


class StudentScheduleForm(forms.Form):
    weekday = forms.ChoiceField(
        label="День недели",
        choices=StudentSchedule.Weekday.choices,
    )
    lesson_number = forms.IntegerField(
        label="Номер урока (опционально)",
        required=False,
        min_value=1,
        max_value=12,
    )
    start_time = forms.TimeField(
        label="Время начала",
        widget=forms.TimeInput(attrs={"type": "time"}),
    )
    duration_minutes = forms.IntegerField(
        label="Длительность (мин)",
        required=False,
        min_value=20,
        max_value=180,
        initial=45,
    )

    def clean_duration_minutes(self):
        value = self.cleaned_data.get("duration_minutes")
        return value or 45


class SlotReportForm(forms.Form):
    max_input_length = 200
    attendance_status = forms.ChoiceField(
        label="Посещаемость",
        choices=LessonSlot.AttendanceStatus.choices,
    )
    result_note = forms.CharField(
        label="Результат (опционально)",
        required=False,
        max_length=120,
    )
    report_comment = forms.CharField(
        label="Комментарий",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    attachment = forms.FileField(label="Прикрепить файл", required=False)
    media_url = forms.URLField(label="Ссылка на медиа", required=False)

    def clean(self):
        cleaned_data = super().clean()
        for field_name in ("result_note", "report_comment", "media_url"):
            value = cleaned_data.get(field_name)
            if value and len(value) >= self.max_input_length:
                self.add_error(field_name, "Введите значение короче 200 символов.")
        return cleaned_data
