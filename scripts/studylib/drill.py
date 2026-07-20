from __future__ import annotations

import random

from .nextstep import WEAKNESS_SCORE


def _weighted_sample_no_replace(
    rng: random.Random, items: list[str], weights: list[float], k: int
) -> list[str]:
    if k >= len(items):
        return list(items)
    # Efraimidis–Spirakis: key = u**(1/w); take the k largest keys.
    pairs = []
    for it, w in zip(items, weights):
        ww = w if w and w > 0 else 1e-9
        pairs.append((rng.random() ** (1.0 / ww), it))
    pairs.sort(key=lambda p: p[0], reverse=True)
    return [it for _, it in pairs[:k]]


def select_kcs(kc_states: dict[str, dict], mode: str, count: int, seed: int = 0) -> list[str]:
    if mode not in ("syllabus", "diagnostic"):
        raise ValueError(f"unknown mode: {mode}")
    ids = list(kc_states)
    if not ids or count <= 0:
        return []
    rng = random.Random(seed)
    if mode == "syllabus":
        weights = [kc_states[i].get("exam_weight", 0.5) for i in ids]
    else:  # diagnostic, adaptive
        has_record = any(kc_states[i].get("teaching_state") != "unseen" for i in ids)
        if has_record:
            weights = [WEAKNESS_SCORE.get(kc_states[i].get("teaching_state"), 0.0) for i in ids]
        else:
            weights = [kc_states[i].get("exam_weight", 0.5) for i in ids]
    return _weighted_sample_no_replace(rng, ids, weights, min(count, len(ids)))
