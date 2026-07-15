from __future__ import annotations

from .schemas import SCHEMA_VERSION

_RESOLVE_TRANSFER = {"T1", "T2"}


def build_misconceptions(events: list[dict], questions: dict[str, dict]) -> dict[str, dict]:
    by_id: dict[str, dict] = {}
    key_index: dict[tuple, str] = {}

    for e in events:
        t = e["event_type"]
        p = e["payload"]

        if t == "misconception_identified":
            key = (p["kc_ids"][0], p["error_type"], p.get("wrong_assumption", ""))
            if key in key_index:
                m = by_id[key_index[key]]
                m["recurrence_count"] += 1
                m["last_seen_at"] = e["timestamp"]
                m["trigger_conditions"] = sorted(
                    set(m["trigger_conditions"]) | set(p.get("trigger_conditions", []))
                )
                if p.get("origin_question_id"):
                    m["origin_question_ids"].append(p["origin_question_id"])
            else:
                error_id = p.get("error_id") or "err_" + e["event_id"][4:]
                by_id[error_id] = {
                    "schema_version": SCHEMA_VERSION,
                    "error_id": error_id,
                    "course_id": e["course_id"],
                    "kc_ids": list(p["kc_ids"]),
                    "origin_question_id": p.get("origin_question_id"),
                    "origin_question_ids": [p["origin_question_id"]] if p.get("origin_question_id") else [],
                    "wrong_assumption": p.get("wrong_assumption", ""),
                    "missing_premise": p.get("missing_premise", ""),
                    "error_type": p["error_type"],
                    "trigger_conditions": sorted(set(p.get("trigger_conditions", []))),
                    "confidence_before": p.get("confidence_before"),
                    "attribution_confidence": p.get("attribution_confidence"),
                    "recurrence_count": 1,
                    "repair_status": "active",
                    "repair_history": [],
                    "retests_passed": [],
                    "transfer_failures": [],
                    "first_seen_at": e["timestamp"],
                    "last_seen_at": e["timestamp"],
                }
                key_index[key] = error_id

        elif t == "repair_started":
            m = by_id.get(p.get("error_id"))
            if m is not None:
                m["repair_status"] = "repairing"
                if p.get("repair_id"):
                    m["repair_history"].append(p["repair_id"])

        elif t == "repair_completed":
            m = by_id.get(p.get("error_id"))
            if m is not None:
                m["repair_status"] = "retest_pending"

        elif t in ("question_attempted", "transfer_test_attempted"):
            error_id = p.get("retest_of_error_id")
            m = by_id.get(error_id) if error_id else None
            if m is None:
                continue
            level = questions.get(p["question_id"], {}).get("transfer_level", "T0")
            if p.get("correct"):
                m["retests_passed"].append({"question_id": p["question_id"], "level": level})
            else:
                m["repair_status"] = "active"
                m["last_seen_at"] = e["timestamp"]
                if level != "T0":
                    m["transfer_failures"].append(p["question_id"])

    for m in by_id.values():
        if m["repair_status"] == "retest_pending":
            levels = {r["level"] for r in m["retests_passed"]}
            if "T0" in levels and (levels & _RESOLVE_TRANSFER):
                m["repair_status"] = "resolved"
    return by_id


def active_high_confidence(miscs: dict[str, dict], kc_id: str, threshold: float = 0.75) -> bool:
    for m in miscs.values():
        if kc_id not in m["kc_ids"] or m["repair_status"] == "resolved":
            continue
        if (m.get("confidence_before") or 0) >= threshold:
            return True
    return False
