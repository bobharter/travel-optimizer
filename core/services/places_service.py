import json
import os
import socket
from urllib.parse import quote_plus

# OpenRouter exposes an OpenAI-compatible API, so we use the openai SDK
# pointed at OpenRouter's base URL instead of the Anthropic SDK.
from openai import OpenAI

# Force IPv4 for all socket connections in this process.
# Bob's machine tries IPv6 first, which hangs for ~40 seconds before falling
# back to IPv4. Patching socket.getaddrinfo at this low level covers all HTTP
# libraries including httpx (used internally by the openai SDK).
_original_getaddrinfo = socket.getaddrinfo
def _getaddrinfo_ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
    """Force IPv4 by overriding the address family to AF_INET."""
    return _original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _getaddrinfo_ipv4_only


# OpenRouter's API endpoint — drop-in replacement for OpenAI's base URL
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _get_model_list() -> list[str]:
    """
    Read the comma-separated LLM_MODEL_LIST env var and return it as a list.

    Returns:
        list[str] — model identifiers in priority order, e.g.:
                    ["google/gemini-2.5-flash", "openai/gpt-4o-mini", "anthropic/claude-haiku-4-5"]
                    Falls back to a sensible default if the env var is missing.
    """
    raw = os.environ.get("LLM_MODEL_LIST", "google/gemini-2.5-flash,openai/gpt-4o-mini")
    # Strip whitespace around commas so spacing in the env var doesn't matter
    return [m.strip() for m in raw.split(",") if m.strip()]


def _google_search_url(name: str, city: str) -> str:
    """
    Generate a Google search URL for a destination name and city.
    Used instead of LLM-generated URLs, which are unreliable and often link
    to parked domains or hallucinated addresses.

    Inputs:
        name (str) — destination name, e.g. "Tuscania Cooking School"
        city (str) — city the user is visiting, e.g. "Rome, Italy"

    Returns:
        str — a Google search URL, e.g.:
              "https://www.google.com/search?q=Tuscania+Cooking+School+Rome%2C+Italy"
    """
    query = quote_plus(f"{name} {city}")
    return f"https://www.google.com/search?q={query}"


def extract_and_normalize_destinations(city: str, free_text: str) -> dict:
    """
    Use an LLM (via OpenRouter) to extract and normalize travel destinations
    from a free-text trip description. Tries each model in LLM_MODEL_LIST in
    order, falling back to the next if one fails.

    Inputs:
        city      (str) — the city the user is traveling to (e.g. "Rome, Italy")
        free_text (str) — the user's raw trip description, which may contain typos,
                          vague requests, or a mix of specific and general interests

    Returns:
        dict with two keys:
            "named"       — list of destinations the user explicitly mentioned,
                            with typos corrected
            "recommended" — list of specific places the LLM recommends for any vague
                            requests (e.g. "best pasta", "biggest museum")

        Each destination in both lists is a dict with:
            "name"         (str)       — correct, properly spelled place name (best guess
                                         when the input is ambiguous)
            "category"     (str)       — short descriptive label, e.g. "Restaurant", "Art Museum"
            "url"          (str)       — Google search URL generated from the destination name
                                         and city (not from the LLM — LLM-generated URLs are
                                         unreliable and often link to parked/wrong domains)
            "alternatives" (list[dict]) — if the user's input was ambiguous and could match
                                          multiple real places, a list of candidate objects
                                          each with "name", "category", and "url" fields.
                                          The chosen "name" entry appears first.
                                          Empty list when there is no ambiguity.

    Raises:
        RuntimeError — if all models in the fallback list fail
    """
    # Build the OpenRouter client — same interface as the OpenAI SDK
    client = OpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url=OPENROUTER_BASE_URL,
    )

    # Build the prompt once — it's the same regardless of which model handles it.
    # We ask the model to split results into "named" vs "recommended" so the UI
    # can present them differently (confirmed vs suggested).
    # The url field is optional — the model should return null rather than guess.
    # The alternatives field lets the user disambiguate when the input was vague.
    prompt = f"""You are a travel assistant helping a user plan a trip to {city}.

The user described their trip as:
"{free_text}"

Extract all destinations and categorize them. For each destination provide:
- "name": the correct, properly spelled place name (your best guess if ambiguous)
- "category": a short, specific label like "Restaurant", "Art Museum", "Ancient Monument", "Park", "Cathedral", etc.
- "alternatives": ONLY populate this if the user's input was genuinely ambiguous and matches 2 or more distinct real places. List all plausible candidates as objects with "name" and "category" fields — include the chosen "name" entry first. Use an empty array [] for any destination that has one clear match — do NOT put a single-entry array.

Split them into two groups:
- "named": places the user explicitly mentioned (fix any typos or misspellings)
- "recommended": places you are recommending based on vague or category descriptions (e.g. "best pasta", "biggest museum") — for each distinct category or experience the user mentions, choose one specific, well-known, highly-regarded place in {city} that fits, near one of the named destinations if possible. Treat each vague request separately — do not consolidate similar categories. For example, "best art galleries" and "highest-rated museums" must each produce their own distinct recommendation.

Return ONLY this JSON, no explanation, no code fences:
{{"named": [{{"name": "Millennium Eye", "category": "Observation Wheel", "alternatives": [{{"name": "Millennium Eye", "category": "Observation Wheel"}}, {{"name": "Millennium Bridge", "category": "Landmark Bridge"}}, {{"name": "Millennium Dome", "category": "Entertainment Venue"}}]}}], "recommended": [{{"name": "Trattoria Da Enzo al 29", "category": "Restaurant", "alternatives": []}}]}}

If there are no vague descriptions, return an empty array for "recommended"."""

    # Try each model in the fallback list in order.
    # If a model fails (API error, bad JSON, etc.), log it and try the next one.
    models = _get_model_list()
    last_error = None

    for model in models:
        print(f"DEBUG trying model: {model}")
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=2048,  # Generous limit — alternatives arrays with full objects can be lengthy
                messages=[{"role": "user", "content": prompt}],
            )

            raw = response.choices[0].message.content.strip()
            print(f"DEBUG raw response from {model}: {repr(raw)}")

            # Strip markdown code fences if the model wraps the JSON despite being told not to
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            # If JSON parses successfully, inject Google search URLs for every
            # destination and alternative. We generate these ourselves rather than
            # trusting the LLM — LLM-generated URLs are unreliable and often link
            # to parked domains or hallucinated addresses.
            result = json.loads(raw)
            for group in ("named", "recommended"):
                for dest in result.get(group, []):
                    dest["url"] = _google_search_url(dest["name"], city)
                    for alt in dest.get("alternatives", []):
                        alt["url"] = _google_search_url(alt["name"], city)
            print(f"DEBUG success with model: {model}")
            return result

        except Exception as e:
            # Log the failure and try the next model in the list
            print(f"DEBUG model {model} failed: {e}")
            last_error = e
            continue

    # All models failed — surface the last error so the view can show a message to the user
    raise RuntimeError(f"All models in LLM_MODEL_LIST failed. Last error: {last_error}")
