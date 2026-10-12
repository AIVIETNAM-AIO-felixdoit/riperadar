"""Classical computer-vision pipeline: produce segmentation, colour profiling and
spot/bruise detection. Runs on CPU in well under a second for a 640px image."""
from dataclasses import dataclass, field

import cv2
import numpy as np

MAX_SIDE = 640
MIN_ITEM_FRAC = 0.015  # ignore blobs smaller than 1.5% of the frame
MAX_ITEMS = 8


@dataclass
class ItemRegion:
    contour: np.ndarray
    mask: np.ndarray  # full-frame uint8 mask (0/255)
    bbox: tuple  # x, y, w, h
    crop: np.ndarray  # BGR crop with background dimmed
    metrics: dict = field(default_factory=dict)
    spot_mask: np.ndarray | None = None


def load_image(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image")
    h, w = img.shape[:2]
    scale = MAX_SIDE / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return img


def _border_mask(h, w, frac=0.04):
    b = max(2, int(min(h, w) * frac))
    m = np.zeros((h, w), bool)
    m[:b], m[-b:], m[:, :b], m[:, -b:] = True, True, True, True
    return m


def segment(img: np.ndarray) -> np.ndarray:
    """Foreground mask of produce. Background colour is estimated from the frame
    border, colour distance seeds GrabCut, then morphology cleans it up."""
    h, w = img.shape[:2]
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    border = _border_mask(h, w)
    bg = np.median(lab[border], axis=0)
    dist = np.linalg.norm(lab - bg, axis=2)
    # Saturated pixels are a strong produce prior against table/wall backgrounds
    sat = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[..., 1].astype(np.float32)
    score = dist + 0.35 * sat
    score_u8 = cv2.normalize(score, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    score_u8 = cv2.GaussianBlur(score_u8, (5, 5), 0)
    t, _ = cv2.threshold(score_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    gc = np.full((h, w), cv2.GC_PR_BGD, np.uint8)
    gc[score_u8 > t] = cv2.GC_PR_FGD
    gc[score_u8 > min(254, t * 1.6)] = cv2.GC_FGD
    gc[border] = cv2.GC_BGD

    if (gc == cv2.GC_PR_FGD).sum() + (gc == cv2.GC_FGD).sum() < 0.01 * h * w:
        # Nothing stands out: assume the subject is centred
        gc[:] = cv2.GC_BGD
        gc[h // 8: -h // 8, w // 8: -w // 8] = cv2.GC_PR_FGD

    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(img, gc, None, bgd, fgd, 4, cv2.GC_INIT_WITH_MASK)
    except cv2.error:
        pass
    fg = np.where((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    return fg


def split_items(img: np.ndarray, fg: np.ndarray) -> list[ItemRegion]:
    h, w = fg.shape
    contours, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = [c for c in contours if cv2.contourArea(c) >= MIN_ITEM_FRAC * h * w]
    contours.sort(key=cv2.contourArea, reverse=True)
    if not contours:
        # Fall back to the whole frame so the classifier still gets a look
        contours = [np.array([[[0, 0]], [[w - 1, 0]], [[w - 1, h - 1]], [[0, h - 1]]], np.int32)]

    items = []
    for c in contours[:MAX_ITEMS]:
        mask = np.zeros((h, w), np.uint8)
        cv2.drawContours(mask, [c], -1, 255, cv2.FILLED)  # fills holes too
        x, y, bw, bh = cv2.boundingRect(c)
        pad = int(0.08 * max(bw, bh))
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(w, x + bw + pad), min(h, y + bh + pad)
        crop = img[y0:y1, x0:x1].copy()
        m = mask[y0:y1, x0:x1]
        # Dim (not erase) the background so CLIP keeps some context
        crop[m == 0] = (crop[m == 0] * 0.35 + 255 * 0.65).astype(np.uint8)
        items.append(ItemRegion(contour=c, mask=mask, bbox=(x, y, bw, bh), crop=crop))
    return items


def colour_metrics(img: np.ndarray, item: ItemRegion) -> None:
    """Fill item.metrics with colour fractions and dark-spot coverage."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    # Erode so edge shadows are not counted as bruises
    k = max(3, int(0.03 * max(item.bbox[2], item.bbox[3])) | 1)
    inner = cv2.erode(item.mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))) > 0
    if inner.sum() < 50:
        inner = item.mask > 0
    n = max(1, int(inner.sum()))

    v_med = float(np.median(V[inner]))
    # Dark spots: much darker than the item's own median brightness, or
    # brown (orange hue, low brightness) patches typical of bruising/ageing
    dark = V < 0.58 * v_med
    brown = (H >= 4) & (H <= 24) & (S > 70) & (V < 0.72 * v_med)
    spots = ((dark | brown) & inner).astype(np.uint8) * 255
    spots = cv2.morphologyEx(spots, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n_spots, _, stats, _ = cv2.connectedComponentsWithStats(spots)
    spot_count = int(sum(1 for s in stats[1:] if s[cv2.CC_STAT_AREA] >= 6))
    spot_cov = float((spots > 0).sum()) / n

    clean = inner & (spots == 0)
    nc = max(1, int(clean.sum()))
    vivid = S > 55
    green = ((H >= 33) & (H <= 90) & vivid & clean).sum() / nc
    yellow = ((H >= 18) & (H < 33) & vivid & clean).sum() / nc
    red = (((H < 18) | (H >= 160)) & vivid & clean).sum() / nc
    dull = ((~vivid) & clean).sum() / nc

    mean_bgr = cv2.mean(img, mask=inner.astype(np.uint8))[:3]
    item.spot_mask = spots
    item.metrics = {
        "green": round(float(green), 3),
        "yellow": round(float(yellow), 3),
        "red": round(float(red), 3),
        "dull": round(float(dull), 3),
        "spot_coverage": round(spot_cov, 3),
        "spot_count": spot_count,
        "mean_hex": "#%02x%02x%02x" % (int(mean_bgr[2]), int(mean_bgr[1]), int(mean_bgr[0])),
        "area_frac": round(float((item.mask > 0).sum()) / item.mask.size, 3),
    }


def render_overlay(img: np.ndarray, items: list[ItemRegion], colours: list[tuple], labels: list[str]) -> np.ndarray:
    out = img.copy()
    shade = (out * 0.45).astype(np.uint8)
    fg_any = np.zeros(img.shape[:2], bool)
    for it in items:
        fg_any |= it.mask > 0
    out[~fg_any] = shade[~fg_any]
    for it, col, label in zip(items, colours, labels):
        if it.spot_mask is not None:
            heat = it.spot_mask > 0
            out[heat] = (out[heat] * 0.3 + np.array([40, 40, 230]) * 0.7).astype(np.uint8)
        cv2.drawContours(out, [it.contour], -1, col, 3, cv2.LINE_AA)
        x, y, _, _ = it.bbox
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        ty = max(th + 8, y)
        cv2.rectangle(out, (x, ty - th - 8), (x + tw + 10, ty), col, cv2.FILLED)
        cv2.putText(out, label, (x + 5, ty - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 2, cv2.LINE_AA)
    return out


def to_jpeg_b64(img: np.ndarray) -> str:
    import base64

    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()
