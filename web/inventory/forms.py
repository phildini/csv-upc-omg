"""Forms for core_app."""

from django import forms

from .models import CSVUpload


class UploadForm(forms.ModelForm):
    class Meta:
        model = CSVUpload
        fields = ["file"]
