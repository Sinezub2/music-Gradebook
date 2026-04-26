from django import forms

from apps.accounts.forms import validate_library_video_upload
from apps.accounts.utils import get_user_display_name
from apps.school.models import Course
from apps.text_limits import TEXT_CHAR_LIMIT, char_limit_error, exceeds_char_limit


class AssignmentCreateForm(forms.Form):
    course = forms.ModelChoiceField(label="Курс", queryset=Course.objects.none())
    due_date = forms.DateField(label="Дедлайн", widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
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
            enrollments = (
                course_for_students.enrollments.select_related("student")
                .order_by("student__first_name", "student__last_name", "student__username")
            )
            self.fields["students"].choices = [
                (str(e.student_id), get_user_display_name(e.student))
                for e in enrollments
            ]
        else:
            self.fields["students"].choices = []


class StudentAssignmentCreateForm(forms.Form):
    due_date = forms.DateField(label="Дедлайн", widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    attachment = forms.FileField(label="Прикрепить фото / видео", required=False)


class GroupAssignmentCreateForm(forms.Form):
    max_input_length = TEXT_CHAR_LIMIT
    title = forms.CharField(
        label="Название задания",
        max_length=200,
        widget=forms.TextInput(attrs={"class": "input"}),
    )
    description = forms.CharField(
        label="Описание",
        widget=forms.Textarea(attrs={"rows": 4, "class": "input"}),
    )
    due_date = forms.DateField(label="Дедлайн", widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    attachment = forms.FileField(label="Прикрепить фото / видео", required=False)

    def clean_title(self):
        value = " ".join((self.cleaned_data.get("title") or "").split()).strip()
        if not value:
            raise forms.ValidationError("Укажите название задания.")
        return value

    def clean_description(self):
        value = (self.cleaned_data.get("description") or "").strip()
        if not value:
            raise forms.ValidationError("Укажите описание задания.")
        if exceeds_char_limit(value, self.max_input_length):
            raise forms.ValidationError(char_limit_error(self.max_input_length))
        return value


class StudentAssignmentEditForm(forms.Form):
    max_input_length = TEXT_CHAR_LIMIT
    composition_name = forms.CharField(
        label="Название композиции",
        max_length=200,
        widget=forms.TextInput(attrs={"class": "input"}),
    )
    task_text = forms.CharField(
        label="Задание",
        widget=forms.Textarea(attrs={"rows": 4, "class": "input"}),
    )
    due_date = forms.DateField(label="Дедлайн", widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    attachment = forms.FileField(label="Прикрепить фото / видео", required=False)

    def clean_composition_name(self):
        value = " ".join((self.cleaned_data.get("composition_name") or "").split()).strip()
        if not value:
            raise forms.ValidationError("Укажите название композиции.")
        return value

    def clean_task_text(self):
        value = (self.cleaned_data.get("task_text") or "").strip()
        if not value:
            raise forms.ValidationError("Укажите задание.")
        if exceeds_char_limit(value, self.max_input_length):
            raise forms.ValidationError(char_limit_error(self.max_input_length))
        return value


class AssignmentSubmissionForm(forms.Form):
    student_comment = forms.CharField(
        label="Комментарий",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": "input"}),
    )
    video = forms.FileField(
        label="Видео",
        required=False,
        widget=forms.ClearableFileInput(
            attrs={
                "accept": ",".join(
                    [
                        ".mp4",
                        ".mov",
                        ".webm",
                        ".m4v",
                        "video/mp4",
                        "video/webm",
                        "video/quicktime",
                    ]
                )
            }
        ),
    )

    def clean_video(self):
        return validate_library_video_upload(self.cleaned_data.get("video"))

    def clean(self):
        cleaned_data = super().clean()
        comment = (cleaned_data.get("student_comment") or "").strip()
        video = cleaned_data.get("video")
        if comment and len(comment) >= 500:
            self.add_error("student_comment", "Комментарий слишком длинный.")
        if not comment and not video:
            raise forms.ValidationError("Добавьте комментарий или видео.")
        return cleaned_data
