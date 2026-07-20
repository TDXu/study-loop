from __future__ import annotations

from .display import kc_label
from .ioutils import now_iso
from .schemas import SCHEMA_VERSION


def _question_view(q: dict, kcs: dict | None) -> dict:
    kc_ids = list(q.get("kc_ids", []))
    return {
        "question_id": q["question_id"],
        "kc_ids": kc_ids,
        "kc_labels": [kc_label(k, kcs) for k in kc_ids],
        "stem": q.get("stem", ""),
        "answer": q.get("answer", ""),
        "solution": q.get("solution", ""),
        "difficulty": q.get("difficulty", 0.5),
        "transfer_level": q.get("transfer_level", "T0"),
    }


def build_manifest(course: dict, mode: str, count: int, questions: list[dict],
                   kcs: dict | None = None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "course_id": course["id"],
            "course_name": course["name"],
            "mode": mode,
            "count": count,
            "generated_at": now_iso(),
        },
        "questions": [_question_view(q, kcs) for q in questions],
    }
