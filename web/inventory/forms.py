"""Forms for inventory app."""

from django import forms

from .models import CSVUpload, InventoryItem, Location


class UploadForm(forms.ModelForm):
    class Meta:
        model = CSVUpload
        fields = ["file"]


class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "description": forms.Textarea(
                attrs={"class": "textarea textarea-bordered w-full", "rows": 3}
            ),
        }


class InventoryItemForm(forms.ModelForm):
    location = forms.ModelChoiceField(
        queryset=None,
        widget=forms.Select(attrs={"class": "select select-bordered w-full"}),
        required=False,
        empty_label="No location",
    )
    expiry_date = forms.DateField(
        widget=forms.DateInput(
            attrs={"type": "date", "class": "input input-bordered w-full"}
        ),
        required=False,
    )
    purchase_date = forms.DateField(
        widget=forms.DateInput(
            attrs={"type": "date", "class": "input input-bordered w-full"}
        ),
        required=False,
    )

    class Meta:
        model = InventoryItem
        fields = [
            "product",
            "location",
            "quantity",
            "low_stock_threshold",
            "purchase_date",
            "expiry_date",
            "notes",
        ]
        widgets = {
            "product": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "quantity": forms.NumberInput(
                attrs={"class": "input input-bordered w-full", "min": 1}
            ),
            "low_stock_threshold": forms.NumberInput(
                attrs={"class": "input input-bordered w-full", "min": 0}
            ),
            "notes": forms.Textarea(
                attrs={"class": "textarea textarea-bordered w-full", "rows": 3}
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["location"].queryset = Location.objects.filter(user=user)
