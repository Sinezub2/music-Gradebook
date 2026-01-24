from django import forms

from .models import Goal


class GoalForm(forms.ModelForm):
    max_input_length = 50
    month = forms.DateField(
        input_formats=["%Y-%m"],
        widget=forms.DateInput(attrs={"type": "month", "class": "input"}),
        label="Месяц",
    )

    class Meta:
        model = Goal
        fields = ["student", "month", "title", "details"]
        widgets = {
            "student": forms.Select(attrs={"class": "input"}),
            "title": forms.TextInput(attrs={"class": "input", "placeholder": "Цель на месяц"}),
            "details": forms.Textarea(attrs={"class": "input", "rows": 3, "placeholder": "Детали"}),
        }
        labels = {
            "student": "Ученик",
            "title": "Цель",
            "details": "Комментарий",
        }

    def clean(self):
        cleaned_data = super().clean()
        for field_name in ("title", "details"):
            value = cleaned_data.get(field_name)
            if value and len(value) >= self.max_input_length:
                self.add_error(field_name, "Введите значение короче 50 символов.")
        return cleaned_data
