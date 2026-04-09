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
            "name"     (str)       — correct, properly spelled place name
            "category" (str)       — short descriptive label, e.g. "Restaurant", "Art Museum"
            "url"      (str|None)  — official website URL if Claude is confident one exists,
                                     otherwise null
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
- "name": the correct, properly spelled place name
- "category": a short, specific label like "Restaurant", "Art Museum", "Ancient Monument", "Park", "Cathedral", etc.
- "url": the official website URL for the destination if you are confident it exists and is current (e.g. "https://colosseo.it"), or null if you are not sure

Split them into two groups:
- "named": places the user explicitly mentioned (fix any typos or misspellings)
- "recommended": places you are recommending based on vague or category descriptions (e.g. "best pasta", "biggest museum") — for each distinct category or experience the user mentions, choose one specific, well-known, highly-regarded place in {city} that fits, near one of the named destinations if possible. Treat each vague request separately — do not consolidate similar categories. For example, "best art galleries" and "highest-rated museums" must each produce their own distinct recommendation.

Return ONLY this JSON, no explanation, no code fences:
{{"named": [{{"name": "Colosseum", "category": "Ancient Amphitheater", "url": "https://colosseo.it"}}], "recommended": [{{"name": "Trattoria Da Enzo al 29", "category": "Restaurant", "url": null}}]}}

If there are no vague descriptions, return an empty array for "recommended"."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
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
