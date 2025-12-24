# apps/accounts/forms.py
from django import forms
from django.contrib.auth.forms import AuthenticationForm


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Логин", widget=forms.TextInput(attrs={"autofocus": True}))
    password = forms.CharField(label="Пароль", widget=forms.PasswordInput())
