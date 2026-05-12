from django import forms

from apps.accounts.utils import get_user_display_name

from .models import CourseInternalGroup
from .utils import get_group_student_enrollments


class CourseInternalGroupForm(forms.Form):
    group_type = forms.ChoiceField(
        label="Тип внутренней группы",
        choices=CourseInternalGroup.GroupType.choices,
    )
    name = forms.CharField(
        label="Название (опционально)",
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Например, Подгруппа A"}),
    )
    students = forms.MultipleChoiceField(
        label="Ученики",
        required=False,
        widget=forms.CheckboxSelectMultiple,
        choices=[],
    )

    def __init__(self, *args, course=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.course = course
        if course is None:
            self.fields["students"].choices = []
            return
        enrollments = list(get_group_student_enrollments(course))
        self.fields["students"].choices = [
            (str(enrollment.student_id), get_user_display_name(enrollment.student))
            for enrollment in enrollments
        ]

    def clean_name(self):
        return " ".join((self.cleaned_data.get("name") or "").split()).strip()

    def clean_students(self):
        student_ids = []
        for value in self.cleaned_data.get("students", []):
            try:
                student_ids.append(int(value))
            except (TypeError, ValueError) as exc:
                raise forms.ValidationError("Некорректный ученик в выбранной группе.") from exc
        return student_ids

    def clean(self):
        cleaned_data = super().clean()
        if self.course is None:
            raise forms.ValidationError("Курс не найден.")
        if not cleaned_data.get("students"):
            raise forms.ValidationError("Выберите хотя бы одного ученика.")
        if cleaned_data.get("group_type") == CourseInternalGroup.GroupType.CUSTOM and not cleaned_data.get("name"):
            self.add_error("name", "Укажите название для своей группы.")
        return cleaned_data
