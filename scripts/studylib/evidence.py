from __future__ import annotations

from .schemas import SCHEMA_VERSION

ATTEMPT_EVENTS = ("question_attempted", "transfer_test_attempted")


def build_evidence(events: list[dict], questions: dict[str, dict]) -> list[dict]:
    rows: list[dict] = []
    for e in events:
        if e["event_type"] not in ATTEMPT_EVENTS:
            continue
        p = e["payload"]
        q = questions.get(p["question_id"], {})
        correct = bool(p.get("correct"))
        rows.append({
            "schema_version": SCHEMA_VERSION,
            "evidence_id": "evd_" + e["event_id"][4:],
            "course_id": e["course_id"],
            "kc_ids": list(p.get("kc_ids") or q.get("kc_ids", [])),
            "evidence_type": "question_attempt",
            "question_id": p["question_id"],
            "result": {"correct": correct, "score": float(p.get("score", 1.0 if correct else 0.0))},
            "confidence_before": p.get("confidence_before"),
            "hint_level": int(p.get("hint_level", 0)),
            "response_time_sec": p.get("response_time_sec"),
            "transfer_level": q.get("transfer_level", "T0"),
            "source_event_id": e["event_id"],
            "weight": 1.0,
            "created_at": e["timestamp"],
        })
    return rows
