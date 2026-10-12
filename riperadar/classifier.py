"""Zero-shot produce identification and condition scoring with CLIP (CPU)."""
import threading

import numpy as np
import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

from .produce import PRODUCE

MODEL_ID = "openai/clip-vit-base-patch32"
NOT_PRODUCE = "not_produce"

TYPE_TEMPLATES = ["a photo of a {}.", "a close-up photo of a {}, food.", "a {} on a kitchen table."]
NEGATIVE_PROMPTS = ["a photo of a person.", "a photo of an empty table.", "a photo of a room.",
                    "a photo of a phone or electronics.", "a screenshot with text."]
CONDITION_TEMPLATES = [
    ["a photo of an unripe, hard, green {}.", "a photo of an underripe {}."],
    ["a photo of a fresh, perfectly ripe {}.", "a photo of a ripe {} ready to eat."],
    ["a photo of an overripe {} with brown spots.", "a photo of a very soft, bruised {}."],
    ["a photo of a rotten, moldy {}.", "a photo of a spoiled, decaying {}."],
]


class ProduceClassifier:
    def __init__(self):
        torch.set_num_threads(max(1, torch.get_num_threads()))
        self.model = CLIPModel.from_pretrained(MODEL_ID).eval()
        self.proc = CLIPProcessor.from_pretrained(MODEL_ID)
        self.names = list(PRODUCE)
        self.scale = self.model.logit_scale.exp().item()
        self._cond_cache: dict[str, torch.Tensor] = {}
        with torch.no_grad():
            per_type = [self._embed_text([t.format(n) for t in TYPE_TEMPLATES]).mean(0) for n in self.names]
            neg = self._embed_text(NEGATIVE_PROMPTS).mean(0)
            self.type_emb = self._norm(torch.stack(per_type + [neg]))

    @staticmethod
    def _norm(x):
        return x / x.norm(dim=-1, keepdim=True)

    def _embed_text(self, texts):
        inputs = self.proc(text=texts, return_tensors="pt", padding=True)
        return self._norm(self.model.get_text_features(**inputs))

    def _condition_emb(self, name):
        if name not in self._cond_cache:
            with torch.no_grad():
                embs = [self._embed_text([t.format(name) for t in group]).mean(0) for group in CONDITION_TEMPLATES]
            self._cond_cache[name] = self._norm(torch.stack(embs))
        return self._cond_cache[name]

    @torch.no_grad()
    def classify(self, crops_bgr: list[np.ndarray]) -> list[dict]:
        if not crops_bgr:
            return []
        images = [Image.fromarray(c[..., ::-1]) for c in crops_bgr]
        inputs = self.proc(images=images, return_tensors="pt")
        img_emb = self._norm(self.model.get_image_features(**inputs))

        type_probs = (self.scale * img_emb @ self.type_emb.T).softmax(-1)
        results = []
        for i in range(len(images)):
            probs = type_probs[i]
            top = torch.topk(probs, 3)
            idx = int(top.indices[0])
            name = self.names[idx] if idx < len(self.names) else NOT_PRODUCE
            alts = [
                {"name": self.names[j] if j < len(self.names) else NOT_PRODUCE, "p": round(float(p), 3)}
                for p, j in zip(top.values.tolist(), top.indices.tolist())
            ]
            cond = [0.25] * 4
            if name != NOT_PRODUCE:
                cond_logits = self.scale * img_emb[i] @ self._condition_emb(name).T
                cond = cond_logits.softmax(-1).tolist()
            results.append({"name": name, "confidence": round(float(top.values[0]), 3),
                            "alternatives": alts, "condition_probs": [round(c, 3) for c in cond]})
        return results


_instance = None
_lock = threading.Lock()


def get_classifier() -> ProduceClassifier:
    global _instance
    with _lock:
        if _instance is None:
            _instance = ProduceClassifier()
    return _instance
