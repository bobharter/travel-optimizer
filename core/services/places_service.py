import json
import os
import anthropic


def extract_and_normalize_destinations(city: str, free_text: str) -> dict:
    """
    Given a city and a free-text trip description, use Claude to:
    - Extract named destinations and fix typos  → "named"
    - Resolve vague intents to specific places  → "recommended"
    Each destination has a "name" and a "category".
    Returns {"named": [...], "recommended": [...]}
    """
    print(f"DEBUG calling Claude for city={city!r}")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = f"""You are a travel assistant helping a user plan a trip to {city}.

The user described their trip as:
"{free_text}"

Extract all destinations and categorize them. For each destination provide:
- "name": the correct, properly spelled place name
- "category": a short, specific label like "Restaurant", "Art Museum", "Ancient Monument", "Park", "Cathedral", etc.

Split them into two groups:
- "named": places the user explicitly mentioned (fix any typos or misspellings)
- "recommended": places you are recommending based on vague or category descriptions (e.g. "best pasta", "biggest museum") — choose one specific, well-known, highly-regarded place in {city} that fits, near one of the named destinations if possible

Return ONLY this JSON, no explanation, no code fences:
{{"named": [{{"name": "Colosseum", "category": "Ancient Amphitheater"}}], "recommended": [{{"name": "Trattoria Da Enzo al 29", "category": "Restaurant"}}]}}

If there are no vague descriptions, return an empty array for "recommended"."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    print(f"DEBUG Claude raw response: {repr(raw)}")
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)
