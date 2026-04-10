"""
Django management command for testing Google Maps API integration in stages.

Usage:
    python manage.py test_maps --stage 1   # test geocoding only
    python manage.py test_maps --stage 2   # test hotel search
    python manage.py test_maps --stage 3   # test distance matrix ranking

This lets us verify each Maps API function in isolation before wiring
everything into the web UI.
"""
import os
from django.core.management.base import BaseCommand
from core.services.maps_service import geocode_destinations, find_hotels_near_destinations, rank_hotels_by_walking_distance


class Command(BaseCommand):
    """
    Management command to test Google Maps API calls stage by stage.
    Run with: python manage.py test_maps --stage <number>
    """
    help = "Test Google Maps API integration by stage"

    def add_arguments(self, parser):
        """
        Define command-line arguments.
        --stage: which stage to test (default: 1)
        """
        parser.add_argument(
            "--stage",
            type=int,
            default=1,
            help="Which stage to test: 1=geocoding, 2=hotel search, 3=distance matrix",
        )

    def handle(self, *args, **options):
        """
        Entry point — dispatch to the appropriate stage test.

        Inputs:
            options["stage"] (int) — the stage number to run
        """
        stage = options["stage"]

        if stage == 1:
            self._test_geocoding()
        elif stage == 2:
            self._test_hotel_search()
        elif stage == 3:
            self._test_distance_matrix()
        else:
            self.stdout.write(self.style.WARNING(f"Stage {stage} not implemented yet."))

    def _test_geocoding(self):
        """
        Stage 1: Test geocode_destinations() with a known city and set of landmarks.
        Prints the resulting coordinates so we can verify accuracy before proceeding.
        """
        # Use London with a mix of well-known and slightly ambiguous destinations
        # to test both the happy path and the city-disambiguation logic
        city = "London, UK"
        destinations = [
            "Big Ben",
            "Tower of London",
            "British Museum",
            "Borough Market",
        ]

        # Print the first 10 chars of the API key so we can confirm it loaded from .env
        # (without exposing the full key)
        api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "NOT SET")
        self.stdout.write(f"API key loaded: {api_key[:10]}..." if api_key != "NOT SET" else "ERROR: GOOGLE_MAPS_API_KEY not set!")

        self.stdout.write(f"\nStage 1: Geocoding destinations in {city}")
        self.stdout.write("-" * 50)

        results = geocode_destinations(city, destinations)

        if not results:
            self.stdout.write(self.style.ERROR("No results returned — check your GOOGLE_MAPS_API_KEY"))
            return

        for r in results:
            self.stdout.write(
                f"\n  {r['name']}"
                f"\n    Address  : {r['address']}"
                f"\n    Coords   : {r['lat']}, {r['lng']}"
                f"\n    Place ID : {r['place_id']}"
            )

        self.stdout.write(self.style.SUCCESS(f"\nGeocoded {len(results)} of {len(destinations)} destinations successfully."))
        return results

    def _test_hotel_search(self):
        """
        Stage 2: Test find_hotels_near_destinations() using the geocoded results
        from Stage 1 as input. Prints the hotels found near the centroid so we
        can verify the search area and result quality before Stage 3.
        """
        city = "London, UK"
        destinations = [
            "Big Ben",
            "Tower of London",
            "British Museum",
            "Borough Market",
        ]

        self.stdout.write(f"\nStage 2: Finding hotels near destinations in {city}")
        self.stdout.write("-" * 50)

        # Stage 2 depends on Stage 1 — geocode first, then search for hotels
        self.stdout.write("Step 1: Geocoding destinations...")
        geocoded = geocode_destinations(city, destinations)

        if not geocoded:
            self.stdout.write(self.style.ERROR("Geocoding failed — cannot proceed to hotel search"))
            return

        self.stdout.write(f"  Geocoded {len(geocoded)} destinations")

        # Search for hotels near the centroid of those destinations
        self.stdout.write("\nStep 2: Searching for hotels near centroid...")
        hotels = find_hotels_near_destinations(geocoded)

        if not hotels:
            self.stdout.write(self.style.WARNING("No hotels found near the centroid — try increasing radius_meters"))
            return

        for h in hotels:
            # Show rating as a star-like display, or "No rating" if unavailable
            rating = f"{h['rating']} ★" if h['rating'] else "No rating"
            self.stdout.write(
                f"\n  {h['name']}"
                f"\n    Address  : {h['address']}"
                f"\n    Coords   : {h['lat']}, {h['lng']}"
                f"\n    Rating   : {rating}"
                f"\n    Place ID : {h['place_id']}"
            )

        self.stdout.write(self.style.SUCCESS(f"\nFound {len(hotels)} hotels near centroid."))

    def _test_distance_matrix(self):
        """
        Stage 3: Test rank_hotels_by_walking_distance() using results from
        Stages 1 and 2 as input. Prints hotels ranked by total walking distance
        to all destinations so we can verify the ranking logic before wiring
        into the web UI.
        """
        city = "London, UK"
        destinations = [
            "Big Ben",
            "Tower of London",
            "British Museum",
            "Borough Market",
        ]

        self.stdout.write(f"\nStage 3: Ranking hotels by walking distance in {city}")
        self.stdout.write("-" * 50)

        # Stage 3 depends on Stages 1 and 2 — run them first
        self.stdout.write("Step 1: Geocoding destinations...")
        geocoded = geocode_destinations(city, destinations)
        if not geocoded:
            self.stdout.write(self.style.ERROR("Geocoding failed — cannot proceed"))
            return

        self.stdout.write(f"Step 2: Finding hotels near centroid...")
        hotels = find_hotels_near_destinations(geocoded)
        if not hotels:
            self.stdout.write(self.style.WARNING("No hotels found — cannot proceed"))
            return

        self.stdout.write(f"Step 3: Ranking {len(hotels)} hotels by walking distance...")
        ranked = rank_hotels_by_walking_distance(hotels, geocoded)

        # Print ranked results — most useful hotel first
        for i, h in enumerate(ranked, start=1):
            rating = f"{h['rating']} ★" if h['rating'] else "No rating"
            self.stdout.write(f"\n  #{i} {h['name']} ({rating})")
            self.stdout.write(f"      Total walking: {h['total_walking_m']}m")
            # Show the per-destination breakdown so we can verify accuracy
            for d in h["per_destination"]:
                self.stdout.write(f"      → {d['destination']}: {d['distance_text']} ({d['duration_text']})")

        self.stdout.write(self.style.SUCCESS(f"\nRanked {len(ranked)} hotels successfully."))
