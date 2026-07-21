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
        ww = w if w > 0 else 1e-9
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
    else:  # diagnostic (adaptive: prefers weak KCs when any learning record exists)
        has_record = any(kc_states[i].get("teaching_state") != "unseen" for i in ids)
        if has_record:
            weights = [WEAKNESS_SCORE.get(kc_states[i].get("teaching_state"), 0.0) for i in ids]
        else:
            weights = [kc_states[i].get("exam_weight", 0.5) for i in ids]
    return _weighted_sample_no_replace(rng, ids, weights, min(count, len(ids)))


def gather_questions(
    questions: dict, kc_ids: list[str], per_kc: int = 2, total: int | None = None
) -> tuple[list[dict], dict[str, int]]:
    total = total if total is not None else per_kc * max(1, len(kc_ids))
    by_kc: dict[str, list[dict]] = {k: [] for k in kc_ids}
    for q in questions.values():
        for k in q.get("kc_ids", []):
            if k in by_kc and len(by_kc[k]) < per_kc:
                by_kc[k].append(q)
    picked: list[dict] = []
    seen: set = set()
    i = 0
    while len(picked) < total:
        progressed = False
        for k in kc_ids:
            if i < len(by_kc[k]):
                progressed = True
                q = by_kc[k][i]
                qid = q.get("question_id")
                if qid not in seen:
                    seen.add(qid)
                    picked.append(q)
                    if len(picked) >= total:
                        break
        if not progressed:
            break
        i += 1
    shortfall = {k: per_kc - len(by_kc[k]) for k in kc_ids if len(by_kc[k]) < per_kc}
    return picked, shortfall
