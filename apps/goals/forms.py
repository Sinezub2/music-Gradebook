from django import forms

from .models import Goal


class GoalForm(forms.ModelForm):
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
