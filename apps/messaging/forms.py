from django import forms


class MessageForm(forms.Form):
    text = forms.CharField(label="", widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Сообщение..."}))
