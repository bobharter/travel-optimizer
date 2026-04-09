from django.shortcuts import render
from django.http import JsonResponse
from .forms import TripSearchForm
from .services.places_service import extract_and_normalize_destinations


def test(request):
    return JsonResponse({"message": "API is working"})


def home(request):
    form = TripSearchForm()
    named = None
    recommended = None
    original_description = None
    error = None

    if request.method == 'POST':
        form = TripSearchForm(request.POST)
        if form.is_valid():
            city = form.cleaned_data['city']
            free_text = form.cleaned_data['destinations']
            try:
                result = extract_and_normalize_destinations(city, free_text)
                named = result.get("named", [])        # list of {"name": ..., "category": ...}
                recommended = result.get("recommended", [])  # same
                original_description = free_text
            except Exception as e:
                error = f"Could not process your destinations: {e}"

    return render(request, 'core/home.html', {
        'form': form,
        'named': named,
        'recommended': recommended,
        'original_description': original_description,
        'error': error,
    })
