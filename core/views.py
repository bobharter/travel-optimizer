from django.shortcuts import render
from django.http import JsonResponse
from .forms import TripSearchForm


def test(request):
    return JsonResponse({"message": "API is working"})


def home(request):
    form = TripSearchForm()
    destinations = None

    if request.method == 'POST':
        form = TripSearchForm(request.POST)
        if form.is_valid():
            city = form.cleaned_data['city']
            destinations = [d.strip() for d in form.cleaned_data['destinations'].split(',') if d.strip()]

    return render(request, 'core/home.html', {'form': form, 'destinations': destinations})
