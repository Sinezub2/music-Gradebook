from django import forms
from apps.school.models import Course
from .models import Lesson, LessonReport


class LessonCreateForm(forms.Form):
    course = forms.ModelChoiceField(label="Курс", queryset=Course.objects.none())
    date = forms.DateField(label="Дата", widget=forms.DateInput(attrs={"type": "date"}))
    topic = forms.CharField(label="Тема", max_length=200)
    result = forms.CharField(
        label="Результат (для всех учеников)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    # report (optional but encouraged)
    report_text = forms.CharField(label="Отчёт", required=False, widget=forms.Textarea(attrs={"rows": 4}))
    media_url = forms.URLField(label="Ссылка на медиа", required=False)

    def __init__(self, *args, teacher_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if teacher_user is not None:
            self.fields["course"].queryset = Course.objects.filter(teacher=teacher_user).order_by("name")
        else:
            self.fields["course"].queryset = Course.objects.all().order_by("name")
