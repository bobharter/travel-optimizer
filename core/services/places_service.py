import json
import os
import anthropic


def extract_and_normalize_destinations(city: str, free_text: str) -> dict:
    """
    Given a city and a free-text trip description, use Claude to:
    - Extract named destinations and fix typos  → "named"
    - Resolve vague intents to specific places  → "recommended"
    Returns {"named": [...], "recommended": [...]}
    """
    print(f"DEBUG calling Claude for city={city!r}")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = f"""You are a travel assistant helping a user plan a trip to {city}.

The user has described their trip as follows:
"{free_text}"

Your job is to extract destinations from this description and categorize them into two groups:

1. "named": Places the user explicitly named (fix any typos or misspellings, e.g. "Coliseum" → "Colosseum"). Choose a specific well-known instance in {city} if needed.
2. "recommended": Places you are recommending based on vague or category descriptions (e.g. "biggest museum", "good pasta place", "a nice park"). For each, choose one specific, well-known, highly-regarded place in {city} that fits the description AND is near one of the named destinations if possible.

Return ONLY a JSON object in this exact format — no explanation, no extra text:
{{"named": ["Place One", "Place Two"], "recommended": ["Place Three"]}}

If there are no vague descriptions, return an empty array for "recommended"."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
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
