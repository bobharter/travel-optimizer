import os
import math
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

# Radius clamping bounds — prevents searches that are too tight (few/no results)
# or absurdly large (irrelevant hotels far from destinations)
MIN_SEARCH_RADIUS_METERS = 500
MAX_SEARCH_RADIUS_METERS = 5000

# Fraction of the max destination spread to use as the hotel search radius.
# 1/2 means hotels up to half the full spread from the centroid (looser).
# 1/3 means hotels within a tighter central zone — good default for city trips.
RADIUS_FRACTION = 1 / 3


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


def _calculate_centroid(geocoded_destinations: list[dict]) -> tuple[float, float]:
    """
    Calculate the geographic centroid (average position) of a list of geocoded
    destinations. Used to find the central point around which to search for hotels.

    Inputs:
        geocoded_destinations (list[dict]) — list of dicts each containing "lat" and "lng",
                                             as returned by geocode_destinations()

    Returns:
        tuple (lat, lng) — the centroid coordinates as floats
    """
    # Simple average of lat/lng — accurate enough for city-scale distances
    avg_lat = sum(d["lat"] for d in geocoded_destinations) / len(geocoded_destinations)
    avg_lng = sum(d["lng"] for d in geocoded_destinations) / len(geocoded_destinations)
    return avg_lat, avg_lng


