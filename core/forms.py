from django import forms


class TripSearchForm(forms.Form):
    city = forms.CharField(
        label='City',
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'e.g. Paris, France',
        })
    )
    destinations = forms.CharField(
        label='Destinations',
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. Eiffel Tower, Louvre Museum, Notre-Dame Cathedral',
            'rows': 3,
        }),
        help_text='Enter places separated by commas.'
    )
