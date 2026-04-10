import json
import os

from django.shortcuts import render, redirect
from django.http import JsonResponse

from .forms import TripSearchForm
from .services.places_service import extract_and_normalize_destinations
from .services.maps_service import (
    geocode_destinations,
    find_hotels_near_destinations,
    rank_hotels_by_walking_distance,
    detect_units,
)


def test(request):
    """Simple health-check endpoint — returns JSON confirmation that the API is up."""
    return JsonResponse({"message": "API is working"})


def home(request):
    """
    Main entry point — renders the trip search form and handles destination
    normalization via the LLM.

    GET:  Render the blank search form.
    POST: Submit city + free-text description to the LLM, which extracts and
          normalizes destinations into "named" and "recommended" lists.
          The user can then review, adjust, and confirm before proceeding
          to the results page.

    Context passed to template:
        form                 (TripSearchForm) — the search form
        named                (list|None)      — LLM-extracted named destinations
        recommended          (list|None)      — LLM-recommended destinations
        city                 (str|None)       — the city, passed through so the
                                                confirm button can POST it to /results/
        original_description (str|None)       — the user's raw input, shown collapsibly
        error                (str|None)       — error message if LLM call failed
    """
    form = TripSearchForm()
    named = None
    recommended = None
    original_description = None
    city = None
    error = None

    if request.method == 'POST':
        form = TripSearchForm(request.POST)
        if form.is_valid():
            city = form.cleaned_data['city']
            free_text = form.cleaned_data['destinations']
            try:
                result = extract_and_normalize_destinations(city, free_text)
                named = result.get("named", [])        # list of {name, category, url, alternatives}
                recommended = result.get("recommended", [])  # same structure
                original_description = free_text
            except Exception as e:
                error = f"Could not process your destinations: {e}"

    return render(request, 'core/home.html', {
        'form': form,
        'named': named,
        'recommended': recommended,
        'city': city,
        'original_description': original_description,
        'error': error,
    })


def results(request):
    """
    Hotel ranking results page — runs all three Maps stages and renders the
    ranked hotel list alongside an interactive map.

    POST only (redirects to home on GET). Receives:
        city        (str)       — the city from the confirmation step
        destination (list[str]) — one value per confirmed destination name

    Context passed to template:
        ranked_hotels         (list)  — hotels sorted by total walking distance,
                                        each with per-destination breakdown
        geocoded_destinations (list)  — destinations with lat/lng for map markers
        city                  (str)   — city name for display
        hotels_json           (str)   — JSON-serialized ranked_hotels for the map JS
        destinations_json     (str)   — JSON-serialized geocoded_destinations for the map JS
        google_maps_api_key   (str)   — Maps JavaScript API key for the embedded map
        error                 (str)   — error message if any stage failed
    """
    # Results are only generated from a confirmed POST — redirect stray GETs to home
    if request.method != 'POST':
        return redirect('home')

    city = request.POST.get('city', '').strip()
    destination_names = request.POST.getlist('destination')

    # Validate that we have something to work with before hitting the APIs
    if not city or not destination_names:
        return render(request, 'core/results.html', {
            'error': 'Missing city or destinations — please go back and try again.'
        })

    # The Distance Matrix API allows 100 elements max (hotels × destinations).
    # With even 1 hotel we need at least 1 destination slot, so cap at 100.
    # In practice users are very unlikely to hit this, but we guard against it cleanly.
    if len(destination_names) > 100:
        return render(request, 'core/results.html', {
            'error': f'You selected {len(destination_names)} destinations — the maximum is 100. Please go back and deselect some.'
        })

    try:
        # Stage 1: Convert destination names to lat/lng coordinates
        geocoded = geocode_destinations(city, destination_names)
        if not geocoded:
            return render(request, 'core/results.html', {
                'error': 'Could not geocode any of your destinations. Please check the names and try again.'
            })

        # Stage 2: Find hotels near the centroid of the destinations
        hotels = find_hotels_near_destinations(geocoded)
        if not hotels:
            return render(request, 'core/results.html', {
                'error': 'No hotels found near your destinations. Try choosing destinations that are closer together.'
            })

        # Stage 3: Rank hotels by total walking distance to all destinations
        # Detect units from the geocoded addresses — imperial for US, metric elsewhere
        units = detect_units(geocoded)
        ranked = rank_hotels_by_walking_distance(hotels, geocoded, units=units)

        # Add map marker letter labels (A, B, C...) to geocoded destinations
        # so the template can display the legend without needing a custom filter
        for i, dest in enumerate(geocoded):
            dest["label"] = chr(65 + i)

        # Serialize hotel and destination data as JSON so the map JavaScript can use it
        # Only pass the fields the map needs — keeps the payload lean
        hotels_for_map = [
            {
                "name"            : h["name"],
                "lat"             : h["lat"],
                "lng"             : h["lng"],
                "rating"          : h["rating"],
                "total_walking_m" : h["total_walking_m"],
                "rank"            : i + 1,
            }
            for i, h in enumerate(ranked)
        ]
        destinations_for_map = [
            {"name": d["name"], "lat": d["lat"], "lng": d["lng"]}
            for d in geocoded
        ]

        return render(request, 'core/results.html', {
            'ranked_hotels'        : ranked,
            'geocoded_destinations': geocoded,
            'city'                 : city,
            'hotels_json'          : json.dumps(hotels_for_map),
            'destinations_json'    : json.dumps(destinations_for_map),
            'google_maps_api_key'  : os.environ.get('GOOGLE_MAPS_API_KEY', ''),
        })

    except Exception as e:
        return render(request, 'core/results.html', {
            'error': f'Something went wrong while searching for hotels: {e}'
        })