def _haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate the straight-line distance in metres between two geographic
    coordinates using the Haversine formula. Accurate enough for city-scale
    distances where Earth's curvature has minimal effect.

    Inputs:
        lat1, lng1 (float) — coordinates of the first point
        lat2, lng2 (float) — coordinates of the second point

    Returns:
        float — distance in metres between the two points
    """
    # Earth's mean radius in metres
    R = 6_371_000

    # Convert degrees to radians for the trig functions
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)

    # Haversine formula
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _calculate_search_radius(geocoded_destinations: list[dict]) -> int:
    """
    Calculate a dynamic hotel search radius based on the spread of the user's
    destinations. Uses half the distance between the two farthest destinations
    so that the search circle is just large enough to encompass the area
    between them, clamped to sensible min/max bounds.

    Inputs:
        geocoded_destinations (list[dict]) — geocoded destinations, each with "lat" and "lng"

    Returns:
        int — search radius in metres, clamped between MIN_SEARCH_RADIUS_METERS
              and MAX_SEARCH_RADIUS_METERS
    """
    # With only one destination there's no spread — use the minimum radius
    if len(geocoded_destinations) < 2:
        return MIN_SEARCH_RADIUS_METERS

    # Find the maximum pairwise distance between all destinations
    max_distance = 0.0
    for i, a in enumerate(geocoded_destinations):
        for b in geocoded_destinations[i + 1:]:
            # Compare every unique pair (i, j) where j > i to avoid duplicates
            dist = _haversine_distance(a["lat"], a["lng"], b["lat"], b["lng"])
            if dist > max_distance:
                max_distance = dist

    # Use RADIUS_FRACTION of the full spread — 1/3 keeps hotels in the tighter
    # central zone rather than allowing them to drift toward the outer edges
    radius = max_distance * RADIUS_FRACTION

    # Clamp to avoid degenerate cases (all destinations at the same spot, or very spread out)
    clamped = int(max(MIN_SEARCH_RADIUS_METERS, min(radius, MAX_SEARCH_RADIUS_METERS)))
    print(f"DEBUG max destination spread: {max_distance:.0f}m → search radius: {clamped}m", flush=True)
    return clamped


def detect_units(geocoded_destinations: list[dict]) -> str:
    """
    Detect whether to use imperial or metric distance units based on the
    country of the geocoded destinations. Checks the formatted_address field
    returned by Google's Geocoding API, which always ends with the country name.

    Inputs:
        geocoded_destinations (list[dict]) — geocoded destinations as returned by
                                             geocode_destinations(), each with an "address" field

    Returns:
        str — "imperial" if destinations are in the United States, "metric" otherwise

    Future enhancement: expose this as a user-selectable toggle on the results page
    so travelers who prefer one system regardless of location can override it.
    """
    for dest in geocoded_destinations:
        address = dest.get("address", "")
        # Google's formatted_address can end with either "USA" (short form) or
        # "United States" (long form) depending on the place type — check both
        if "United States" in address or ", USA" in address:
            return "imperial"
    return "metric"


# Place types returned by the Places API that are too generic to display —
# we skip these and show the first more-specific type instead
_GENERIC_PLACE_TYPES = {"lodging", "point_of_interest", "establishment", "food", "store"}


def _format_place_type(types: list[str]) -> str:
    """
    Extract the most descriptive place type from the Places API types array
    and format it for display. Skips generic catch-all types like "lodging"
    and "establishment" to surface more specific labels like "hotel" or
    "bed_and_breakfast".

    Inputs:
        types (list[str]) — the types array from a Places API result,
                            e.g. ["hotel", "lodging", "establishment"]

    Returns:
        str — a human-readable label, e.g. "Hotel", "Bed And Breakfast", "Lodging"
    """
    for t in types:
        if t not in _GENERIC_PLACE_TYPES:
            # Convert snake_case to Title Case for display: "bed_and_breakfast" → "Bed And Breakfast"
            return t.replace("_", " ").title()
    # All types were generic — fall back to "Lodging" as the least-wrong label
    return "Lodging"


def _max_hotel_results() -> int:
    """
    Read the maximum number of hotel results to return from the MAX_HOTEL_RESULTS
    env var. Defaults to 20 if not set. Configurable in .env without touching code.

    Returns:
        int — maximum number of hotels to fetch and rank
    """
    try:
        return int(os.environ.get("MAX_HOTEL_RESULTS", "20"))
    except ValueError:
        # If the env var is set to a non-integer, fall back to the default
        print("WARNING: MAX_HOTEL_RESULTS is not a valid integer — using default of 20", flush=True)
        return 20


def find_hotels_near_destinations(geocoded_destinations: list[dict]) -> list[dict]:
    """
    Find hotels near the centroid of the given destinations using the
    Google Maps Places Nearby Search API. The search radius is calculated
    dynamically based on the spread of the destinations (half the distance
    between the two farthest destinations), clamped between
    MIN_SEARCH_RADIUS_METERS and MAX_SEARCH_RADIUS_METERS. The maximum number
    of results is read from the MAX_HOTEL_RESULTS env var (default: 20).

    Inputs:
        geocoded_destinations (list[dict]) — geocoded destinations as returned by
                                             geocode_destinations(); each must have
                                             "lat" and "lng" fields

    Returns:
        list[dict] — one entry per hotel found, sorted by Google's relevance ranking:
            {
                "name"       : str,         # hotel name
                "address"    : str,         # vicinity / street address
                "lat"        : float,       # latitude
                "lng"        : float,       # longitude
                "rating"     : float|None,  # Google rating (1-5), or None if not available
                "place_id"   : str,         # Google place ID for future API calls
                "place_type" : str,         # human-readable type, e.g. "Hotel", "Bed And Breakfast"
            }
    """
    # Calculate the centroid and dynamic radius from the destination spread
    centroid_lat, centroid_lng = _calculate_centroid(geocoded_destinations)
    radius_meters = _calculate_search_radius(geocoded_destinations)
    max_results = _max_hotel_results()
    print(f"DEBUG centroid: {centroid_lat:.6f}, {centroid_lng:.6f}", flush=True)
    print(f"DEBUG searching for up to {max_results} hotels within {radius_meters}m of centroid...", flush=True)

    try:
        # Call the Places Nearby Search API directly (same approach as geocoding)
        response = requests.get(
            f"{GOOGLE_MAPS_BASE_URL}/place/nearbysearch/json",
            params={
                "location": f"{centroid_lat},{centroid_lng}",
                "radius": radius_meters,
                "type": "lodging",   # covers hotels, boutique hotels, B&Bs, etc.
                "key": _api_key(),
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        if data["status"] not in ("OK", "ZERO_RESULTS"):
            # Unexpected API error status (e.g. REQUEST_DENIED, INVALID_REQUEST)
            raise RuntimeError(f"Places API error: {data['status']} — {data.get('error_message', '')}")

        hotels = []
        for place in data.get("results", [])[:max_results]:
            # Extract location coordinates from the nested geometry object
            location = place["geometry"]["location"]
            hotels.append({
                "name"        : place["name"],
                "address"     : place.get("vicinity", ""),      # vicinity is the street address in Nearby Search
                "lat"         : location["lat"],
                "lng"         : location["lng"],
                "rating"      : place.get("rating"),            # not always present — None if missing
                "place_id"    : place["place_id"],
                "place_type"  : _format_place_type(place.get("types", [])),  # e.g. "Hotel", "Bed And Breakfast"
                "price_level" : place.get("price_level"),       # int 0–4, or None if not available
                                                                # Note: price_level is rarely populated
                                                                # for hotels by Google's Places API —
                                                                # it is much more commonly available
                                                                # for restaurants. Most lodging results
                                                                # will return None here.
            })

        print(f"DEBUG found {len(hotels)} hotels near centroid", flush=True)
        return hotels

    except Exception as e:
        print(f"WARNING: hotel search failed: {e}", flush=True)
        raise


def _format_total_distance(meters: int, units: str) -> str:
    """
    Format a total walking distance in metres into a human-readable string
    using the correct unit system. Mirrors the style of the Distance Matrix
    API's distance_text field so the UI looks consistent.

    Inputs:
        meters (int) — total walking distance in metres
        units  (str) — "imperial" (miles) or "metric" (km)

    Returns:
        str — e.g. "2.3 mi" or "3.7 km"
    """
    if units == "imperial":
        # 1 metre = 0.000621371 miles
        miles = meters / 1609.344
        return f"{miles:.1f} mi"
    else:
        km = meters / 1000
        return f"{km:.1f} km"


def rank_hotels_by_walking_distance(
    hotels: list[dict],
    geocoded_destinations: list[dict],
    units: str = "metric",
) -> list[dict]:
    """
    Rank hotels by total walking distance to all destinations using the
    Google Maps Distance Matrix API. Makes a single API call with all hotels
    as origins and all destinations as destinations — the API handles the
    full matrix in one request.

    Inputs:
        hotels                (list[dict]) — hotels as returned by find_hotels_near_destinations(),
                                             each with "name", "lat", "lng" fields
        geocoded_destinations (list[dict]) — destinations as returned by geocode_destinations(),
                                             each with "name", "lat", "lng" fields
        units                 (str)        — "metric" (km) or "imperial" (miles); affects the
                                             human-readable distance_text field only —
                                             distance_m is always in metres regardless

    Returns:
        list[dict] — hotels sorted by total walking distance ascending (best first),
                     each hotel dict extended with:
            "total_walking_m"    (int)      — sum of walking distances to all destinations in metres
            "total_walking_text" (str)      — formatted total, e.g. "2.3 mi" or "3.7 km"
            "fully_reachable"    (bool)     — False if any destination had no walkable route
            "per_destination"  (list[dict]) — breakdown per destination:
                {
                    "label"         : str,       # map marker letter, e.g. "A", "B", "C"
                    "destination"   : str,       # destination name
                    "distance_m"    : int|None,  # walking distance in metres, None if unreachable
                    "distance_text" : str,        # human-readable distance e.g. "1.2 km" or "0.8 mi"
                    "duration_text" : str,        # human-readable walk time e.g. "15 mins"
                }
    """
    # The Distance Matrix API allows a maximum of 100 elements per request,
    # where elements = number of origins (hotels) × number of destinations.
    # Trim the hotel list if necessary so we stay within the limit.
    max_elements = 100
    max_hotels = max_elements // len(geocoded_destinations)
    if len(hotels) > max_hotels:
        print(f"DEBUG trimming hotels from {len(hotels)} to {max_hotels} to stay within Distance Matrix 100-element limit", flush=True)
        hotels = hotels[:max_hotels]

    # Build pipe-separated lat/lng strings — the Distance Matrix API format
    # e.g. "51.5007,-0.1246|51.5194,-0.1270"
    origins_str      = "|".join(f"{h['lat']},{h['lng']}" for h in hotels)
    destinations_str = "|".join(f"{d['lat']},{d['lng']}" for d in geocoded_destinations)

    print(f"DEBUG distance matrix: {len(hotels)} hotels × {len(geocoded_destinations)} destinations = {len(hotels) * len(geocoded_destinations)} elements", flush=True)

    response = requests.get(
        f"{GOOGLE_MAPS_BASE_URL}/distancematrix/json",
        params={
            "origins"      : origins_str,
            "destinations" : destinations_str,
            "mode"         : "walking",  # walking distance — most relevant for city tourism
            "units"        : units,      # "metric" → km, "imperial" → miles in distance_text
            "key"          : _api_key(),
        },
        timeout=15,  # Slightly longer timeout — larger payload than geocoding
    )
    response.raise_for_status()
    data = response.json()

    if data["status"] != "OK":
        raise RuntimeError(f"Distance Matrix API error: {data['status']} — {data.get('error_message', '')}")

    # Each row in data["rows"] corresponds to one hotel (origin),
    # each element within a row corresponds to one destination
    ranked = []
    for hotel, row in zip(hotels, data["rows"]):
        total_distance = 0
        per_destination = []
        fully_reachable = True

        for i, (dest, element) in enumerate(zip(geocoded_destinations, row["elements"])):
            # Map marker letter for this destination: A, B, C, ...
            label = chr(65 + i)
            if element["status"] == "OK":
                # Normal case — a walkable route exists
                dist_m = element["distance"]["value"]
                total_distance += dist_m
                per_destination.append({
                    "label"         : label,
                    "destination"   : dest["name"],
                    "distance_m"    : dist_m,
                    "distance_text" : element["distance"]["text"],
                    "duration_text" : element["duration"]["text"],
                })
            else:
                # No walkable route (e.g. island, motorway-only) — penalize heavily
                # so this hotel sorts to the bottom rather than crashing
                fully_reachable = False
                total_distance += 999_999
                per_destination.append({
                    "label"         : label,
                    "destination"   : dest["name"],
                    "distance_m"    : None,
                    "distance_text" : "N/A",
                    "duration_text" : "N/A",
                })

        ranked.append({
            **hotel,                           # carry over all existing hotel fields
            "total_walking_m"    : total_distance,
            "total_walking_text" : _format_total_distance(total_distance, units),
            "fully_reachable"    : fully_reachable,
            "per_destination"    : per_destination,
        })

    # Sort ascending — shortest total walk first
    ranked.sort(key=lambda h: h["total_walking_m"])
    print(f"DEBUG ranking complete — top hotel: {ranked[0]['name']} ({ranked[0]['total_walking_m']}m total)", flush=True)
    return ranked


def geocode_destinations(city: str, destination_names: list[str]) -> list[dict]:
    """
    Convert a list of destination names into geographic coordinates using
    the Google Maps Places Text Search API. Appends the city name to each
    query to disambiguate (e.g. "Colosseum" → "Colosseum, Rome").
    All destinations are geocoded in parallel to minimize total wait time.

    Uses Places Text Search (/place/textsearch/json) rather than the Geocoding
    API (/geocode/json) because Text Search is designed for named places and
    returns the same pin coordinates that Google Maps shows for landmarks.
    The Geocoding API sometimes returns a building centroid or nearby street
    address instead of the landmark pin, placing markers in the wrong location.

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
        Look up a single destination name via the Google Maps Places Text Search
        API, which returns the same pin coordinates that Google Maps displays for
        named landmarks — more accurate than the Geocoding API for attractions.

        Inputs:
            name (str) — the destination name to look up

        Returns:
            dict with name/address/lat/lng/place_id, or None on failure
        """
        # Append city to the query so Google disambiguates correctly —
        # "Tower of London" is unambiguous, but "Castle" or "Park" would not be
        query = f"{name}, {city}"
        print(f"DEBUG geocoding via Places Text Search: {query!r}", flush=True)

        try:
            # Places Text Search — designed for named places, returns landmark pins
            response = requests.get(
                f"{GOOGLE_MAPS_BASE_URL}/place/textsearch/json",
                params={"query": query, "key": _api_key()},
                timeout=10,  # Fail fast — 10 seconds max per request
            )
            response.raise_for_status()  # Raise an error for non-200 HTTP responses
            data = response.json()

            if data["status"] != "OK" or not data["results"]:
                # Google returned no results or an error status (e.g. ZERO_RESULTS)
                print(f"WARNING: no Places Text Search result for {query!r} (status: {data['status']}) — skipping", flush=True)
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
