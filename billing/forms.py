from django import forms
from .models import Customer, Product, Invoice, InvoiceItem


class InvoiceCreationForm(forms.Form):
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.all(),
        empty_label="Select Customer",
        widget=forms.Select(attrs={
            'class': 'form-input form-select',
            'id': 'customer-select',
        }),
        required=True,
        error_messages={
            'required': 'Please select a customer.',
            'invalid_choice': 'Selected customer is invalid.',
        }
    )

    product = forms.ModelChoiceField(
        queryset=Product.objects.all(),
        empty_label="Select Product",
        widget=forms.Select(attrs={
            'class': 'form-input form-select',
            'id': 'product-select',
        }),
        required=True,
        error_messages={
            'required': 'Please select a product.',
            'invalid_choice': 'Selected product is invalid.',
        }
    )

    quantity = forms.IntegerField(
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-input',
            'id': 'quantity-input',
            'min': '1',
            'placeholder': 'Enter quantity (e.g. 1)',
        }),
        required=True,
        error_messages={
            'required': 'Please enter a valid quantity.',
            'min_value': 'Quantity must be at least 1.',
            'invalid': 'Please enter a valid integer quantity.',
        }
    )

    gst = forms.DecimalField(
        min_value=0,
        initial=0,
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-input',
            'id': 'gst-input',
            'min': '0',
            'max': '100',
            'step': '0.01',
            'placeholder': 'GST % (e.g. 18)',
        }),
        error_messages={
            'min_value': 'GST rate cannot be negative.',
            'invalid': 'Please enter a valid GST percentage.',
        }
    )

    discount = forms.DecimalField(
        min_value=0,
        initial=0,
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-input',
            'id': 'discount-input',
            'min': '0',
            'max': '100',
            'step': '0.01',
            'placeholder': 'Discount % (e.g. 10)',
        }),
        error_messages={
            'min_value': 'Discount cannot be negative.',
            'invalid': 'Please enter a valid discount percentage.',
        }
    )
