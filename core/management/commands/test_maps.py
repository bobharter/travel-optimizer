"""
Django management command for testing Google Maps API integration in stages.

Usage:
    python manage.py test_maps --stage 1   # test geocoding only
    python manage.py test_maps --stage 2   # test hotel search (coming soon)
    python manage.py test_maps --stage 3   # test distance matrix (coming soon)

This lets us verify each Maps API function in isolation before wiring
everything into the web UI.
"""
import os
from django.core.management.base import BaseCommand
from core.services.maps_service import geocode_destinations


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
