import os
import socket
import requests
import urllib3.util.connection as urllib3_cn
from concurrent.futures import ThreadPoolExecutor, as_completed

# import googlemaps  # Replaced with direct requests calls — library had ~40s per-call overhead

# Force IPv4 for all requests calls — Python's requests tries IPv6 first by default,
# which hangs for ~40 seconds on this machine before falling back to IPv4.
# curl is fast because it tries both simultaneously; this patch makes requests do the same.
_original_allowed_gai_family = urllib3_cn.allowed_gai_family
def _force_ipv4():
    return socket.AF_INET
urllib3_cn.allowed_gai_family = _force_ipv4

# Base URL for all Google Maps REST APIs
GOOGLE_MAPS_BASE_URL = "https://maps.googleapis.com/maps/api"


def _api_key() -> str:
    """
    Return the Google Maps API key from the environment.

    Returns:
        str — the API key from GOOGLE_MAPS_API_KEY env var
    """
    return os.environ["GOOGLE_MAPS_API_KEY"]


# def _get_client() -> googlemaps.Client:
#     """Previously used the googlemaps library — replaced with direct requests calls."""
#     return googlemaps.Client(
#         key=os.environ["GOOGLE_MAPS_API_KEY"],
#         timeout=10,
#     )


def geocode_destinations(city: str, destination_names: list[str]) -> list[dict]:
    """
    Convert a list of destination names into geographic coordinates using
    the Google Maps Geocoding API. Appends the city name to each query to
    disambiguate (e.g. "Colosseum" → "Colosseum, Rome, Italy").
    All destinations are geocoded in parallel to minimize total wait time.

    Inputs:
        city              (str)       — the city the user is traveling to,
                                        used to disambiguate place name searches
        destination_names (list[str]) — plain place names extracted from the
                                        LLM response, e.g. ["Big Ben", "Tower of London"]

    Returns:
        list[dict] — one entry per successfully geocoded destination, in the
                     same order as destination_names:
            {
                "name"     : str,   # the original name as passed in
                "address"  : str,   # formatted address returned by Google
                "lat"      : float, # latitude
                "lng"      : float, # longitude
                "place_id" : str,   # Google place ID, useful for future Places API calls
            }
        Destinations that could not be geocoded are skipped with a warning printed.
    """

    def _geocode_one(name: str) -> dict | None:
        """
        Geocode a single destination name via a direct HTTP call to the
        Google Maps Geocoding API REST endpoint.

        Inputs:
            name (str) — the destination name to look up

        Returns:
            dict with name/address/lat/lng/place_id, or None on failure
        """
        # Append city to the query so Google disambiguates correctly —
        # "Tower of London" is unambiguous, but "Castle" or "Park" would not be
        query = f"{name}, {city}"
        print(f"DEBUG geocoding: {query!r}", flush=True)

        try:
            # Call the Geocoding API directly — same as the curl command that was fast
            response = requests.get(
                f"{GOOGLE_MAPS_BASE_URL}/geocode/json",
                params={"address": query, "key": _api_key()},
                timeout=10,  # Fail fast — 10 seconds max per request
            )
            response.raise_for_status()  # Raise an error for non-200 HTTP responses
            data = response.json()

            if data["status"] != "OK" or not data["results"]:
                # Google returned no results or an error status (e.g. ZERO_RESULTS)
                print(f"WARNING: no geocode result for {query!r} (status: {data['status']}) — skipping", flush=True)
                return None

            # Take the first (best) result
            best = data["results"][0]
            location = best["geometry"]["location"]

            result = {
                "name"     : name,
                "address"  : best["formatted_address"],
                "lat"      : location["lat"],
                "lng"      : location["lng"],
                "place_id" : best["place_id"],
            }
            print(f"DEBUG geocoded {name!r} → {location['lat']}, {location['lng']}", flush=True)
            return result

        except Exception as e:
            # Don't let one bad geocode kill the whole request — log and skip
            print(f"WARNING: geocoding failed for {name!r}: {e} — skipping", flush=True)
            return None

    # Run all geocoding calls in parallel — wall-clock time becomes the slowest
    # single call rather than the sum of all calls
    results = []
    with ThreadPoolExecutor(max_workers=len(destination_names)) as executor:
        futures = {executor.submit(_geocode_one, name): name for name in destination_names}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                results.append(result)

    # Restore original order (as_completed returns in completion order, not submission order)
    order = {name: i for i, name in enumerate(destination_names)}
    results.sort(key=lambda r: order.get(r["name"], 999))

    return results
