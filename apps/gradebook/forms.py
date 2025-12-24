# apps/gradebook/forms.py
# Minimal demo: we do simple POST parsing on the teacher page (no ModelForm needed).
from django import forms


class DummyGradeEntryForm(forms.Form):
    """Placeholder to keep structure; not used directly."""
    pass
