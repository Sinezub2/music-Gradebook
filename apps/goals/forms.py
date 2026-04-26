from django import forms

from apps.text_limits import TEXT_CHAR_LIMIT, char_limit_error, exceeds_char_limit
from .models import Goal


class GoalForm(forms.ModelForm):
    max_input_length = TEXT_CHAR_LIMIT

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
        if exceeds_char_limit(value, self.max_input_length):
            raise forms.ValidationError(char_limit_error(self.max_input_length))
        return value


class StudentGoalCreateForm(forms.ModelForm):
    max_input_length = TEXT_CHAR_LIMIT

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
        if exceeds_char_limit(value, self.max_input_length):
            raise forms.ValidationError(char_limit_error(self.max_input_length))
        return value
