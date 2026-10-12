"""End-to-end scan: segment → measure → classify → fuse → shelf life."""
import time

from . import vision
from .classifier import NOT_PRODUCE, get_classifier
from .produce import PRODUCE, action_for, fuse, ripeness_from_colour, shelf_life, stage_of


def _hex_to_bgr(h: str) -> tuple:
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return (b, g, r)


def scan(image_bytes: bytes, storage: str = "counter") -> dict:
    t0 = time.perf_counter()
    img = vision.load_image(image_bytes)
    fg = vision.segment(img)
    regions = vision.split_items(img, fg)
    for r in regions:
        vision.colour_metrics(img, r)
    t_cv = time.perf_counter()

    preds = get_classifier().classify([r.crop for r in regions])
    t_clip = time.perf_counter()

    items, keep, colours, labels = [], [], [], []
    for r, pred in zip(regions, preds):
        if pred["name"] == NOT_PRODUCE or pred["confidence"] < 0.12:
            continue
        p = PRODUCE[pred["name"]]
        cv_score = ripeness_from_colour(p, r.metrics)
        score = fuse(p, cv_score, pred["condition_probs"])
        stage, colour = stage_of(score)
        life = shelf_life(p, score, storage)
        items.append({
            "id": len(items) + 1,
            "name": p.name,
            "emoji": p.emoji,
            "confidence": pred["confidence"],
            "alternatives": pred["alternatives"],
            "ripeness": score,
            "cv_score": round(cv_score, 1),
            "clip_probs": pred["condition_probs"],
            "stage": stage,
            "stage_colour": colour,
            **life,
            **action_for(p, score, storage, life),
            "metrics": r.metrics,
            "thumb": vision.to_jpeg_b64(r.crop),
        })
        keep.append(r)
        colours.append(_hex_to_bgr(colour))
        labels.append(f"#{len(items)} {p.name} {score:.0f}")

    overlay = vision.render_overlay(img, keep, colours, labels)
    items.sort(key=lambda i: i["days_left"])
    return {
        "items": items,
        "overlay": vision.to_jpeg_b64(overlay),
        "original": vision.to_jpeg_b64(img),
        "timing_ms": {
            "vision": round(1000 * (t_cv - t0)),
            "clip": round(1000 * (t_clip - t_cv)),
        },
        "regions_found": len(regions),
    }
