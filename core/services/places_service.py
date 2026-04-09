import json
import os
import anthropic


def extract_and_normalize_destinations(city: str, free_text: str) -> dict:
    """
    Use Claude to extract and normalize travel destinations from a free-text trip description.

    Inputs:
        city      (str) — the city the user is traveling to (e.g. "Rome, Italy")
        free_text (str) — the user's raw trip description, which may contain typos,
                          vague requests, or a mix of specific and general interests

    Returns:
        dict with two keys:
            "named"       — list of destinations the user explicitly mentioned,
                            with typos corrected
            "recommended" — list of specific places Claude recommends for any vague
                            requests (e.g. "best pasta", "biggest museum")

        Each destination in both lists is a dict with:
            "name"         (str)        — correct, properly spelled place name (Claude's best guess
                                          when the input is ambiguous)
            "category"     (str)        — short descriptive label, e.g. "Restaurant", "Art Museum"
            "url"          (str|None)   — official website URL if Claude is confident one exists,
                                          otherwise null
            "alternatives" (list[dict])  — if the user's input was ambiguous and could match
                                           multiple real places, a list of candidate objects
                                           each with "name", "category", and "url" fields
                                           (url may be null). The chosen "name" entry appears
                                           first. Empty list when there is no ambiguity.
    """
    print(f"DEBUG calling Claude for city={city!r}")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Build the prompt. We ask Claude to split results into "named" vs "recommended"
    # so the UI can present them differently (confirmed vs suggested).
    # The url field is optional — Claude should return null rather than guess.
    prompt = f"""You are a travel assistant helping a user plan a trip to {city}.

The user described their trip as:
"{free_text}"

Extract all destinations and categorize them. For each destination provide:
- "name": the correct, properly spelled place name (your best guess if ambiguous)
- "category": a short, specific label like "Restaurant", "Art Museum", "Ancient Monument", "Park", "Cathedral", etc.
- "url": the official website URL for the destination if you are confident it exists and is current (e.g. "https://colosseo.it"), or null if you are not sure
- "alternatives": if the user's input was ambiguous and could reasonably match multiple distinct real places, list all plausible candidates as objects with "name", "category", and "url" fields (url may be null) — include the chosen "name" entry first. Use an empty array [] when there is no meaningful ambiguity.

Split them into two groups:
- "named": places the user explicitly mentioned (fix any typos or misspellings)
- "recommended": places you are recommending based on vague or category descriptions (e.g. "best pasta", "biggest museum") — for each distinct category or experience the user mentions, choose one specific, well-known, highly-regarded place in {city} that fits, near one of the named destinations if possible. Treat each vague request separately — do not consolidate similar categories. For example, "best art galleries" and "highest-rated museums" must each produce their own distinct recommendation.

Return ONLY this JSON, no explanation, no code fences:
{{"named": [{{"name": "Millennium Eye", "category": "Observation Wheel", "url": "https://www.londoneye.com", "alternatives": [{{"name": "Millennium Eye", "category": "Observation Wheel", "url": "https://www.londoneye.com"}}, {{"name": "Millennium Bridge", "category": "Landmark Bridge", "url": "https://www.tate.org.uk/visit/tate-modern/millennium-bridge"}}, {{"name": "Millennium Dome", "category": "Entertainment Venue", "url": "https://www.theo2.co.uk"}}]}}], "recommended": [{{"name": "Trattoria Da Enzo al 29", "category": "Restaurant", "url": null, "alternatives": []}}]}}

If there are no vague descriptions, return an empty array for "recommended"."""

    # Model is configured via ANTHROPIC_MODEL env var — swap in .env to change without touching code
    model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
    print(f"DEBUG using model: {model}")
    message = client.messages.create(
        model=model,
        max_tokens=2048,  # Increased from 512 — alternatives arrays with full objects can be lengthy
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    print(f"DEBUG Claude raw response: {repr(raw)}")
    # Strip markdown code fences if Claude wraps the JSON despite being told not to
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)
