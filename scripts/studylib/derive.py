from __future__ import annotations

from pathlib import Path

from . import dashboard
from .course import load_course
from .events import append_event, new_event, read_events
from .evidence import build_evidence
from .fsrs_store import due_cards, replay_cards, retention_by_kc
from .ioutils import atomic_write_json, atomic_write_text, now_iso, write_jsonl
from .misconceptions import build_misconceptions
from .nextstep import compute_next_best_step, days_to_exam
from .registry import build_kcs, build_questions, build_sources
from .state_rules import DeriveConfig, compute_kc_states

READINESS_SCORE = {
    "confirmed": 1.0, "checked": 0.75, "practiced": 0.4, "explained": 0.25,
    "weak": 0.15, "blocked": 0.05, "unseen": 0.0,
}

PHASE_MAP = {
    "question_attempted": "drill", "transfer_test_attempted": "drill",
    "question_registered": "drill", "transfer_test_created": "drill",
    "repair_started": "repair", "repair_step_completed": "repair",
    "repair_completed": "repair", "misconception_identified": "repair",
    "fsrs_reviewed": "review", "fsrs_card_created": "review",
}

STATES = ("unseen", "explained", "practiced", "checked", "confirmed", "weak", "blocked")


def build_state(course: dict, kc_states: dict, miscs: dict, due: list, events: list) -> dict:
    counts = {s: 0 for s in STATES}
    for kc in kc_states.values():
        counts[kc["teaching_state"]] += 1

    total_w = sum(kc.get("exam_weight", 0.5) for kc in kc_states.values())
    score = (
        sum(kc.get("exam_weight", 0.5) * READINESS_SCORE[kc["teaching_state"]]
            for kc in kc_states.values()) / total_w
        if total_w else 0.0
    )
    level = "low" if score < 0.4 else ("medium" if score < 0.7 else "high")

    days = days_to_exam(course)
    last = events[-1] if events else None
    active = sum(1 for m in miscs.values() if m["repair_status"] != "resolved")

    return {
        "schema_version": "2.0",
        "course": {"id": course["id"], "name": course["name"]},
        "profile": course.get("profile", {}),
        "current": {
            "phase": PHASE_MAP.get(last["event_type"], "init") if last else "init",
            "last_session": last["session_id"] if last else None,
        },
        "exam": {"date": course.get("exam_date"), "days_remaining": days},
        "readiness": {"level": level, "score": round(score, 4)},
        "counts": counts,
        "due_cards": len(due),
        "active_misconceptions": active,
        "next_best_step": compute_next_best_step(course, kc_states, miscs, due),
        "updated_at": now_iso(),
    }


def derive(root: Path, *, write: bool = True, cfg: DeriveConfig | None = None) -> dict:
    root = Path(root)
    events = read_events(root)
    course = load_course(root)
    kcs = build_kcs(events)
    questions = build_questions(events)
    sources = build_sources(events)
    miscs = build_misconceptions(events, questions)
    evid = build_evidence(events, questions)
    cards = replay_cards(events)
    kc_states = compute_kc_states(kcs, evid, miscs, retention_by_kc(cards), cfg)
    due = due_cards(cards)
    state = build_state(course, kc_states, miscs, due, events)

    if write:
        study = root / ".study"
        atomic_write_json(study / "state.json", state)
        atomic_write_json(study / "kc.json", kc_states)
        write_jsonl(study / "evidence.jsonl", evid)
        write_jsonl(study / "errors.jsonl", list(miscs.values()))
        write_jsonl(study / "cards.jsonl", list(cards.values()))
        write_jsonl(study / "questions.jsonl", list(questions.values()))
        write_jsonl(study / "sources.jsonl", sources)
        atomic_write_text(study / "dashboard.md", dashboard.render(state, kc_states, miscs, due))

    return {"state": state, "kc": kc_states, "misconceptions": miscs,
            "evidence": evid, "cards": cards, "questions": questions, "sources": sources}


def rebuild(root: Path, *, dry_run: bool = False) -> dict:
    import json

    root = Path(root)
    old_kc_path = root / ".study" / "kc.json"
    old_kc = json.loads(old_kc_path.read_text(encoding="utf-8")) if old_kc_path.exists() else {}

    fresh = derive(root, write=False)
    changed = {
        k: [old_kc[k]["teaching_state"], v["teaching_state"]]
        for k, v in fresh["kc"].items()
        if k in old_kc and old_kc[k]["teaching_state"] != v["teaching_state"]
    }
    summary = {"changed_kc_states": changed, "kc_total": len(fresh["kc"])}
    if dry_run:
        return summary

    course = load_course(root)
    append_event(root, new_event(course["id"], "state_rebuilt", {"changed": changed}))
    derive(root, write=True)
    return summary
