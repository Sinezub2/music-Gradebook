from django import forms

from apps.school.models import Course
from apps.text_limits import TEXT_CHAR_LIMIT, char_limit_error, exceeds_char_limit
from .models import LessonSlot, StudentSchedule


class LessonCreateForm(forms.Form):
    max_input_length = TEXT_CHAR_LIMIT
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
        if value and exceeds_char_limit(value, self.max_input_length):
            self.add_error("media_url", char_limit_error(self.max_input_length))
        return cleaned_data


class StudentLessonCreateForm(forms.Form):
    max_input_length = TEXT_CHAR_LIMIT
    date = forms.DateField(label="Дата", widget=forms.DateInput(attrs={"type": "date"}))
    attachment = forms.FileField(label="Прикрепить фото / видео", required=False)
    media_url = forms.URLField(label="Ссылка на медиа", required=False)

    def clean(self):
        cleaned_data = super().clean()
        value = cleaned_data.get("media_url")
        if value and exceeds_char_limit(value, self.max_input_length):
            self.add_error("media_url", char_limit_error(self.max_input_length))
        return cleaned_data


class GroupAttendanceSessionForm(forms.Form):
    date = forms.DateField(label="Дата", widget=forms.DateInput(attrs={"type": "date"}))
    topic = forms.CharField(
        label="Тема занятия",
        max_length=200,
        widget=forms.TextInput(attrs={"class": "input"}),
    )
    attachment = forms.FileField(label="Материалы", required=False)

    def clean_topic(self):
        value = " ".join((self.cleaned_data.get("topic") or "").split()).strip()
        if not value:
            raise forms.ValidationError("Укажите тему занятия.")
        return value


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


class SlotReportForm(forms.Form):
    attendance_status = forms.ChoiceField(
        label="Посещаемость",
        choices=(
            (LessonSlot.AttendanceStatus.PRESENT, "Присутствовал"),
            (LessonSlot.AttendanceStatus.ABSENT, "Не присутствовал"),
        ),
    )


class SlotRescheduleForm(forms.Form):
    new_date = forms.DateField(
        label="Новая дата",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    new_start_time = forms.TimeField(
        label="Новое время начала",
        widget=forms.TimeInput(attrs={"type": "time"}),
    )
    reason = forms.CharField(
        label="Причина переноса (опционально)",
        required=False,
        max_length=255,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
