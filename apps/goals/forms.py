from django import forms

from .models import Goal


class GoalForm(forms.ModelForm):
    max_input_length = 50

    class Meta:
        model = Goal
        fields = ["student", "title", "details"]
        widgets = {
            "student": forms.Select(attrs={"class": "input"}),
            "title": forms.TextInput(attrs={"class": "input", "placeholder": "Годовая цель"}),
            "details": forms.Textarea(attrs={"class": "input", "rows": 3, "placeholder": "Детали"}),
        }
        labels = {
            "student": "Ученик",
            "title": "Годовая цель",
            "details": "Комментарий",
        }

    def clean(self):
        cleaned_data = super().clean()
        for field_name in ("title", "details"):
            value = cleaned_data.get(field_name)
            if value and len(value) >= self.max_input_length:
                self.add_error(field_name, "Введите значение короче 50 символов.")
        return cleaned_data


class StudentGoalCreateForm(forms.ModelForm):
    max_input_length = 50

    class Meta:
        model = Goal
        fields = ["title", "details"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "input", "placeholder": "Годовая цель"}),
            "details": forms.Textarea(attrs={"class": "input", "rows": 3, "placeholder": "Детали"}),
        }
        labels = {
            "title": "Годовая цель",
            "details": "Комментарий",
        }

    def clean(self):
        cleaned_data = super().clean()
        for field_name in ("title", "details"):
            value = cleaned_data.get(field_name)
            if value and len(value) >= self.max_input_length:
                self.add_error(field_name, "Введите значение короче 50 символов.")
        return cleaned_data
