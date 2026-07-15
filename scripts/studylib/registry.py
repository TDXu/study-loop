from __future__ import annotations

from .errors import UnknownKC


def build_kcs(events: list[dict]) -> dict[str, dict]:
    kcs: dict[str, dict] = {}
    for e in events:
        t = e["event_type"]
        p = e["payload"]
        if t == "kc_created":
            kcs[p["kc_id"]] = {
                "kc_id": p["kc_id"],
                "name": p.get("name", p["kc_id"]),
                "chapter_id": p.get("chapter_id"),
                "prerequisites": list(p.get("prerequisites", [])),
                "exam_weight": float(p.get("exam_weight", 0.5)),
                "source_ids": list(p.get("source_ids", [])),
                "explained": False,
            }
        elif t == "kc_updated":
            kc = kcs.get(p["kc_id"])
            if kc is None:
                raise UnknownKC(f"kc_updated for unknown kc_id: {p['kc_id']}")
            if p.get("update") == "explained":
                kc["explained"] = True
            for field in ("name", "exam_weight", "prerequisites", "chapter_id"):
                if field in p:
                    kc[field] = p[field]
    return kcs


def build_questions(events: list[dict]) -> dict[str, dict]:
    qs: dict[str, dict] = {}
    for e in events:
        if e["event_type"] in ("question_registered", "transfer_test_created"):
            p = e["payload"]
            qs[p["question_id"]] = p
    return qs


def build_sources(events: list[dict]) -> list[dict]:
    return [e["payload"] for e in events if e["event_type"] == "source_registered"]
