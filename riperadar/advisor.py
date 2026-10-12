"""Turns the vision results into a 'use it up' plan with Gemini, with an offline fallback."""
import json
import os

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

FALLBACK_IDEAS = {
    "banana": "Overripe bananas make the best banana bread, smoothies or frozen 'nice cream'.",
    "tomato": "Soft tomatoes are perfect for pasta sauce, shakshuka or soup.",
    "avocado": "Very ripe avocado → guacamole or a chocolate-avocado mousse.",
    "strawberry": "Soft strawberries → jam, smoothie or a quick compote for yogurt.",
    "apple": "Wrinkly apples → applesauce, crumble or baked cinnamon apples.",
    "mango": "Overripe mango → lassi, sorbet or chutney.",
    "pear": "Soft pears → poached pears or a pear crumble.",
    "peach": "Soft peaches → cobbler, grilled peaches or smoothie.",
    "broccoli": "Yellowing broccoli → soup, stir-fry or roasted with garlic.",
    "lettuce": "Wilting lettuce → soak in ice water 10 min to revive, or add to soup.",
    "bread": "Stale bread → croutons, French toast or bread pudding (only if no mould!).",
}


def _fallback(items: list[dict]) -> dict:
    urgent = sorted(items, key=lambda i: i["days_left"])
    ideas = [FALLBACK_IDEAS[i["name"]] for i in urgent if i["name"] in FALLBACK_IDEAS and i["ripeness"] >= 60]
    return {
        "source": "offline",
        "summary": "Eat the items with the fewest days left first." if items else "No produce detected.",
        "recipe": None,
        "ideas": list(dict.fromkeys(ideas))[:3],
    }


def make_plan(items: list[dict], storage: str) -> dict:
    items = [i for i in items if i["name"] != "not_produce"]
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key or not items:
        return _fallback(items)
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=key)
        facts = [
            {k: i[k] for k in ("name", "stage", "ripeness", "days_left", "days_to_ripe")}
            | {"spot_coverage_pct": round(100 * i["metrics"]["spot_coverage"])}
            for i in items
        ]
        prompt = (
            "You are a food-waste coach. A computer-vision scan of someone's produce "
            f"(stored on the {storage}) found these items (ripeness 0=unripe, 100=spoiled):\n"
            f"{json.dumps(facts)}\n\n"
            "Return JSON with keys: summary (1-2 friendly sentences on what to eat first and why), "
            "recipe (object with title, minutes, ingredients[list of short strings], steps[3-5 short strings]) "
            "that uses the MOST urgent items, or null if nothing is ripe yet; "
            "ideas (2-3 short extra tips to avoid waste for these exact items). "
            "Never suggest eating items with stage 'Spoiled'."
        )
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.6),
        )
        plan = json.loads(resp.text)
        plan["source"] = "gemini"
        return plan
    except Exception as e:  # network/quota errors should never break the scan
        plan = _fallback(items)
        plan["error"] = str(e)[:200]
        return plan
