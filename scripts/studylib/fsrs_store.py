from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fsrs import Card, Rating, Scheduler

from .errors import InvalidSchema
from .schemas import CARD_TYPES, SCHEMA_VERSION


def _utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts).astimezone(timezone.utc)


def new_card_payload(card_type: str, kc_ids: list[str], question_id: str | None = None) -> dict:
    if card_type not in CARD_TYPES:
        raise InvalidSchema(f"unknown card_type: {card_type} (allowed: {sorted(CARD_TYPES)})")
    return {
        "card_id": f"card_{uuid.uuid4().hex[:12]}",
        "card_type": card_type,
        "question_id": question_id,
        "kc_ids": list(kc_ids),
        "fsrs": Card().to_dict(),
    }


def replay_cards(events: list[dict]) -> dict[str, dict]:
    scheduler = Scheduler()
    cards: dict[str, Card] = {}
    meta: dict[str, dict] = {}
    for e in events:
        p = e["payload"]
        if e["event_type"] == "fsrs_card_created":
            cards[p["card_id"]] = Card.from_dict(p["fsrs"])
            meta[p["card_id"]] = {
                "card_type": p["card_type"],
                "question_id": p.get("question_id"),
                "kc_ids": list(p.get("kc_ids", [])),
                "created_at": e["timestamp"],
                "review_count": 0,
                "last_review": None,
            }
        elif e["event_type"] == "fsrs_reviewed":
            cid = p["card_id"]
            if cid not in cards:
                continue
            card, _log = scheduler.review_card(
                cards[cid], Rating(int(p["rating"])), review_datetime=_utc(p["review_time"])
            )
            cards[cid] = card
            meta[cid]["review_count"] += 1
            meta[cid]["last_review"] = p["review_time"]

    out: dict[str, dict] = {}
    for cid, card in cards.items():
        d = card.to_dict()
        out[cid] = {"schema_version": SCHEMA_VERSION, "card_id": cid, **meta[cid],
                    "fsrs": d, "due": d["due"]}
    return out


def due_cards(cards: dict[str, dict], now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    due = [c for c in cards.values() if _utc(c["due"]) <= now]
    return sorted(due, key=lambda c: c["due"])


def retention_by_kc(cards: dict[str, dict], now: datetime | None = None) -> dict[str, dict]:
    now = now or datetime.now(timezone.utc)
    scheduler = Scheduler()
    ret: dict[str, dict] = {}
    for c in cards.values():
        card = Card.from_dict(c["fsrs"])
        r = float(scheduler.get_card_retrievability(card, current_datetime=now))
        is_due = _utc(c["due"]) <= now
        for kc_id in c["kc_ids"]:
            slot = ret.setdefault(kc_id, {"fsrs_card_ids": [], "retrievability": None, "due_count": 0})
            slot["fsrs_card_ids"].append(c["card_id"])
            slot["retrievability"] = r if slot["retrievability"] is None else min(slot["retrievability"], r)
            slot["due_count"] += 1 if is_due else 0
    return ret


def rating_from_result(correct: bool, confidence: float | None) -> int:
    if not correct:
        return 1
    if confidence is not None and confidence < 0.75:
        return 2
    return 3
