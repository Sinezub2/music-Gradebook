from django import forms

from .models import Goal


class GoalForm(forms.ModelForm):
    max_input_length = 50

    class Meta:
        model = Goal
        fields = ["title"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "input", "placeholder": "Цель на полугодие"}),
        }
        labels = {
            "title": "Цель на полугодие",
        }

    def clean_title(self):
        value = (self.cleaned_data.get("title") or "").strip()
        if len(value) >= self.max_input_length:
            raise forms.ValidationError("Введите значение короче 50 символов.")
        return value


class StudentGoalCreateForm(forms.ModelForm):
    max_input_length = 50

    class Meta:
        model = Goal
        fields = ["title"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "input", "placeholder": "Цель на полугодие"}),
        }
        labels = {
            "title": "Цель на полугодие",
        }

    def clean_title(self):
        value = (self.cleaned_data.get("title") or "").strip()
        if len(value) >= self.max_input_length:
            raise forms.ValidationError("Введите значение короче 50 символов.")
        return value
