from __future__ import annotations

from pathlib import Path

from jinja2 import Template

TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "templates" / "dashboard.md.j2"


def build_risks(kc_states: dict, miscs: dict, due: list) -> list[str]:
    risks: list[str] = []
    for kc in kc_states.values():
        gap = kc["calibration"].get("gap")
        if kc["teaching_state"] == "weak" and gap is not None and gap >= 0.3:
            risks.append(f"「{kc['name']}」：高置信度盲区")
        elif kc["teaching_state"] == "blocked":
            risks.append(f"「{kc['name']}」：前置未稳定")
    for m in miscs.values():
        if m["repair_status"] != "resolved" and m.get("recurrence_count", 1) >= 2:
            risks.append(f"错因复发：{m['error_type']}（×{m['recurrence_count']}）")
    if due:
        risks.append(f"{len(due)} 张卡片到期")
    return risks


def render(state: dict, kc_states: dict, miscs: dict, due: list) -> str:
    template = Template(TEMPLATE_PATH.read_text(encoding="utf-8"))

    class _NS(dict):
        __getattr__ = dict.get

    def ns(d):
        return _NS({k: ns(v) if isinstance(v, dict) else v for k, v in d.items()})

    return template.render(s=ns(state), risks=build_risks(kc_states, miscs, due))
