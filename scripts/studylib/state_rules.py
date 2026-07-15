from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .ioutils import now_iso
from .misconceptions import active_high_confidence
from .schemas import SCHEMA_VERSION, TRANSFER_KEY, TRANSFER_LEVELS


@dataclass
class DeriveConfig:
    independent_hint_max: int = 1
    weak_success_floor: float = 0.5
    retention_min_days: float = 1.0
    high_conf_threshold: float = 0.75
    transfer_window: int = 3


def _ts(row: dict) -> datetime:
    return datetime.fromisoformat(row["created_at"])


def kc_aggregate(kc_id: str, evidence: list[dict], cfg: DeriveConfig) -> dict:
    ev = sorted((r for r in evidence if kc_id in r["kc_ids"]), key=lambda r: r["created_at"])
    independent = [
        r for r in ev if r["result"]["correct"] and r["hint_level"] <= cfg.independent_hint_max
    ]
    observed = (sum(1 for r in ev if r["result"]["correct"]) / len(ev)) if ev else None
    confs = [r["confidence_before"] for r in ev if r.get("confidence_before") is not None]
    self_estimate = sum(confs) / len(confs) if confs else None
    gap = (self_estimate - observed) if (self_estimate is not None and observed is not None) else None
    blind_spot = (self_estimate * (1 - observed)) if (self_estimate is not None and observed is not None) else 0.0

    transfer_mean: dict[str, float | None] = {}
    transfer_last: dict[str, bool | None] = {}
    for lvl in TRANSFER_LEVELS:
        rows = [r for r in ev if r["transfer_level"] == lvl]
        recent = rows[-cfg.transfer_window:]
        transfer_mean[lvl] = (sum(1 for r in recent if r["result"]["correct"]) / len(recent)) if recent else None
        transfer_last[lvl] = rows[-1]["result"]["correct"] if rows else None

    retention_ok = False
    if len(independent) >= 2:
        span_days = (_ts(independent[-1]) - _ts(independent[0])).total_seconds() / 86400
        retention_ok = span_days >= cfg.retention_min_days

    return {
        "attempts": ev,
        "independent_corrects": independent,
        "observed": observed,
        "self_estimate": self_estimate,
        "gap": gap,
        "blind_spot": blind_spot,
        "transfer_mean": transfer_mean,
        "transfer_last": transfer_last,
        "last_hint_level": ev[-1]["hint_level"] if ev else 0,
        "independent_success_rate": (
            sum(1 for r in ev if r["hint_level"] == 0 and r["result"]["correct"]) / len(ev)
            if ev else None
        ),
        "retention_ok": retention_ok,
        "recent_transfer_failure": any(
            transfer_last[lvl] is False for lvl in ("T1", "T2", "T3", "T4")
        ),
    }


def teaching_state(
    kc: dict, agg: dict, prereq_states: dict[str, str], high_conf_active: bool, cfg: DeriveConfig
) -> str:
    ev = agg["attempts"]
    prereq_bad = any(prereq_states.get(p) in ("weak", "blocked") for p in kc.get("prerequisites", []))
    if prereq_bad and not agg["independent_corrects"]:
        return "blocked"

    if not ev and not kc.get("explained"):
        return "unseen"

    if ev:
        weak = (
            not ev[-1]["result"]["correct"]
            or high_conf_active
            or (len(ev) >= 2 and agg["observed"] is not None and agg["observed"] < cfg.weak_success_floor)
            or agg["recent_transfer_failure"]
        )
        if weak:
            return "weak"
        if agg["independent_corrects"]:
            transfer_pass = agg["transfer_last"]["T1"] is True or agg["transfer_last"]["T2"] is True
            if agg["retention_ok"] and transfer_pass and not high_conf_active:
                return "confirmed"
            return "checked"
        return "practiced"
    return "explained"


def _topo_order(kcs: dict[str, dict]) -> list[str]:
    order: list[str] = []
    done: set[str] = set()

    def visit(kc_id: str, stack: set[str]):
        if kc_id in done or kc_id in stack or kc_id not in kcs:
            return
        stack.add(kc_id)
        for pre in kcs[kc_id].get("prerequisites", []):
            visit(pre, stack)
        stack.discard(kc_id)
        done.add(kc_id)
        order.append(kc_id)

    for k in kcs:
        visit(k, set())
    return order


def compute_kc_states(
    kcs: dict[str, dict],
    evidence: list[dict],
    miscs: dict[str, dict],
    retention_by_kc: dict[str, dict] | None = None,
    cfg: DeriveConfig | None = None,
) -> dict[str, dict]:
    cfg = cfg or DeriveConfig()
    retention_by_kc = retention_by_kc or {}
    states: dict[str, str] = {}
    out: dict[str, dict] = {}

    for kc_id in _topo_order(kcs):
        kc = kcs[kc_id]
        agg = kc_aggregate(kc_id, evidence, cfg)
        high_conf = active_high_confidence(miscs, kc_id, cfg.high_conf_threshold)
        st = teaching_state(kc, agg, states, high_conf, cfg)
        states[kc_id] = st
        out[kc_id] = {
            "schema_version": SCHEMA_VERSION,
            "kc_id": kc_id,
            "name": kc["name"],
            "chapter_id": kc.get("chapter_id"),
            "prerequisites": kc.get("prerequisites", []),
            "exam_weight": kc.get("exam_weight", 0.5),
            "teaching_state": st,
            "retention": retention_by_kc.get(
                kc_id, {"fsrs_card_ids": [], "retrievability": None, "due_count": 0}
            ),
            "transfer": {TRANSFER_KEY[lvl]: agg["transfer_mean"][lvl] for lvl in TRANSFER_LEVELS},
            "calibration": {
                "self_estimate": agg["self_estimate"],
                "observed_performance": agg["observed"],
                "gap": agg["gap"],
                "blind_spot": agg["blind_spot"],
            },
            "assistance": {
                "last_hint_level": agg["last_hint_level"],
                "independent_success_rate": agg["independent_success_rate"],
            },
            "evidence_ids": [r["evidence_id"] for r in agg["attempts"]],
            "active_misconceptions": sorted(
                m["error_id"] for m in miscs.values()
                if kc_id in m["kc_ids"] and m["repair_status"] != "resolved"
            ),
            "updated_at": now_iso(),
        }
    return out
