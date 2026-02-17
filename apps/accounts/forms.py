# apps/accounts/forms.py
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Логин", widget=forms.TextInput(attrs={"autofocus": True}))
    password = forms.CharField(label="Пароль", widget=forms.PasswordInput())


class StudentInviteCreateForm(forms.Form):
    first_name = forms.CharField(label="Имя", max_length=150)
    last_name = forms.CharField(label="Фамилия", max_length=150)
    school_grade = forms.CharField(label="Класс", max_length=20, required=False)


class InviteRegistrationForm(UserCreationForm):
    username = forms.CharField(label="Логин", max_length=150)
    password1 = forms.CharField(label="Пароль", widget=forms.PasswordInput())
    password2 = forms.CharField(label="Подтверждение пароля", widget=forms.PasswordInput())

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username",)


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
