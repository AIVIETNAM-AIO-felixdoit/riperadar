"""Produce knowledge base and the ripeness fusion model."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Produce:
    name: str
    emoji: str
    green_means_unripe: bool  # skin turns from green as it ripens
    yellow_means_decay: bool  # leafy greens / broccoli yellow as they age
    counter_days: float  # shelf life at peak ripeness
    fridge_days: float
    ripen_days: float  # counter days from fully unripe to ripe
    fridge_ok_unripe: bool = False  # does cold storage stop ripening (bad for unripe)


PRODUCE = {
    p.name: p
    for p in [
        Produce("banana", "🍌", True, False, 5, 7, 5),
        Produce("apple", "🍎", False, False, 10, 45, 0, True),
        Produce("tomato", "🍅", True, False, 5, 9, 5),
        Produce("avocado", "🥑", False, False, 3, 7, 5),
        Produce("strawberry", "🍓", True, False, 2, 6, 2, True),
        Produce("orange", "🍊", False, False, 10, 28, 0, True),
        Produce("lemon", "🍋", False, False, 7, 28, 0, True),
        Produce("mango", "🥭", True, False, 4, 10, 5),
        Produce("pear", "🍐", False, False, 4, 12, 4),
        Produce("grapes", "🍇", False, False, 3, 10, 0, True),
        Produce("peach", "🍑", False, False, 3, 6, 3),
        Produce("kiwi", "🥝", False, False, 5, 21, 5),
        Produce("bell pepper", "🫑", False, False, 5, 12, 0, True),
        Produce("broccoli", "🥦", False, True, 2, 10, 0, True),
        Produce("lettuce", "🥬", False, True, 2, 7, 0, True),
        Produce("cucumber", "🥒", False, True, 3, 8, 0, True),
        Produce("carrot", "🥕", False, False, 5, 25, 0, True),
        Produce("bread", "🍞", False, False, 4, 7, 0, True),
    ]
}

STAGES = [
    (0, "Unripe", "#5fae4a"),
    (30, "Ripe", "#e9c53a"),
    (60, "Very ripe", "#e39a2d"),
    (80, "Overripe", "#b5651d"),
    (92, "Spoiled", "#6b3f22"),
]

# Expected ripeness score for each CLIP condition prompt
CLIP_CONDITION_SCORES = [12, 45, 78, 97]


def ripeness_from_colour(p: Produce, m: dict) -> float:
    decay = m["spot_coverage"] + (0.7 * m["yellow"] if p.yellow_means_decay else 0)
    decay_part = 45 * min(decay / 0.4, 1.0)
    if p.green_means_unripe:
        coloured = m["yellow"] + m["red"] + m["green"]
        green_share = m["green"] / coloured if coloured > 0.05 else 0.0
        base = 55 * (1 - green_share)
    else:
        base = 40
    return min(100.0, base + decay_part)


def fuse(p: Produce, cv_score: float, clip_probs: list[float]) -> float:
    clip_score = sum(pr * s for pr, s in zip(clip_probs, CLIP_CONDITION_SCORES))
    # Colour rules are most reliable for skins that change colour as they ripen
    w_cv = 0.5 if p.green_means_unripe else 0.35
    score = w_cv * cv_score + (1 - w_cv) * clip_score
    return round(max(0.0, min(100.0, score)), 1)


def stage_of(score: float) -> tuple[str, str]:
    label, colour = STAGES[0][1], STAGES[0][2]
    for threshold, l, c in STAGES:
        if score >= threshold:
            label, colour = l, c
    return label, colour


def shelf_life(p: Produce, score: float, storage: str) -> dict:
    """Days until ripe (if unripe) and days of good eating left."""
    total = p.fridge_days if storage == "fridge" else p.counter_days
    days_to_ripe = 0.0
    if score < 30 and p.ripen_days:
        days_to_ripe = p.ripen_days * (30 - score) / 30
        if storage == "fridge" and not p.fridge_ok_unripe:
            days_to_ripe *= 2.5  # cold slows ripening a lot
    remaining = max(0.0, (100 - max(score, 30)) / 70)
    days_left = days_to_ripe + total * remaining ** 1.3
    return {"days_to_ripe": round(days_to_ripe, 1), "days_left": round(days_left, 1)}


def action_for(p: Produce, score: float, storage: str, life: dict) -> dict:
    if score >= 92:
        return {"verdict": "Compost it", "icon": "♻️",
                "tip": "Past safe eating. Compost it, and check items it touched for mould."}
    if score >= 80:
        return {"verdict": "Use today: cook, bake or freeze", "icon": "🔥",
                "tip": f"Too soft to enjoy raw, but great cooked. Freezing now buys months."}
    if score >= 60:
        return {"verdict": "Eat within a day or two", "icon": "⏰",
                "tip": "Peak sweetness. Move it to the front of the fridge so it gets eaten first."}
    if score >= 30:
        tip = "Ready to eat."
        if storage == "counter" and p.fridge_days > p.counter_days * 1.3:
            tip += f" Refrigerate to stretch it to ~{round(p.fridge_days * (100 - score) / 70)} days."
        return {"verdict": "Ready to eat", "icon": "✅", "tip": tip}
    tip = f"Ripens in about {life['days_to_ripe']:.0f} day(s) on the counter."
    if p.ripen_days:
        tip += f" A paper bag next to a ripe banana speeds it up."
        if storage == "fridge" and not p.fridge_ok_unripe:
            tip = "The fridge stalls ripening, so leave it on the counter until it's ripe."
    return {"verdict": "Not ready yet: wait", "icon": "⏳", "tip": tip}
