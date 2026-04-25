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
            'placeholder': 'e.g. I want to visit the Coliseum and the three highest-rated museums and the best art galleries and get some excellent linguini. (For activities like cruises or tours, use "Pick from map" on the next screen.)',
            'rows': 4,
        }),
        help_text='Describe your interests in your own words — you can mention specific places or experiences. Or you can be vague, and don\'t worry about spelling.'
    )
