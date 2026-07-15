from __future__ import annotations

from datetime import date

DEFAULT_WEIGHTS = {
    "exam_weight": 1.0, "urgency": 1.0, "weakness": 1.5, "prereq_centrality": 0.8,
    "forgetting_risk": 1.0, "transfer_gap": 0.8, "blind_spot": 1.2, "expected_time": 0.5,
}

WEAKNESS_SCORE = {
    "weak": 1.0, "blocked": 0.9, "practiced": 0.6, "explained": 0.5,
    "unseen": 0.4, "checked": 0.2, "confirmed": 0.0,
}

ACTION_FOR_STATE = {
    "weak": "repair", "blocked": "repair", "practiced": "drill",
    "explained": "drill", "checked": "drill", "unseen": "advance",
}

ACTION_MINUTES = {"repair": 12, "drill": 10, "advance": 15}


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def days_to_exam(course: dict, today: date | None = None) -> int | None:
    exam = course.get("exam_date")
    if not exam:
        return None
    return (date.fromisoformat(str(exam)) - (today or date.today())).days


def _transfer_gap(kc: dict) -> float:
    t1 = kc["transfer"].get("T1_near")
    t2 = kc["transfer"].get("T2_structural")
    seen = [t for t in (t1, t2) if t is not None]
    if not seen:
        return 0.6
    worst = min(seen)  # 最差层级决定缺口：T1 通过但 T2 失败 → gap=1.0
    return _clamp(1.0 - worst)


def compute_next_best_step(
    course: dict,
    kc_states: dict[str, dict],
    miscs: dict[str, dict],
    due: list[dict],
    weights: dict | None = None,
) -> dict:
    w = dict(DEFAULT_WEIGHTS, **(weights or {}))
    days = days_to_exam(course)
    urgency = _clamp(1 - days / 60) if days is not None else 0.3

    out_degree = {k: 0 for k in kc_states}
    for kc in kc_states.values():
        for pre in kc.get("prerequisites", []):
            if pre in out_degree:
                out_degree[pre] += 1
    max_deg = max(out_degree.values(), default=0) or 1

    active_by_kc: dict[str, list[dict]] = {}
    for m in miscs.values():
        if m.get("repair_status") != "resolved":
            for k in m["kc_ids"]:
                active_by_kc.setdefault(k, []).append(m)

    candidates: list[dict] = []
    for kc_id, kc in kc_states.items():
        state = kc["teaching_state"]
        action = ACTION_FOR_STATE.get(state)
        if action is None:
            continue
        if state == "checked" and _transfer_gap(kc) <= 0.0:
            continue
        minutes = ACTION_MINUTES[action]
        retention = kc.get("retention", {})
        retr = retention.get("retrievability")
        forgetting = (1 - retr) if retr is not None else (0.8 if retention.get("due_count") else 0.0)
        gap = _transfer_gap(kc) if state in ("checked", "weak") else 0.0
        blind = kc["calibration"].get("blind_spot") or 0.0
        centrality = out_degree[kc_id] / max_deg
        score = (
            w["exam_weight"] * kc.get("exam_weight", 0.5)
            + w["urgency"] * urgency
            + w["weakness"] * WEAKNESS_SCORE[state]
            + w["prereq_centrality"] * centrality
            + w["forgetting_risk"] * forgetting
            + w["transfer_gap"] * gap
            + w["blind_spot"] * _clamp(blind)
            - w["expected_time"] * _clamp(minutes / 60)
        )

        reasons = [f"当前状态：{state}"]
        for m in active_by_kc.get(kc_id, []):
            reasons.append(f"存在未修复错因（{m['error_type']} ×{m.get('recurrence_count', 1)}）")
            if (m.get("confidence_before") or 0) >= 0.75:
                reasons.append("其中有高置信度错误")
        if gap >= 0.99 and kc["transfer"].get("T2_structural") is not None:
            reasons.append("T2 结构迁移未通过")
        elif gap >= 0.6:
            reasons.append("迁移尚未验证（T1/T2 无证据）")
        if forgetting >= 0.5:
            reasons.append(f"{retention.get('due_count', 0)} 张相关卡片到期")
        if centrality >= 0.5 and out_degree[kc_id]:
            reasons.append(f"是 {out_degree[kc_id]} 个后续知识点的前置")
        if kc.get("exam_weight", 0.5) >= 0.7:
            reasons.append("考试权重高")
        if days is not None:
            reasons.append(f"距考试 {days} 天")

        candidates.append({
            "action": action, "kc_id": kc_id, "kc_name": kc.get("name", kc_id),
            "estimated_minutes": minutes, "priority_score": round(score, 4),
            "reasons": reasons,
        })

    if due:
        minutes = max(5, 2 * len(due))
        score = (
            w["urgency"] * urgency
            + w["forgetting_risk"] * 1.0
            - w["expected_time"] * _clamp(minutes / 60)
        )
        candidates.append({
            "action": "review", "kc_id": None, "kc_name": None,
            "estimated_minutes": minutes, "priority_score": round(score, 4),
            "reasons": [f"{len(due)} 张卡片到期"] + ([f"距考试 {days} 天"] if days is not None else []),
        })

    if not candidates:
        return {"action": "rest", "kc_id": None, "kc_name": None, "estimated_minutes": 0,
                "priority_score": 0.0,
                "reasons": ["没有到期复习，也没有待修复/待推进的知识点"]}
    return max(candidates, key=lambda c: c["priority_score"])
