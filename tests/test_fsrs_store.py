from datetime import datetime, timedelta, timezone

import pytest


def _created(payload):
    from studylib.events import new_event
    return new_event("c1", "fsrs_card_created", payload)


def _reviewed(card_id, rating, review_time):
    from studylib.events import new_event
    return new_event("c1", "fsrs_reviewed",
                     {"card_id": card_id, "rating": rating, "review_time": review_time})


def test_new_card_payload_shape():
    from studylib.fsrs_store import new_card_payload
    p = new_card_payload("original_question", ["k1"], question_id="past_2023_q17")
    assert p["card_id"].startswith("card_")
    assert p["card_type"] == "original_question"
    assert p["kc_ids"] == ["k1"]
    assert isinstance(p["fsrs"], dict) and "due" in p["fsrs"]


def test_new_card_payload_rejects_bad_type():
    from studylib.errors import InvalidSchema
    from studylib.fsrs_store import new_card_payload
    with pytest.raises(InvalidSchema):
        new_card_payload("mystery_card", ["k1"])


def test_replay_is_deterministic_and_review_advances_due():
    from studylib.fsrs_store import new_card_payload, replay_cards
    payload = new_card_payload("original_question", ["k1"], question_id="q1")
    created = _created(payload)
    review_time = datetime.now(timezone.utc).isoformat()
    events = [created, _reviewed(payload["card_id"], 3, review_time)]
    a = replay_cards(events)
    b = replay_cards(events)
    card_a = a[payload["card_id"]]
    assert card_a["review_count"] == 1
    assert card_a["last_review"] == review_time
    assert card_a["due"] == b[payload["card_id"]]["due"], "replay must be deterministic"
    assert card_a["due"] > payload["fsrs"]["due"], "Good review must push due later"


def test_due_cards_and_retention_by_kc():
    from studylib.fsrs_store import due_cards, new_card_payload, replay_cards, retention_by_kc
    p1 = new_card_payload("original_question", ["k1"], question_id="q1")
    p2 = new_card_payload("transfer_question", ["k1", "k2"], question_id="q2")
    cards = replay_cards([_created(p1), _created(p2)])
    now = datetime.now(timezone.utc) + timedelta(days=365)
    due = due_cards(cards, now=now)
    assert {c["card_id"] for c in due} == {p1["card_id"], p2["card_id"]}
    ret = retention_by_kc(cards, now=now)
    assert set(ret) == {"k1", "k2"}
    assert set(ret["k1"]["fsrs_card_ids"]) == {p1["card_id"], p2["card_id"]}
    assert ret["k1"]["due_count"] == 2
    assert 0.0 <= ret["k1"]["retrievability"] <= 1.0


def test_rating_from_result():
    from studylib.fsrs_store import rating_from_result
    assert rating_from_result(False, 0.9) == 1
    assert rating_from_result(True, 0.9) == 3
    assert rating_from_result(True, 0.5) == 2
    assert rating_from_result(True, None) == 3
