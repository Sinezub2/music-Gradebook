from django import forms
from django.utils import timezone

from apps.school.models import Course


class AssignmentCreateForm(forms.Form):
    max_input_length = 50
    course = forms.ModelChoiceField(label="Курс", queryset=Course.objects.none())
    title = forms.CharField(label="Название", max_length=200)
    description = forms.CharField(label="Описание", required=False, widget=forms.Textarea(attrs={"rows": 4}))
    due_date = forms.DateField(label="Дедлайн", widget=forms.DateInput(attrs={"type": "date"}))
    attachment = forms.FileField(label="Прикрепить фото / видео", required=False)

    # Students чекбоксы подставляем динамически
    students = forms.MultipleChoiceField(
        label="Назначить ученикам",
        required=False,
        widget=forms.CheckboxSelectMultiple,
        choices=[],
    )

    def __init__(self, *args, teacher_user=None, course_for_students=None, course_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Teacher sees only their courses (admin can be supported later; сейчас по ТЗ teacher-only create view)
        if course_queryset is not None:
            self.fields["course"].queryset = course_queryset
        elif teacher_user is not None:
            self.fields["course"].queryset = Course.objects.filter(teacher=teacher_user).order_by("name")
        else:
            self.fields["course"].queryset = Course.objects.all().order_by("name")

        if course_for_students is not None:
            # course_for_students: Course instance
            enrollments = course_for_students.enrollments.select_related("student").order_by("student__username")
            self.fields["students"].choices = [(str(e.student_id), e.student.username) for e in enrollments]
        else:
            self.fields["students"].choices = []

    def clean(self):
        cleaned_data = super().clean()
        for field_name in ("title", "description"):
            value = cleaned_data.get(field_name)
            if value and len(value) >= self.max_input_length:
                self.add_error(field_name, "Введите значение короче 50 символов.")
        return cleaned_data


class StudentAssignmentCreateForm(forms.Form):
    max_input_length = 50
    title = forms.CharField(label="Название", max_length=200)
    description = forms.CharField(label="Описание", required=False, widget=forms.Textarea(attrs={"rows": 4}))
    due_date = forms.DateField(label="Дедлайн", widget=forms.DateInput(attrs={"type": "date"}))
    attachment = forms.FileField(label="Прикрепить фото / видео", required=False)

    def clean(self):
        cleaned_data = super().clean()
        for field_name in ("title", "description"):
            value = cleaned_data.get(field_name)
            if value and len(value) >= self.max_input_length:
                self.add_error(field_name, "Введите значение короче 50 символов.")
        return cleaned_data
