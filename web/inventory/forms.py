"""Forms for inventory app."""

from django import forms

from .models import CSVUpload, InventoryItem, Location, UPCProduct


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
    photo = forms.ImageField(
        required=False,
        widget=forms.ClearableFileInput(
            attrs={"class": "file-input file-input-bordered w-full"}
        ),
    )
    custom_name = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "input input-bordered w-full",
                "placeholder": "Leave blank to use catalogue name",
            }
        ),
    )
    custom_description = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "textarea textarea-bordered w-full",
                "rows": 4,
                "placeholder": "Leave blank to use catalogue description",
            }
        ),
        required=False,
    )

    product = forms.ModelChoiceField(
        queryset=UPCProduct.objects.all(),
        widget=forms.HiddenInput(),
        required=True,
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
            "photo",
            "custom_name",
            "custom_description",
        ]
        widgets = {
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
