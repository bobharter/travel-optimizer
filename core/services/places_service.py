import json
import os
import anthropic


def extract_and_normalize_destinations(city: str, free_text: str) -> list[str]:
    """
    Given a city and a free-text trip description, use Claude to:
    - Extract named destinations and fix typos
    - Resolve category intents (e.g. "good pasta") to a specific well-known place
      near one of the named destinations
    Returns a list of concrete, correctly-spelled place names.
    """
    print(f"DEBUG calling Claude for city={city!r}")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = f"""You are a travel assistant helping a user plan a trip to {city}.

The user has described their trip as follows:
"{free_text}"

Your job is to extract a list of specific destinations from this description. Follow these rules:
1. Extract all named places and fix any typos or misspellings (e.g. "Coliseum" → "Colosseum", "Vatcain" → "Vatican").
2. For any category or experience the user mentions (e.g. "good pasta", "a nice café", "local market"), choose one specific, well-known, highly-regarded place in {city} that fits that description AND is in the same neighborhood as one of the named destinations.
3. Return ONLY a JSON array of strings — the final list of concrete place names. No explanation, no extra text.

Example output format:
["Pantheon", "Colosseum", "Vatican Museums", "Trattoria Da Enzo al 29"]"""

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
