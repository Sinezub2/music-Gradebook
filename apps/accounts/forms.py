# apps/accounts/forms.py
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError

from apps.school.models import Course, Enrollment

from .models import ActivationCode, LibraryVideo, Profile, LIBRARY_VIDEO_EXTENSIONS


def validate_library_video_upload(video):
    if not video:
        return video

    content_type = (getattr(video, "content_type", "") or "").lower()
    extension = video.name.rsplit(".", 1)[-1].lower() if "." in video.name else ""
    if extension not in LIBRARY_VIDEO_EXTENSIONS:
        raise forms.ValidationError("Загрузите видео в формате mp4, mov, webm или m4v.")
    if content_type and not content_type.startswith("video/"):
        raise forms.ValidationError("Файл должен быть видео.")
    return video


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Логин", widget=forms.TextInput(attrs={"autofocus": True}))
    password = forms.CharField(label="Пароль", widget=forms.PasswordInput())


class RegistrationForm(UserCreationForm):
    REGISTERABLE_ROLE_CHOICES = (
        (Profile.Role.TEACHER, "Учитель"),
        (Profile.Role.STUDENT, "Ученик"),
        (Profile.Role.PARENT, "Родитель"),
    )

    username = forms.CharField(label="Логин", max_length=150)
    first_name = forms.CharField(label="Имя", max_length=150)
    last_name = forms.CharField(label="Фамилия", max_length=150)
    role = forms.ChoiceField(label="Роль", choices=REGISTERABLE_ROLE_CHOICES)
    password1 = forms.CharField(label="Пароль", widget=forms.PasswordInput())
    password2 = forms.CharField(label="Повторите пароль", widget=forms.PasswordInput())

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "first_name", "last_name")

    def clean_role(self):
        role = (self.cleaned_data.get("role") or "").strip()
        allowed_roles = {choice[0] for choice in self.REGISTERABLE_ROLE_CHOICES}
        if role not in allowed_roles:
            raise forms.ValidationError("Выберите корректную роль.")
        return role

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data["first_name"].strip()
        user.last_name = self.cleaned_data["last_name"].strip()
        if commit:
            user.save()
        return user


class ActivationCodeCreateForm(forms.Form):
    target_role = forms.ChoiceField(label="Тип кода", choices=ActivationCode.TargetRole.choices)
    course = forms.ModelChoiceField(label="Курс", queryset=Course.objects.none())
    cycle = forms.ChoiceField(label="Цикл", choices=Profile.Cycle.choices)
    student = forms.ModelChoiceField(
        label="Ученик для родителя",
        queryset=get_user_model().objects.none(),
        required=False,
        help_text="Обязательно только для родительского кода.",
    )

    def __init__(self, *args, teacher_user=None, **kwargs):
        self.teacher_user = teacher_user
        super().__init__(*args, **kwargs)

        user_model = get_user_model()
        course_qs = Course.objects.filter(teacher=teacher_user).select_related("course_type").order_by("name", "id")
        self.fields["course"].queryset = course_qs

        student_qs = (
            user_model.objects.filter(
                profile__role=Profile.Role.STUDENT,
                enrollments__course__teacher=teacher_user,
            )
            .select_related("profile")
            .distinct()
            .order_by("first_name", "last_name", "username")
        )
        raw_course_id = self.data.get("course") or self.initial.get("course")
        if raw_course_id and course_qs.filter(id=raw_course_id).exists():
            student_qs = student_qs.filter(enrollments__course_id=raw_course_id)
        self.fields["student"].queryset = student_qs

    def clean(self):
        cleaned_data = super().clean()
        course = cleaned_data.get("course")
        target_role = cleaned_data.get("target_role")
        student = cleaned_data.get("student")

        if course and self.teacher_user and course.teacher_id != self.teacher_user.id:
            self.add_error("course", "Нельзя создать код для чужого курса.")

        if target_role == ActivationCode.TargetRole.PARENT:
            if not student:
                self.add_error("student", "Для родительского кода выберите ученика.")
            elif course and not Enrollment.objects.filter(course=course, student=student).exists():
                self.add_error("student", "Ученик не записан на выбранный курс.")
        else:
            cleaned_data["student"] = None

        return cleaned_data


class ActivationCodeApplyForm(forms.Form):
    code = forms.CharField(label="Код активации", max_length=32)

    def clean_code(self):
        return (self.cleaned_data.get("code") or "").strip().upper()


class UsernameChangeForm(forms.Form):
    username = forms.CharField(label="Новый логин", max_length=150)

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["username"].initial = user.username

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        user_model = get_user_model()
        username_field = user_model._meta.get_field(user_model.USERNAME_FIELD)
        try:
            username_field.run_validators(username)
        except ValidationError as exc:
            raise forms.ValidationError(exc.messages)
        if user_model.objects.exclude(pk=self.user.pk).filter(**{user_model.USERNAME_FIELD: username}).exists():
            raise forms.ValidationError("Этот логин уже занят.")
        return username

    def save(self):
        self.user.username = self.cleaned_data["username"]
        self.user.save(update_fields=["username"])
        return self.user


class StudentProfileDetailsForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ("school_grade", "class_curator_phone")
        labels = {
            "school_grade": "Класс",
            "class_curator_phone": "Номер классного руководителя",
        }
        widgets = {
            "school_grade": forms.TextInput(attrs={"placeholder": "Например, 7Б"}),
            "class_curator_phone": forms.TextInput(attrs={"placeholder": "Например, +7 777 123 45 67"}),
        }


class LibraryVideoUploadForm(forms.ModelForm):
    class Meta:
        model = LibraryVideo
        fields = ("title", "video")
        labels = {
            "title": "Название видео",
            "video": "Видео",
        }
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Например, Домашний разбор этюда"}),
            "video": forms.ClearableFileInput(
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
        }
        help_texts = {
            "video": "Поддерживаются форматы mp4, mov, webm и m4v.",
        }

    def __init__(self, *args, teacher_user=None, student=None, **kwargs):
        self.teacher_user = teacher_user
        self.student = student
        super().__init__(*args, **kwargs)
        self.resolved_course = None
        if teacher_user is not None and student is not None:
            self.resolved_course = (
                Course.objects.filter(teacher=teacher_user, enrollments__student=student)
                .select_related("course_type")
                .distinct()
                .order_by("name", "id")
                .first()
            )
        self.fields["title"].required = False

    def clean_video(self):
        video = self.cleaned_data.get("video")
        return validate_library_video_upload(video)

    def clean(self):
        cleaned_data = super().clean()
        if self.teacher_user and self.student and self.resolved_course is None:
            raise forms.ValidationError("Не удалось определить курс для выбранного ученика.")
        return cleaned_data

    def save(self, *, teacher, student, commit=True):
        instance = super().save(commit=False)
        instance.teacher = teacher
        instance.student = student
        instance.course = self.resolved_course
        if commit:
            instance.save()
        return instance
