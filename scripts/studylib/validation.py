from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from .errors import ValidationFailed
from .events import append_event, new_event, read_events
from .registry import build_kcs
from .schemas import Question


def validate_candidate(kcs: dict[str, dict], cand: dict) -> list[str]:
    issues: list[str] = []
    try:
        q = Question.model_validate(cand)
    except ValidationError as e:
        return [f"schema 不合法：{err['loc']} {err['msg']}" for err in e.errors()]

    for kc_id in q.kc_ids:
        if kc_id not in kcs:
            issues.append(f"目标 KC 未注册：{kc_id}")
    if not q.answer.strip():
        issues.append("缺少标准答案")

    if q.source_type == "synthetic":
        if not q.derived_from:
            issues.append("AI 生成题缺少 derived_from 来源链")
        v = q.validation
        if v is None:
            issues.append("AI 生成题缺少 validation 块（四道闸门未执行）")
        else:
            if v.generator.get("status") != "passed":
                issues.append("Gate 1 Generator 未通过")
            if v.independent_solver.get("status") != "passed" or v.independent_solver.get("answer_match") is not True:
                issues.append("Gate 2 Independent Solver 未通过或答案不一致（solver answer_match 必须为 true）")
            if v.adversarial_review.get("status") != "passed":
                issues.append("Gate 3 Adversarial Reviewer 未通过")
            if v.mechanical_validator is not None and v.mechanical_validator.get("status") != "passed":
                issues.append("Gate 4 Mechanical Validator 未通过")

    if q.transfer_level in ("T2", "T3", "T4"):
        structural = set(q.changed_dimensions) - {"surface_context"}
        if not structural:
            issues.append(
                f"{q.transfer_level} 要求结构性改变维度，仅 surface_context（换数字/换背景）不能冒充结构迁移"
            )
    return issues


def register_question(
    root: Path, cand: dict, *, as_transfer_test: bool = False, session_id: str = "session_adhoc"
) -> dict:
    events = read_events(root)
    kcs = build_kcs(events)
    issues = validate_candidate(kcs, cand)
    if issues:
        raise ValidationFailed("题目未通过质量闸门：\n" + "\n".join(f"- {i}" for i in issues))
    q = Question.model_validate(cand)
    payload = {**cand, **q.model_dump()}
    course_id = events[0]["course_id"] if events else "unknown"
    etype = "transfer_test_created" if as_transfer_test else "question_registered"
    return append_event(root, new_event(course_id, etype, payload, session_id=session_id))
