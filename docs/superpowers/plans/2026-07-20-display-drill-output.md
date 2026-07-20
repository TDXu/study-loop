# study-loop V2：KC 显示 / 学习模式 / 网页·试卷输出 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 study-loop 加三项能力——KC 中英对照显示、学习模式选择（考纲直出 / 诊断先行 + 题量）、选择题输出形态（本地网页可点击测验 / PDF 试卷 + 解析开关）。

**Architecture:** 一条主线 `选题（模式+题量）→ 题集（drill manifest）→ 渲染（HTML | PDF）`，外加贯穿全局的 KC 显示工具。实现顺序 F1 → F3 → F2。所有纯逻辑落在 `scripts/studylib/`，CLI 是 `scripts/*.py` 下的薄 Typer 层（沿用现有 `@guard` + `resolve_root` + `course_lock` 模式）。事件层只读不写（本轮输出形态是练习用，不回写 events.jsonl）。

**Tech Stack:** Python 3.11+、pydantic v2、typer、jinja2（已在 requirements）、reportlab（新增）、pytest。

## Global Constraints

- 铁律不变：**绝不直接写 `.study/` 下 JSON/JSONL**；状态只通过 `scripts/` CLI。
- 输出形态（HTML/PDF）只读 `derive()` 结果，不产生事件。
- 每个任务结束：`pytest` 全绿 + `CHANGELOG.md` 追加一条 + `git commit`。
- 测试风格沿用 `tests/`：纯函数单测直接 import `studylib`；CLI 测用 `subprocess`（见 `tests/test_cli_smoke.py`）。`conftest.py` 提供 `course` fixture（已 init 的模电课程）与 `home` fixture。
- KC 显示格式恒为 `kc_id（中文名）`（全角括号）；无中文名或 name==id 时只显示 `kc_id`。
- `seed` 固定时选题必须确定（便于复盘/测试）。
- 规格依据：`docs/superpowers/specs/2026-07-20-display-drill-output-design.md`。

---

## Task 1: `studylib/display.py` — `kc_label` 纯函数

**Files:**
- Create: `scripts/studylib/display.py`
- Test: `tests/test_display.py`

**Interfaces:**
- Consumes: 无（纯函数）。
- Produces: `kc_label(kc_id: str, kcs: dict[str, dict] | None = None) -> str`。`kcs` 是 `kc_id -> kc_dict` 映射，`kc_dict` 可能有 `name`。返回 `"kc_id（中文名）"`；`kcs` 无该 id、无 name、或 name==kc_id 时返回裸 `kc_id`。

- [ ] **Step 1: 写失败测试**

Create `tests/test_display.py`:
```python
from studylib.display import kc_label


def test_label_with_chinese_name():
    kcs = {"mao_living_soul": {"name": "毛泽东思想活的灵魂"}}
    assert kc_label("mao_living_soul", kcs) == "mao_living_soul（毛泽东思想活的灵魂）"


def test_label_missing_kc_falls_back_to_id():
    assert kc_label("orphan", {"x": {"name": "X"}}) == "orphan"


def test_label_no_kcs_arg():
    assert kc_label("orphan") == "orphan"


def test_label_name_equals_id():
    assert kc_label("x", {"x": {"name": "x"}}) == "x"


def test_label_empty_name_falls_back():
    assert kc_label("x", {"x": {"name": ""}}) == "x"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_display.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'studylib.display'`

- [ ] **Step 3: 写最小实现**

Create `scripts/studylib/display.py`:
```python
from __future__ import annotations


def kc_label(kc_id: str, kcs: dict[str, dict] | None = None) -> str:
    """User-facing KC label: 'kc_id（中文名）'. Falls back to bare kc_id."""
    kc = (kcs or {}).get(kc_id) or {}
    name = kc.get("name")
    if not name or name == kc_id:
        return kc_id
    return f"{kc_id}（{name}）"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_display.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 提交**

```bash
git add scripts/studylib/display.py tests/test_display.py
git commit -m "feat(display): add kc_label bilingual helper (kc_id（中文名）)"
```

---

## Task 2: 把 KC 标签接入 nextstep / dashboard / echo_next

**Files:**
- Modify: `scripts/studylib/nextstep.py`（`compute_next_best_step` 返回字典加 `kc_label`）
- Modify: `scripts/studylib/dashboard.py`（`build_risks` 用 label）
- Modify: `templates/dashboard.md.j2`（渲染 `kc_label`）
- Modify: `scripts/studylib/cli_common.py`（`echo_next` 用 label）
- Test: `tests/test_nextstep.py`（新增断言）

**Interfaces:**
- Consumes: Task 1 的 `kc_label`。
- Produces: `next_best_step` 字典新增字段 `kc_label: str`（保留旧 `kc_name` 向后兼容）；`build_risks` 返回的字符串含 `kc_id（中文名）`；dashboard 模板用 `s.next_best_step.kc_label`。

- [ ] **Step 1: 写失败测试**

Append to `tests/test_nextstep.py`:
```python
def test_next_step_emits_kc_label():
    from studylib.nextstep import compute_next_best_step
    kc_states = {"u": _kc_state("u", "unseen")}
    _patch_name(kc_states, "u", "未知点")
    rec = compute_next_best_step(COURSE, kc_states, {}, [])
    assert rec["kc_label"] == "u（未知点）"
    assert rec["kc_name"] == "未知点"  # back-compat retained
```
并在文件顶部 helper 区加：
```python
def _patch_name(kc_states, kc_id, name):
    kc_states[kc_id]["name"] = name
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_nextstep.py::test_next_step_emits_kc_label -v`
Expected: FAIL（`kc_label` 字段不存在）

- [ ] **Step 3: 改 `nextstep.py`**

In `scripts/studylib/nextstep.py`，顶部加 import：
```python
from .display import kc_label
```
在 `compute_next_best_step` 内，`candidates.append({...})`（当前含 `"kc_name": kc.get("name", kc_id)`）那一块，把 kc 字典构造改为：
```python
        candidates.append({
            "action": action, "kc_id": kc_id,
            "kc_name": kc.get("name", kc_id),
            "kc_label": kc_label(kc_id, kc_states),
            "estimated_minutes": minutes, "priority_score": round(score, 4),
            "reasons": reasons,
        })
```
（注意 `review` 与 `rest` 两个候选分支保持 `kc_id=None`，不加 `kc_label`，与现状一致。）

- [ ] **Step 4: 改 `dashboard.py` 的 `build_risks`**

In `scripts/studylib/dashboard.py`，顶部加：
```python
from .display import kc_label
```
把 `build_risks` 里两处 `kc['name']` 改为 label：
```python
def build_risks(kc_states: dict, miscs: dict, due: list) -> list[str]:
    risks: list[str] = []
    for kc in kc_states.values():
        label = kc_label(kc.get("kc_id", ""), kc_states)
        gap = kc["calibration"].get("gap")
        if kc["teaching_state"] == "weak" and gap is not None and gap >= 0.3:
            risks.append(f"{label}：高置信度盲区")
        elif kc["teaching_state"] == "blocked":
            risks.append(f"{label}：前置未稳定")
    for m in miscs.values():
        if m["repair_status"] != "resolved" and m.get("recurrence_count", 1) >= 2:
            risks.append(f"错因复发：{m['error_type']}（×{m['recurrence_count']}）")
    if due:
        risks.append(f"{len(due)} 张卡片到期")
    return risks
```

- [ ] **Step 5: 改 dashboard 模板**

In `templates/dashboard.md.j2`，第 6 行：
```
**{{ s.next_best_step.action }}**：{{ s.next_best_step.kc_name or "到期复习" }}
```
改为：
```
**{{ s.next_best_step.action }}**：{{ s.next_best_step.kc_label or s.next_best_step.kc_name or "到期复习" }}
```

- [ ] **Step 6: 改 `echo_next`**

In `scripts/studylib/cli_common.py`，`echo_next` 里：
```python
    target = nbs.get("kc_name") or "到期复习"
```
改为：
```python
    target = nbs.get("kc_label") or nbs.get("kc_name") or "到期复习"
```

- [ ] **Step 7: 跑全套确认通过**

Run: `python3 -m pytest tests/test_nextstep.py tests/test_derive.py -v`
Expected: PASS（含新测试 + 既有 derive 测试不受损）

- [ ] **Step 8: 提交**

```bash
git add scripts/studylib/nextstep.py scripts/studylib/dashboard.py scripts/studylib/cli_common.py templates/dashboard.md.j2 tests/test_nextstep.py
git commit -m "feat(display): show kc_id（中文名）in next-step, dashboard, echo"
```

---

## Task 3: evidence / misconception CLI 显示 KC 标签 + read_json 工具

**Files:**
- Modify: `scripts/studylib/ioutils.py`（新增 `read_json`）
- Modify: `scripts/evidence.py`
- Modify: `scripts/misconception.py`
- Test: `tests/test_ioutils.py`（新增）、`tests/test_cli_smoke.py`（新增 evidence/misconception 断言）

**Interfaces:**
- Consumes: Task 1 的 `kc_label`。
- Produces: `ioutils.read_json(path) -> dict`（读 `.study/kc.json`）；evidence/misconception 输出里 KC 以 `kc_id（中文名）` 显示。

- [ ] **Step 1: 写 `read_json` 失败测试**

Append to `tests/test_ioutils.py`:
```python
def test_read_json_roundtrip(tmp_path):
    from studylib.ioutils import atomic_write_json, read_json
    p = tmp_path / "x.json"
    atomic_write_json(p, {"a": 1, "中文": "好"})
    assert read_json(p) == {"a": 1, "中文": "好"}


def test_read_json_missing_returns_empty(tmp_path):
    from studylib.ioutils import read_json
    assert read_json(tmp_path / "nope.json") == {}
```

- [ ] **Step 2: 跑确认失败**

Run: `python3 -m pytest tests/test_ioutils.py -v`
Expected: FAIL（`ImportError: cannot import name 'read_json'`）

- [ ] **Step 3: 实现 `read_json`**

In `scripts/studylib/ioutils.py`，`read_jsonl` 之后加：
```python
def read_json(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
```

- [ ] **Step 4: 改 `scripts/evidence.py`**

替换为：
```python
#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typer

from studylib.cli_common import guard, resolve_root
from studylib.display import kc_label
from studylib.ioutils import read_json, read_jsonl

app = typer.Typer(add_completion=False)


@app.command("list")
@guard
def list_cmd(
    kc: str = typer.Option(..., "--kc"),
    course: Path = typer.Option(None, "--course"),
):
    root = resolve_root(course)
    kcs = read_json(root / ".study" / "kc.json")
    rows = [r for r in read_jsonl(root / ".study" / "evidence.jsonl") if kc in r["kc_ids"]]
    if not rows:
        typer.echo(f"{kc_label(kc, kcs)} 暂无证据")
        return
    typer.echo(f"{kc_label(kc, kcs)}（共 {len(rows)} 条证据）")
    for r in rows:
        mark = "✓" if r["result"]["correct"] else "✗"
        conf = r.get("confidence_before")
        typer.echo(f"{mark} {r['created_at']}  {r['question_id']}  {r['transfer_level']}  "
                   f"hint=L{r['hint_level']}  conf={conf if conf is not None else '-'}")


if __name__ == "__main__":
    app()
```

- [ ] **Step 5: 改 `scripts/misconception.py`**

把 `kc={','.join(m['kc_ids'])}` 那行改为标签形式。先顶部加 import：
```python
from studylib.display import kc_label
from studylib.ioutils import read_json
```
在 `list_cmd` 内，`rows = ...` 之后加：
```python
    kcs = read_json(root / ".study" / "kc.json")
```
把循环里：
```python
        typer.echo(f"{m['error_id']}  [{m['repair_status']}]  {m['error_type']}  "
                   f"kc={','.join(m['kc_ids'])}  ×{m.get('recurrence_count', 1)}")
```
改为：
```python
        kc_disp = " / ".join(kc_label(k, kcs) for k in m["kc_ids"])
        typer.echo(f"{m['error_id']}  [{m['repair_status']}]  {m['error_type']}  "
                   f"kc={kc_disp}  ×{m.get('recurrence_count', 1)}")
```

- [ ] **Step 6: 写 CLI 断言**

Append to `tests/test_cli_smoke.py` 一个新测试：
```python
def test_evidence_and_misconception_show_labels(tmp_path):
    home = tmp_path / "home"
    course_dir = tmp_path / "模电"
    r = run([SCRIPTS / "init_course.py", str(course_dir), "--course-id", "analog",
             "--name", "模拟电子技术"], tmp_path, home)
    assert r.returncode == 0, r.stderr
    r = run([SCRIPTS / "event.py", "kc-add", "--kc-id", "feedback_topology",
             "--name", "反馈组态判断", "--exam-weight", "0.9"], course_dir, home)
    assert r.returncode == 0, r.stderr
    cand = course_dir / "q.json"
    cand.write_text(json.dumps({
        "question_id": "q1", "kc_ids": ["feedback_topology"], "source_type": "past_exam",
        "transfer_level": "T0", "stem": "判断反馈组态", "answer": "A",
    }, ensure_ascii=False), encoding="utf-8")
    assert run([SCRIPTS / "validate_question.py", str(cand)], course_dir, home).returncode == 0
    assert run([SCRIPTS / "event.py", "attempt", "--question-id", "q1",
                "--wrong", "--confidence", "0.9"], course_dir, home).returncode == 0
    assert run([SCRIPTS / "event.py", "misconception", "--error-id", "err_001",
                "--kc", "feedback_topology", "--question", "q1",
                "--wrong-assumption", "x", "--missing-premise", "y",
                "--error-type", "concept_misconception"], course_dir, home).returncode == 0

    r = run([SCRIPTS / "evidence.py", "list", "--kc", "feedback_topology"], course_dir, home)
    assert r.returncode == 0, r.stderr
    assert "feedback_topology（反馈组态判断）" in r.stdout

    r = run([SCRIPTS / "misconception.py", "list"], course_dir, home)
    assert r.returncode == 0, r.stderr
    assert "feedback_topology（反馈组态判断）" in r.stdout
```

- [ ] **Step 7: 跑全套确认通过**

Run: `python3 -m pytest tests/test_ioutils.py tests/test_cli_smoke.py -v`
Expected: PASS

- [ ] **Step 8: 更新 SKILL.md + CHANGELOG，提交**

In `SKILL.md`，「铁律」列表末尾加一条：
```
6. 面向用户提到知识点时，一律用 `kc_id（中文名）` 形式（脚本已自动生成，你照着念）。
```
In `CHANGELOG.md` `[Unreleased]` 顶部加：
```
### 2026-07-20 — `feat` — F1 KC 中英对照显示
- 新增 `studylib.display.kc_label`；接入 next_step / dashboard / evidence / misconception 输出，统一 `kc_id（中文名）`。
- `ioutils` 新增 `read_json`。涉及：`nextstep.py` `dashboard.py` `cli_common.py` `templates/dashboard.md.j2` `scripts/evidence.py` `scripts/misconception.py`。
```
```bash
git add scripts/studylib/ioutils.py scripts/evidence.py scripts/misconception.py tests/test_ioutils.py tests/test_cli_smoke.py SKILL.md CHANGELOG.md
git commit -m "feat(display): KC labels in evidence/misconception CLI + read_json util"
```

---

## Task 4: `studylib/manifest.py` — drill manifest 契约

**Files:**
- Create: `scripts/studylib/manifest.py`
- Test: `tests/test_manifest.py`

**Interfaces:**
- Consumes: Task 1 的 `kc_label`；`schemas.SCHEMA_VERSION`；`ioutils.now_iso`。
- Produces:
  - `build_manifest(course: dict, mode: str, count: int, questions: list[dict], kcs: dict | None = None) -> dict`
  - 返回结构：`{"schema_version","meta":{course_id,course_name,mode,count,generated_at}, "questions":[{question_id,kc_ids,kc_labels,stem,answer,solution,difficulty,transfer_level}]}`。
  - 每题 `kc_labels = [kc_label(kid, kcs) for kid in kc_ids]`（`kcs` 为 None 时退化为 kc_ids）。不拷贝 `validation` 块。

- [ ] **Step 1: 写失败测试**

Create `tests/test_manifest.py`:
```python
from studylib.manifest import build_manifest


def test_manifest_shape_and_meta():
    course = {"id": "mao-zhongte", "name": "毛中特"}
    qs = [{"question_id": "q1", "kc_ids": ["mao_living_soul"], "stem": "s", "answer": "A",
           "solution": "sol", "difficulty": 0.4, "transfer_level": "T0",
           "validation": {"generator": {}}}]
    m = build_manifest(course, "diagnostic", 5, qs,
                       kcs={"mao_living_soul": {"name": "毛泽东思想活的灵魂"}})
    assert m["meta"] == {k: m["meta"][k] for k in
                         ("course_id", "course_name", "mode", "count", "generated_at")}
    assert m["meta"]["course_name"] == "毛中特" and m["meta"]["count"] == 5
    assert len(m["questions"]) == 1
    q = m["questions"][0]
    assert q["question_id"] == "q1"
    assert q["kc_labels"] == ["mao_living_soul（毛泽东思想活的灵魂）"]
    assert "validation" not in q  # rendering does not need it
    assert q["answer"] == "A" and q["solution"] == "sol"


def test_manifest_no_kcs_falls_back_to_ids():
    m = build_manifest({"id": "c", "name": "C"}, "syllabus", 3,
                       [{"question_id": "q", "kc_ids": ["k"], "stem": "", "answer": "B"}])
    assert m["questions"][0]["kc_labels"] == ["k"]
```

- [ ] **Step 2: 跑确认失败**

Run: `python3 -m pytest tests/test_manifest.py -v`
Expected: FAIL `ModuleNotFoundError: studylib.manifest`

- [ ] **Step 3: 实现**

Create `scripts/studylib/manifest.py`:
```python
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
```

- [ ] **Step 4: 跑确认通过**

Run: `python3 -m pytest tests/test_manifest.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 提交**

```bash
git add scripts/studylib/manifest.py tests/test_manifest.py
git commit -m "feat(drill): add drill-manifest contract with KC labels"
```

---

## Task 5: HTML 渲染器 `studylib/render_html.py` + `templates/quiz.html.j2`

**Files:**
- Create: `templates/quiz.html.j2`
- Create: `scripts/studylib/render_html.py`
- Test: `tests/test_render_html.py`

**Interfaces:**
- Consumes: Task 4 的 manifest 结构。
- Produces:
  - `parse_options(stem: str) -> tuple[str, list[tuple[str, str]]]`：把题干里 `A.xxx\nB.xxx` 拆成 (body, [(letter, text), ...])；识别半角/全角点号/顿号/右括号；选项续行并入上一项；无选项返回 (stem, [])。
  - `render_quiz_html(manifest: dict, reveal_default: bool = True) -> str`：返回自包含 HTML 字符串。

- [ ] **Step 1: 写 `parse_options` 失败测试**

Create `tests/test_render_html.py`:
```python
from studylib.render_html import parse_options, render_quiz_html


def test_parse_options_half_and_full_width():
    body, opts = parse_options("毛泽东思想活的灵魂是（  ）\nA.实事求是\nB.群众路线\nC.独立自主\nD.统一战线")
    assert body == "毛泽东思想活的灵魂是（  ）"
    assert opts == [("A", "实事求是"), ("B", "群众路线"), ("C", "独立自主"), ("D", "统一战线")]


def test_parse_options_full_width_dot():
    _, opts = parse_options("Q\nＡ．甲\nＢ．乙")
    assert opts == [("A", "甲"), ("B", "乙")]


def test_parse_options_none():
    body, opts = parse_options("简答题：论述…")
    assert body == "简答题：论述…" and opts == []


def test_parse_option_continuation_line():
    _, opts = parse_options("Q\nA.第一行\n续行\nB.第二项")
    assert opts == [("A", "第一行 续行"), ("B", "第二项")]
```

- [ ] **Step 2: 跑确认失败**

Run: `python3 -m pytest tests/test_render_html.py -v`
Expected: FAIL `ModuleNotFoundError: studylib.render_html`

- [ ] **Step 3: 实现 `render_html.py`**

Create `scripts/studylib/render_html.py`:
```python
from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Template

TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "templates" / "quiz.html.j2"

_OPT_RE = re.compile(r"^\s*([A-Ha-h])[．.、)]\s*(.*)$")


def parse_options(stem: str) -> tuple[str, list[tuple[str, str]]]:
    lines = stem.splitlines()
    body: list[str] = []
    opts: list[list[str]] = []  # each: [letter, text]
    in_opts = False
    for ln in lines:
        m = _OPT_RE.match(ln)
        if m:
            in_opts = True
            opts.append([m.group(1).upper(), m.group(2).strip()])
        elif not in_opts:
            body.append(ln)
        else:
            opts[-1][1] = (opts[-1][1] + " " + ln.strip()).strip()
    return "\n".join(body).strip(), [(o[0], o[1]) for o in opts]


def _question_for_render(q: dict) -> dict:
    body, opts = parse_options(q.get("stem", ""))
    ans = q.get("answer", "") or ""
    letters = sorted({ch for ch in ans if ch.strip()})
    return {
        "stem": body,
        "options": [{"letter": l, "text": t} for l, t in opts],
        "answer": ans,
        "answer_letters": letters,
        "multi": len(letters) > 1,
        "solution": q.get("solution", ""),
        "kc_labels": q.get("kc_labels") or q.get("kc_ids", []),
    }


def render_quiz_html(manifest: dict, reveal_default: bool = True) -> str:
    tpl = Template(TEMPLATE_PATH.read_text(encoding="utf-8"))
    view = {
        "meta": manifest["meta"],
        "questions": [_question_for_render(q) for q in manifest["questions"]],
    }
    return tpl.render(m=view, reveal_default=("on" if reveal_default else "off"))
```

- [ ] **Step 4: 写模板 `templates/quiz.html.j2`**

Create `templates/quiz.html.j2` (自包含，内联 CSS+JS)：
```html
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{{ m.meta.course_name }} · 练习</title>
<style>
  :root { --ok:#1a7f37; --bad:#cf222e; --muted:#6e7781; --line:#d0d7de; --bg:#f6f8fa; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         max-width: 820px; margin: 0 auto; padding: 24px 16px 80px; color:#1f2328; line-height:1.7; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  .meta { color: var(--muted); font-size: 13px; margin-bottom: 16px; }
  .toolbar { position: sticky; top: 0; background: var(--bg); border:1px solid var(--line);
             border-radius: 8px; padding: 10px 14px; margin-bottom: 20px; display:flex;
             align-items:center; gap:12px; flex-wrap:wrap; }
  .toolbar label.txt { font-size: 14px; cursor:pointer; }
  .switch { position:relative; width:44px; height:24px; flex:0 0 auto; }
  .switch input { opacity:0; width:0; height:0; }
  .slider { position:absolute; inset:0; background:#8c959f; border-radius:24px; transition:.2s; }
  .slider:before { content:""; position:absolute; width:18px; height:18px; left:3px; top:3px;
                   background:#fff; border-radius:50%; transition:.2s; }
  .switch input:checked + .slider { background: var(--ok); }
  .switch input:checked + .slider:before { transform: translateX(20px); }
  button.grade { margin-left:auto; padding:6px 14px; border:1px solid var(--line); background:#fff;
                 border-radius:6px; cursor:pointer; font-size:14px; }
  button.grade:hover { background: var(--bg); }
  .score { font-size: 14px; }
  .q { border:1px solid var(--line); border-radius:10px; padding:14px 16px; margin-bottom:14px; }
  .q .kcs { color: var(--muted); font-size:12px; margin-bottom:6px; }
  .q .stem { margin: 0 0 10px; white-space: pre-wrap; }
  .opts { display:flex; flex-direction:column; gap:6px; }
  .opt { display:flex; gap:8px; align-items:flex-start; padding:8px 10px; border:1px solid transparent;
         border-radius:6px; cursor:pointer; }
  .opt:hover { background: var(--bg); }
  .opt.locked { cursor: default; }
  .opt.correct { background:#dafbe1; border-color:var(--ok); }
  .opt.chosen-wrong { background:#ffebe9; border-color:var(--bad); }
  .reveal { margin-top:8px; padding:10px 12px; background:var(--bg); border-radius:6px;
            font-size:14px; display:none; }
  .reveal.show { display:block; }
  .reveal .ok { color: var(--ok); font-weight:600; }
  .reveal .bad { color: var(--bad); font-weight:600; }
</style>
</head>
<body>
<h1>{{ m.meta.course_name }} · 练习卷</h1>
<div class="meta">{{ m.meta.mode }} 模式 · {{ m.questions | count }} 题 · 生成于 {{ m.meta.generated_at }}</div>

<div class="toolbar">
  <span class="switch">
    <input type="checkbox" id="revealToggle" {% if reveal_default == "on" %}checked{% endif %}>
    <span class="slider"></span>
  </span>
  <label class="txt" for="revealToggle">即时显示答案与解析（开：点选项即出；关：做完点右侧统一对答案）</label>
  <button class="grade" id="gradeBtn" type="button">提交对答案</button>
  <span class="score" id="score"></span>
</div>

{% for q in m.questions %}
{% set qnum = loop.index %}
<section class="q" data-q="{{ qnum }}" data-answer="{{ q.answer_letters | join(',') }}" data-multi="{{ q.multi | lower }}">
  <div class="kcs">{% for l in q.kc_labels %}<span>{{ l }}</span>{% if not loop.last %} · {% endif %}{% endfor %}</div>
  <div class="stem">{{ qnum }}. {{ q.stem }}</div>
  <div class="opts">
    {% for o in q.options %}
    <label class="opt" data-letter="{{ o.letter }}">
      <input type="{{ 'checkbox' if q.multi else 'radio' }}" name="q{{ qnum }}" value="{{ o.letter }}">
      <span><b>{{ o.letter }}.</b> {{ o.text }}</span>
    </label>
    {% endfor %}
  </div>
  <div class="reveal" data-reveal>
    <div>答案：<b>{{ q.answer }}</b> <span class="judge"></span></div>
    <div>{{ q.solution }}</div>
  </div>
</section>
{% endfor %}

<script>
(function () {
  var toggle = document.getElementById('revealToggle');
  var gradeBtn = document.getElementById('gradeBtn');
  var scoreEl = document.getElementById('score');

  function chosen(sec) {
    return Array.prototype.map.call(sec.querySelectorAll('.opt input:checked'), function (i) { return i.value; });
  }
  function gradeQuestion(sec) {
    var answer = sec.getAttribute('data-answer').split(',').filter(Boolean);
    var ch = chosen(sec);
    sec.querySelectorAll('.opt').forEach(function (o) {
      var L = o.getAttribute('data-letter');
      o.classList.remove('correct', 'chosen-wrong');
      if (answer.indexOf(L) !== -1) o.classList.add('correct');
      else if (ch.indexOf(L) !== -1) o.classList.add('chosen-wrong');
    });
    var correct = ch.length === answer.length && ch.every(function (c) { return answer.indexOf(c) !== -1; });
    var j = sec.querySelector('.judge');
    j.textContent = correct ? '✓ 答对' : '✗ 答错';
    j.className = correct ? 'ok' : 'bad';
    sec.querySelector('[data-reveal]').classList.add('show');
    return correct;
  }

  document.querySelectorAll('.opt input').forEach(function (input) {
    input.addEventListener('change', function () {
      if (toggle.checked) gradeQuestion(input.closest('.q'));
    });
  });

  gradeBtn.addEventListener('click', function () {
    var secs = document.querySelectorAll('.q');
    var right = 0;
    secs.forEach(function (sec) { if (gradeQuestion(sec)) right++; });
    document.querySelectorAll('.opt input').forEach(function (i) { i.disabled = true; });
    scoreEl.innerHTML = '<b>得分：' + right + ' / ' + secs.length + '</b>';
  });
})();
</script>
</body>
</html>
```
（radio/checkbox 的 `name` 用外层题号 `qnum`——`{% set qnum = loop.index %}` 必须在外层 `{% for q %}` 内、内层 `{% for o %}` 之前，否则内层 `loop` 指向选项迭代器，会导致跨题单选互斥出错。）

- [ ] **Step 5: 写 `render_quiz_html` 测试**

Append to `tests/test_render_html.py`:
```python
def _manifest(multi=False):
    return {
        "meta": {"course_name": "毛中特", "mode": "diagnostic", "count": 1,
                 "generated_at": "2026-07-20T00:00:00+08:00"},
        "questions": [{
            "kc_labels": ["mao_living_soul（毛泽东思想活的灵魂）"],
            "stem": "活的灵魂三个方面是（  ）\nA.实事求是\nB.群众路线\nC.独立自主",
            "answer": "ABC" if multi else "A",
            "solution": "实事求是/群众路线/独立自主。",
        }],
    }


def test_render_html_embeds_toggle_options_answers():
    html = render_quiz_html(_manifest(multi=True), reveal_default=True)
    assert 'id="revealToggle"' in html
    # toggle ON -> the toggle input carries 'checked'
    assert 'revealToggle" checked' in html
    assert "mao_living_soul（毛泽东思想活的灵魂）" in html
    # multi -> checkbox; single would be radio
    assert 'type="checkbox"' in html
    # answer + solution embedded (hidden by CSS until reveal)
    assert "ABC" in html and "实事求是/群众路线/独立自主" in html


def test_render_html_reveal_default_off_not_checked():
    html = render_quiz_html(_manifest(multi=False), reveal_default=False)
    assert 'type="radio"' in html
    # toggle OFF -> the toggle input must NOT carry 'checked'
    toggle_line = html.split('id="revealToggle"', 1)[1].split(">", 1)[0]
    assert "checked" not in toggle_line
```

- [ ] **Step 6: 跑确认通过**

Run: `python3 -m pytest tests/test_render_html.py -v`
Expected: PASS (6 passed)

- [ ] **Step 7: 提交**

```bash
git add scripts/studylib/render_html.py templates/quiz.html.j2 tests/test_render_html.py
git commit -m "feat(output): self-contained interactive HTML quiz renderer + template"
```

---

## Task 6: `scripts/render_quiz_html.py` CLI

**Files:**
- Create: `scripts/render_quiz_html.py`
- Test: `tests/test_cli_smoke.py`（新增）

**Interfaces:**
- Consumes: Task 5 的 `render_quiz_html`；`ioutils.read_json`（读 manifest）。
- Produces: CLI `render_quiz_html.py --manifest m.json [--out quiz.html] [--reveal-default on|off]`。

- [ ] **Step 1: 写 CLI 失败测试**

Append to `tests/test_cli_smoke.py`:
```python
def test_render_quiz_html_cli(tmp_path):
    home = tmp_path / "home"
    course_dir = tmp_path / "模电"
    assert run([SCRIPTS / "init_course.py", str(course_dir), "--course-id", "analog",
                "--name", "模拟电子技术"], tmp_path, home).returncode == 0
    manifest = course_dir / "m.json"
    manifest.write_text(json.dumps({
        "meta": {"course_id": "analog", "course_name": "模拟电子技术", "mode": "syllabus",
                 "count": 1, "generated_at": "2026-07-20T00:00:00+08:00"},
        "questions": [{"question_id": "q1", "kc_labels": ["k（名）"],
                       "stem": "Q\nA.x\nB.y", "answer": "A", "solution": "s"}],
    }, ensure_ascii=False), encoding="utf-8")
    out = course_dir / "quiz.html"
    r = run([SCRIPTS / "render_quiz_html.py", "--manifest", str(manifest),
             "--out", str(out), "--reveal-default", "on"], course_dir, home)
    assert r.returncode == 0, r.stderr
    text = out.read_text(encoding="utf-8")
    assert "id=\"revealToggle\"" in text and "模拟电子技术" in text
```

- [ ] **Step 2: 跑确认失败**

Run: `python3 -m pytest tests/test_cli_smoke.py::test_render_quiz_html_cli -v`
Expected: FAIL（脚本不存在）

- [ ] **Step 3: 实现 CLI**

Create `scripts/render_quiz_html.py`:
```python
#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typer

from studylib.cli_common import guard
from studylib.ioutils import atomic_write_text, read_json
from studylib.render_html import render_quiz_html

app = typer.Typer(add_completion=False)


@app.command()
@guard
def main(
    manifest: Path = typer.Option(..., "--manifest"),
    out: Path = typer.Option(None, "--out"),
    reveal_default: str = typer.Option("on", "--reveal-default"),
):
    m = read_json(manifest)
    if not m:
        typer.echo(f"错误：manifest 不存在或为空：{manifest}", err=True)
        raise typer.Exit(code=1)
    html = render_quiz_html(m, reveal_default == "on")
    out = out or manifest.with_suffix(".html")
    atomic_write_text(out, html)
    typer.echo(f"已生成交互测验页：{out}")


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: 跑确认通过**

Run: `python3 -m pytest tests/test_cli_smoke.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add scripts/render_quiz_html.py tests/test_cli_smoke.py
git commit -m "feat(output): render_quiz_html CLI"
```

---

## Task 7: PDF 试卷 `studylib/render_paper.py` + CLI（重构 md_to_pdf）

**Files:**
- Create: `scripts/studylib/render_paper.py`
- Create: `scripts/render_paper.py`
- Delete: `scripts/md_to_pdf.py`
- Modify: `requirements.txt`（加 `reportlab`）
- Test: `tests/test_render_paper.py`

**Interfaces:**
- Consumes: Task 4 manifest；`reportlab`。
- Produces:
  - `manifest_to_markdown(manifest: dict, variant: str) -> str`：`variant ∈ {"questions","answers"}`。`questions` 只含题面+选项；`answers` 每题追加 `**答案**` 与 `> 解析`。
  - `markdown_to_pdf(md: str, pdf_path: Path, fonts_dir: Path | None = None) -> Path`：`fonts_dir` 提供则用其 Heiti 字体；否则回退 reportlab 内置 CID `STSong-Light`（无需字体文件）。
  - CLI `render_paper.py --manifest m.json [--variant {questions,answers,both}] [--out-dir <dir>] [--fonts-dir <path>]`。

- [ ] **Step 1: 写 `manifest_to_markdown` 失败测试**

Create `tests/test_render_paper.py`:
```python
from studylib.render_paper import manifest_to_markdown

M = {
    "meta": {"course_name": "毛中特", "mode": "syllabus", "count": 1,
             "generated_at": "2026-07-20T00:00:00+08:00"},
    "questions": [{"question_id": "q1", "kc_labels": ["k（名）"],
                   "stem": "活的灵魂三方面是（  ）\nA.实事求是\nB.群众路线",
                   "answer": "A", "solution": "实事求是是根本观点。"}],
}


def test_questions_variant_has_no_answer():
    md = manifest_to_markdown(M, "questions")
    assert "活的灵魂三方面是" in md and "A.实事求是" in md
    assert "答案" not in md and "实事求是是根本观点" not in md


def test_answers_variant_has_answer_and_solution():
    md = manifest_to_markdown(M, "answers")
    assert "答案：A" in md and "实事求是是根本观点" in md
```

- [ ] **Step 2: 跑确认失败**

Run: `python3 -m pytest tests/test_render_paper.py -v`
Expected: FAIL `ModuleNotFoundError: studylib.render_paper`

- [ ] **Step 3: 实现 `render_paper.py`**

Create `scripts/studylib/render_paper.py`:
```python
from __future__ import annotations

import html as _html
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (HRFlowable, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

BODY_FONT = "Body"
BOLD_FONT = "HeitiM"
_REGISTERED_KEY: str | None = None  # guards repeated registration in one process


def _register_fonts(fonts_dir: Path | None) -> None:
    """Register CJK fonts. Prefer Heiti .ttc from fonts_dir; else fall back to
    reportlab's built-in CID font STSong-Light (no font files needed). Sets the
    module-level BODY_FONT/BOLD_FONT so styles resolve correctly either way."""
    global BODY_FONT, BOLD_FONT, _REGISTERED_KEY
    fonts_dir = Path(fonts_dir) if fonts_dir else None
    use_heiti = bool(fonts_dir and (fonts_dir / "STHeitiLight.ttc").exists()
                     and (fonts_dir / "STHeitiMedium.ttc").exists())
    key = f"heiti:{fonts_dir}" if use_heiti else "cid"
    if _REGISTERED_KEY == key:
        return  # already registered with this config in this process
    if use_heiti:
        pdfmetrics.registerFont(TTFont("Body", str(fonts_dir / "STHeitiLight.ttc"), subfontIndex=0))
        pdfmetrics.registerFont(TTFont("HeitiM", str(fonts_dir / "STHeitiMedium.ttc"), subfontIndex=0))
        BODY_FONT, BOLD_FONT = "Body", "HeitiM"
    else:
        # UnicodeCIDFont registers under its face name; reuse that name for both.
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        BODY_FONT = BOLD_FONT = "STSong-Light"
    registerFontFamily(BODY_FONT, normal=BODY_FONT, bold=BOLD_FONT,
                       italic=BODY_FONT, boldItalic=BOLD_FONT)
    _REGISTERED_KEY = key


def _styles():
    ss = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=ss["Title"], fontName=BOLD_FONT, fontSize=16,
                             leading=22, spaceAfter=6, textColor=colors.HexColor("#1a1a1a")),
        "body": ParagraphStyle("body", fontName=BODY_FONT, fontSize=10.5, leading=16.5,
                               alignment=TA_LEFT, spaceAfter=3),
        "opt": ParagraphStyle("opt", fontName=BODY_FONT, fontSize=10.5, leading=15,
                              leftIndent=14, spaceAfter=1),
        "quote": ParagraphStyle("quote", fontName=BODY_FONT, fontSize=10, leading=15,
                                leftIndent=16, textColor=colors.HexColor("#444444"), spaceAfter=3),
    }


def _inline(t: str) -> str:
    t = t.replace("\\_", "_")
    t = _html.escape(t)
    parts = t.split("**")
    if len(parts) > 1:
        out = []
        for i, p in enumerate(parts):
            out += ["<b>", p, "</b>"] if i % 2 else [p]
        t = "".join(out)
    return t


def manifest_to_markdown(manifest: dict, variant: str) -> str:
    if variant not in ("questions", "answers"):
        raise ValueError(f"unknown variant: {variant}")
    meta = manifest["meta"]
    lines = [f"# {meta['course_name']} · 模拟卷",
             f"> {meta['mode']} 模式 · {len(manifest['questions'])} 题 · 生成于 {meta['generated_at']}", ""]
    for i, q in enumerate(manifest["questions"], 1):
        kcs = " · ".join(q.get("kc_labels") or q.get("kc_ids", []))
        lines.append(f"### 第 {i} 题　{kcs}")
        lines.append(q.get("stem", ""))
        if variant == "answers":
            lines += ["", f"**答案：{q.get('answer', '')}**", f"> 解析：{q.get('solution', '')}"]
        lines.append("")
    return "\n".join(lines)


def _parse(md: str, st: dict) -> list:
    import re
    flows, lines, i, n = [], md.split("\n"), 0, len(md.split("\n"))
    while i < n:
        line = lines[i].rstrip("\n")
        s = line.strip()
        if s == "":
            i += 1
            continue
        if s == "---":
            flows.append(HRFlowable(width="100%", thickness=0.6,
                                    color=colors.HexColor("#bbbbbb"), spaceBefore=4, spaceAfter=4))
            i += 1
            continue
        if s.startswith("# "):
            flows.append(Paragraph(_inline(s[2:].strip()), st["h1"])); i += 1; continue
        if s.startswith("### "):
            flows.append(Paragraph(_inline(s[4:].strip()),
                                   ParagraphStyle("h3", parent=st["body"], fontName=BOLD_FONT,
                                                  textColor=colors.HexColor("#0b5394"), spaceBefore=6)))
            i += 1; continue
        if s.startswith("> "):
            blk = []
            while i < n and lines[i].strip().startswith(">"):
                blk.append(lines[i].strip()[1:].strip()); i += 1
            flows.append(Paragraph("<br/>".join(_inline(x) for x in blk), st["quote"])); continue
        if re.match(r"^[　\s]*[A-H][．.、]", s):
            flows.append(Paragraph(_inline(s), st["opt"])); i += 1; continue
        flows.append(Paragraph(_inline(s), st["body"])); i += 1
    return flows


def markdown_to_pdf(md: str, pdf_path: Path, fonts_dir: Path | None = None) -> Path:
    _register_fonts(fonts_dir)
    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4,
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title=Path(pdf_path).name)
    doc.build(_parse(md, _styles()))
    return Path(pdf_path)
```

- [ ] **Step 4: 加依赖 + 跑纯函数测试**

In `requirements.txt` 末尾加一行：
```
reportlab>=4.0
```
Run: `python3 -m pip install reportlab>=4.0`
Run: `python3 -m pytest tests/test_render_paper.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 写 PDF 冒烟测试（用 CID 回退，免字体文件）**

Append to `tests/test_render_paper.py`:
```python
def test_markdown_to_pdf_produces_file(tmp_path):
    from studylib.render_paper import manifest_to_markdown, markdown_to_pdf
    md = manifest_to_markdown(M, "answers")
    pdf = tmp_path / "out.pdf"
    markdown_to_pdf(md, pdf, fonts_dir=None)  # CID fallback, no font files needed
    assert pdf.exists() and pdf.stat().st_size > 0
```
Run: `python3 -m pytest tests/test_render_paper.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: 实现 CLI + 删除旧脚本**

Create `scripts/render_paper.py`:
```python
#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typer

from studylib.cli_common import guard
from studylib.ioutils import read_json
from studylib.render_paper import manifest_to_markdown, markdown_to_pdf

app = typer.Typer(add_completion=False)


@app.command()
@guard
def main(
    manifest: Path = typer.Option(..., "--manifest"),
    variant: str = typer.Option("both", "--variant"),
    out_dir: Path = typer.Option(None, "--out-dir"),
    fonts_dir: Path = typer.Option(None, "--fonts-dir"),
):
    if variant not in ("questions", "answers", "both"):
        typer.echo("错误：--variant 必须是 questions/answers/both", err=True)
        raise typer.Exit(code=1)
    m = read_json(manifest)
    if not m:
        typer.echo(f"错误：manifest 不存在或为空：{manifest}", err=True)
        raise typer.Exit(code=1)
    out_dir = out_dir or manifest.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    base = m["meta"].get("course_name", "quiz")
    variants = ["questions", "answers"] if variant == "both" else [variant]
    for v in variants:
        md = manifest_to_markdown(m, v)
        tag = "题目" if v == "questions" else "答案解析"
        pdf = out_dir / f"{base}-{tag}.pdf"
        markdown_to_pdf(md, pdf, fonts_dir=fonts_dir)
        typer.echo(f"已生成：{pdf}")


if __name__ == "__main__":
    app()
```
Delete 旧脚本：
```bash
git rm scripts/md_to_pdf.py
```

- [ ] **Step 7: 更新 CHANGELOG，提交**

In `CHANGELOG.md` `[Unreleased]` 顶部加：
```
### 2026-07-20 — `feat` — F3 选择题输出（网页 / PDF 试卷）
- 新增 `studylib.manifest`（drill manifest 契约）、`studylib.render_html` + `templates/quiz.html.j2`（自包含交互测验页，运行时解析开关）、`studylib.render_paper`（manifest→PDF，支持题目卷/答案解析卷，CID 字体回退免装字体）。
- 新增 CLI：`scripts/render_quiz_html.py`、`scripts/render_paper.py`；移除 `scripts/md_to_pdf.py`（其能力并入 render_paper）。
- `requirements` 加 `reportlab>=4.0`。
```
```bash
git add scripts/studylib/render_paper.py scripts/render_paper.py requirements.txt tests/test_render_paper.py CHANGELOG.md
git commit -m "feat(output): PDF paper renderer (questions/answers) replacing md_to_pdf"
```

---

## Task 8: `studylib/drill.py` — `select_kcs`（模式 + 题量）

**Files:**
- Create: `scripts/studylib/drill.py`
- Test: `tests/test_drill_select.py`

**Interfaces:**
- Consumes: `studylib.nextstep.WEAKNESS_SCORE`（诊断弱点权重）。
- Produces: `select_kcs(kc_states: dict[str, dict], mode: str, count: int, seed: int = 0) -> list[str]`。
  - `mode="syllabus"`：按 `exam_weight` 加权无放回抽样。
  - `mode="diagnostic"`：若有任何非 `unseen` 的 KC，按 `WEAKNESS_SCORE` 加权抽；否则退化为 syllabus。
  - `seed` 固定→结果确定；`count` 截断到可用 KC 数；未知 mode 抛 `ValueError`。

- [ ] **Step 1: 写失败测试**

Create `tests/test_drill_select.py`:
```python
import pytest

from studylib.nextstep import WEAKNESS_SCORE


def _kc(state, weight=0.5):
    return {"kc_id": state, "name": state, "teaching_state": state, "exam_weight": weight,
            "prerequisites": [], "transfer": {}, "calibration": {}, "retention": {}}


def test_empty_and_zero_count():
    from studylib.drill import select_kcs
    assert select_kcs({}, "syllabus", 5) == []
    assert select_kcs({"a": _kc("unseen")}, "syllabus", 0) == []


def test_count_capped_to_available():
    from studylib.drill import select_kcs
    kcs = {"a": _kc("unseen"), "b": _kc("unseen")}
    assert set(select_kcs(kcs, "syllabus", 10, seed=1)) == {"a", "b"}


def test_deterministic_with_seed():
    from studylib.drill import select_kcs
    kcs = {f"k{i}": _kc("unseen", weight=(i + 1) / 5) for i in range(6)}
    r1 = select_kcs(kcs, "syllabus", 3, seed=42)
    r2 = select_kcs(kcs, "syllabus", 3, seed=42)
    assert r1 == r2 and len(r1) == 3


def test_unknown_mode_raises():
    from studylib.drill import select_kcs
    with pytest.raises(ValueError):
        select_kcs({"a": _kc("unseen")}, "bogus", 1)


def test_diagnostic_prefers_weak_when_record_exists():
    from studylib.drill import select_kcs
    kcs = {"weak": _kc("weak"), "conf": _kc("confirmed"), "unseen": _kc("unseen")}
    # weak has the highest weakness weight; with count covering all, weak is always in
    chosen = select_kcs(kcs, "diagnostic", 1, seed=0)
    assert chosen == ["weak"]


def test_diagnostic_falls_back_when_all_unseen():
    from studylib.drill import select_kcs
    kcs = {"a": _kc("unseen", weight=0.9), "b": _kc("unseen", weight=0.1)}
    # all unseen -> behaves like syllabus; high-weight 'a' strongly preferred
    chosen = select_kcs(kcs, "diagnostic", 1, seed=0)
    assert chosen == ["a"]
```

- [ ] **Step 2: 跑确认失败**

Run: `python3 -m pytest tests/test_drill_select.py -v`
Expected: FAIL `ModuleNotFoundError: studylib.drill`

- [ ] **Step 3: 实现**

Create `scripts/studylib/drill.py`:
```python
from __future__ import annotations

import random

from .nextstep import WEAKNESS_SCORE


def _weighted_sample_no_replace(
    rng: random.Random, items: list[str], weights: list[float], k: int
) -> list[str]:
    if k >= len(items):
        return list(items)
    # Efraimidis–Spirakis: key = u**(1/w); take the k largest keys.
    pairs = []
    for it, w in zip(items, weights):
        ww = w if w and w > 0 else 1e-9
        pairs.append((rng.random() ** (1.0 / ww), it))
    pairs.sort(key=lambda p: p[0], reverse=True)
    return [it for _, it in pairs[:k]]


def select_kcs(kc_states: dict[str, dict], mode: str, count: int, seed: int = 0) -> list[str]:
    if mode not in ("syllabus", "diagnostic"):
        raise ValueError(f"unknown mode: {mode}")
    ids = list(kc_states)
    if not ids or count <= 0:
        return []
    rng = random.Random(seed)
    if mode == "syllabus":
        weights = [kc_states[i].get("exam_weight", 0.5) for i in ids]
    else:  # diagnostic, adaptive
        has_record = any(kc_states[i].get("teaching_state") != "unseen" for i in ids)
        if has_record:
            weights = [WEAKNESS_SCORE.get(kc_states[i].get("teaching_state"), 0.0) for i in ids]
        else:
            weights = [kc_states[i].get("exam_weight", 0.5) for i in ids]
    return _weighted_sample_no_replace(rng, ids, weights, min(count, len(ids)))
```

- [ ] **Step 4: 跑确认通过**

Run: `python3 -m pytest tests/test_drill_select.py -v`
Expected: PASS (6 passed)。若 `test_diagnostic_prefers_weak` 偶发不过（抽样随机性），核对 `WEAKNESS_SCORE["weak"]=1.0` 为唯一最高，count=1 时必选 weak——应稳定通过。

- [ ] **Step 5: 提交**

```bash
git add scripts/studylib/drill.py tests/test_drill_select.py
git commit -m "feat(drill): select_kcs (syllabus weighted / diagnostic adaptive)"
```

---

## Task 9: `studylib/drill.py` — `gather_questions`（凑题 + 缺口）

**Files:**
- Modify: `scripts/studylib/drill.py`
- Test: `tests/test_drill_gather.py`

**Interfaces:**
- Consumes: registry 题目字典（`question_id -> payload`，payload 有 `kc_ids`）。
- Produces: `gather_questions(questions: dict, kc_ids: list[str], per_kc: int = 2, total: int | None = None) -> tuple[list[dict], dict[str, int]]`。
  - 轮询每个 KC 取至多 `per_kc` 题，总数不超过 `total`（默认 `per_kc * len(kc_ids)`）。
  - `shortfall`: `{kc_id: 缺口数}`，仅含注册表里题数 < per_kc 的 KC。

- [ ] **Step 1: 写失败测试**

Create `tests/test_drill_gather.py`:
```python
def _q(qid, kcs):
    return {"question_id": qid, "kc_ids": kcs, "stem": "", "answer": "A"}


def test_enough_questions_no_shortfall():
    from studylib.drill import gather_questions
    questions = {
        "a1": _q("a1", ["k1"]), "a2": _q("a2", ["k1"]), "a3": _q("a3", ["k1"]),
        "b1": _q("b1", ["k2"]), "b2": _q("b2", ["k2"]),
    }
    picked, short = gather_questions(questions, ["k1", "k2"], per_kc=2, total=4)
    assert len(picked) == 4
    assert short == {}


def test_shortfall_when_kc_has_no_questions():
    from studylib.drill import gather_questions
    questions = {"a1": _q("a1", ["k1"]), "a2": _q("a2", ["k1"])}
    picked, short = gather_questions(questions, ["k1", "k2"], per_kc=2, total=4)
    assert short == {"k2": 2}
    assert all(q["kc_ids"] == ["k1"] for q in picked)


def test_total_cap_respected():
    from studylib.drill import gather_questions
    questions = {f"a{i}": _q(f"a{i}", ["k1"]) for i in range(5)}
    questions.update({f"b{i}": _q(f"b{i}", ["k2"]) for i in range(5)})
    picked, short = gather_questions(questions, ["k1", "k2"], per_kc=2, total=2)
    assert len(picked) == 2
    assert short == {}
```

- [ ] **Step 2: 跑确认失败**

Run: `python3 -m pytest tests/test_drill_gather.py -v`
Expected: FAIL `ImportError: cannot import name 'gather_questions'`

- [ ] **Step 3: 实现**

Append to `scripts/studylib/drill.py`:
```python
def gather_questions(
    questions: dict, kc_ids: list[str], per_kc: int = 2, total: int | None = None
) -> tuple[list[dict], dict[str, int]]:
    total = total if total is not None else per_kc * max(1, len(kc_ids))
    by_kc: dict[str, list[dict]] = {k: [] for k in kc_ids}
    for q in questions.values():
        for k in q.get("kc_ids", []):
            if k in by_kc and len(by_kc[k]) < per_kc:
                by_kc[k].append(q)
    picked: list[dict] = []
    i = 0
    while len(picked) < total:
        progressed = False
        for k in kc_ids:
            if i < len(by_kc[k]):
                picked.append(by_kc[k][i])
                progressed = True
                if len(picked) >= total:
                    break
        if not progressed:
            break
        i += 1
    shortfall = {k: per_kc - len(by_kc[k]) for k in kc_ids if len(by_kc[k]) < per_kc}
    return picked, shortfall
```

- [ ] **Step 4: 跑确认通过**

Run: `python3 -m pytest tests/test_drill_gather.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 提交**

```bash
git add scripts/studylib/drill.py tests/test_drill_gather.py
git commit -m "feat(drill): gather_questions with shortfall detection"
```

---

## Task 10: `scripts/drill.py` CLI（一站式）+ SKILL.md 路由 + 收尾

**Files:**
- Create: `scripts/drill.py`
- Modify: `SKILL.md`（路由表加「刷题/出题/模拟卷」）
- Modify: `CHANGELOG.md`
- Test: `tests/test_cli_smoke.py`（新增 drill 冒烟）

**Interfaces:**
- Consumes: Task 8/9 `select_kcs`/`gather_questions`；Task 4 `build_manifest`；Task 5/7 渲染器；`derive`、`load_course`、`resolve_root`、`course_lock`、`kc_label`、`atomic_write_json`。
- Produces: CLI `drill.py --mode {syllabus,diagnostic} --count N [--per-kc 2] [--format {html,paper,md}] [--out PATH] [--reveal-default on|off] [--seed 0] [--course <path>]`。

- [ ] **Step 1: 写 drill 冒烟测试**

Append to `tests/test_cli_smoke.py`:
```python
def test_drill_cli_produces_html(tmp_path):
    home = tmp_path / "home"
    course_dir = tmp_path / "模电"
    assert run([SCRIPTS / "init_course.py", str(course_dir), "--course-id", "analog",
                "--name", "模拟电子技术"], tmp_path, home).returncode == 0
    assert run([SCRIPTS / "event.py", "kc-add", "--kc-id", "feedback_topology",
                "--name", "反馈组态判断", "--exam-weight", "0.9"], course_dir, home).returncode == 0
    # register two MCQs
    for qid, ans in (("q1", "A"), ("q2", "B")):
        (course_dir / f"{qid}.json").write_text(json.dumps({
            "question_id": qid, "kc_ids": ["feedback_topology"], "source_type": "past_exam",
            "transfer_level": "T0", "stem": f"题 {qid}\nA.x\nB.y", "answer": ans,
        }, ensure_ascii=False), encoding="utf-8")
        assert run([SCRIPTS / "validate_question.py", str(course_dir / f"{qid}.json")],
                   course_dir, home).returncode == 0
    out_html = course_dir / "drill.html"
    r = run([SCRIPTS / "drill.py", "--mode", "syllabus", "--count", "2", "--format", "html",
             "--out", str(out_html), "--seed", "1"], course_dir, home)
    assert r.returncode == 0, r.stderr
    assert "feedback_topology（反馈组态判断）" in r.stdout  # summary uses labels
    assert out_html.exists() and "id=\"revealToggle\"" in out_html.read_text(encoding="utf-8")
```

- [ ] **Step 2: 跑确认失败**

Run: `python3 -m pytest tests/test_cli_smoke.py::test_drill_cli_produces_html -v`
Expected: FAIL（脚本不存在）

- [ ] **Step 3: 实现 CLI**

Create `scripts/drill.py`:
```python
#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typer

from studylib import derive as derive_mod
from studylib.cli_common import guard, resolve_root
from studylib.course import load_course
from studylib.display import kc_label
from studylib.drill import gather_questions, select_kcs
from studylib.ioutils import atomic_write_json, atomic_write_text, course_lock
from studylib.manifest import build_manifest
from studylib.render_html import render_quiz_html
from studylib.render_paper import manifest_to_markdown, markdown_to_pdf

app = typer.Typer(add_completion=False)

NEXT_STEP_HINT = {
    "syllabus": "做完后对命中的同知识点做复盘重测（迁移题），验证不是背题。",
    "diagnostic": "据作答结果，对命中的弱知识点针对性出题 / 修复错因。",
}


@app.command()
@guard
def main(
    mode: str = typer.Option(..., "--mode"),
    count: int = typer.Option(10, "--count"),
    per_kc: int = typer.Option(2, "--per-kc"),
    fmt: str = typer.Option("html", "--format"),
    out: Path = typer.Option(None, "--out"),
    reveal_default: str = typer.Option("on", "--reveal-default"),
    seed: int = typer.Option(0, "--seed"),
    fonts_dir: Path = typer.Option(None, "--fonts-dir"),
    course: Path = typer.Option(None, "--course"),
):
    if mode not in ("syllabus", "diagnostic"):
        typer.echo("错误：--mode 必须是 syllabus 或 diagnostic", err=True)
        raise typer.Exit(code=1)
    if fmt not in ("html", "paper", "md"):
        typer.echo("错误：--format 必须是 html / paper / md", err=True)
        raise typer.Exit(code=1)

    root = resolve_root(course)
    with course_lock(root):
        result = derive_mod.derive(root)
    kc_states = result["kc"]
    questions = result["questions"]
    course_doc = load_course(root)

    selected = select_kcs(kc_states, mode, count, seed)
    picked, shortfall = gather_questions(questions, selected, per_kc=per_kc, total=count)
    manifest = build_manifest(course_doc, mode, count, picked, kcs=kc_states)

    out = out or (root / "output" / f"drill-{mode}-{count}")
    out.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "html":
        html_path = out.with_suffix(".html")
        atomic_write_text(html_path, render_quiz_html(manifest, reveal_default == "on"))
        typer.echo(f"已生成交互测验页：{html_path}")
    elif fmt == "paper":
        for v, tag in (("questions", "题目"), ("answers", "答案解析")):
            pdf = out.parent / f"{out.name}-{tag}.pdf"
            markdown_to_pdf(manifest_to_markdown(manifest, v), pdf, fonts_dir=fonts_dir)
            typer.echo(f"已生成 PDF：{pdf}")
    else:  # md
        md_path = out.with_suffix(".md")
        atomic_write_text(md_path, manifest_to_markdown(manifest, "answers"))
        typer.echo(f"已生成 Markdown：{md_path}")
    atomic_write_json(out.with_suffix(".manifest.json"), manifest)

    typer.echo("\n选题（按权重）：")
    for kc_id in selected:
        typer.echo(f"  - {kc_label(kc_id, kc_states)}")
    typer.echo(f"实际凑题：{len(picked)} 题（目标 {count}）。")
    if shortfall:
        typer.echo("⚠️ 题量不足（注册表缺题，未自动走 AI 出题闸门）：")
        for k, miss in shortfall.items():
            typer.echo(f"  - {kc_label(k, kc_states)}：缺 {miss} 题")
    typer.echo(f"\n下一步建议：{NEXT_STEP_HINT[mode]}")


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: 跑确认通过**

Run: `python3 -m pytest tests/test_cli_smoke.py -v`
Expected: PASS

- [ ] **Step 5: 更新 SKILL.md 路由表**

In `SKILL.md` 路由表，新增一行（插在「做题/刷题」行之后）：
```
| 刷题/出题/模拟卷 | 先问学生三件事：①模式（考纲直出 / 诊断先行）②题量（5/10/自定义）③形态（网页可点击 / PDF 试卷）→ `drill.py --mode .. --count .. --format ..`。网页版默认开启「点击即显示解析」，学生可在页面内随时关。 | references/（见 specs/2026-07-20-...） |
```

- [ ] **Step 6: 收尾 CHANGELOG + 全量测试 + 提交**

In `CHANGELOG.md` `[Unreleased]` 顶部加：
```
### 2026-07-20 — `feat` — F2 学习模式引擎 + 一站式 drill 命令
- 新增 `studylib.drill`：`select_kcs`（考纲加权 / 诊断自适应，seed 确定性）、`gather_questions`（凑题 + 缺口检测）。
- 新增 CLI `scripts/drill.py`：选题→凑题→manifest→渲染（html/paper/md），打印 KC 标签、缺口、下一步建议。
- `SKILL.md` 路由表新增「刷题/出题/模拟卷」意图（先问模式/题量/形态再出）。
```
把 `[Unreleased]` 下已完成的 F1/F3/F2 条目归入新版本号小节 `## [V2.0-rc1] - 2026-07-20`。
Run: `python3 -m pytest -q`
Expected: 全绿。
```bash
git add scripts/drill.py SKILL.md CHANGELOG.md tests/test_cli_smoke.py
git commit -m "feat(drill): one-command drill (mode+count) wiring renderers; SKILL routing"
```

---

## 完成验收（Definition of Done）

1. `python3 -m pytest -q` 全绿。
2. `next_step.py`、`render_dashboard.py`、`evidence.py list`、`misconception.py list` 输出均出现 `kc_id（中文名）`。
3. `drill.py --mode diagnostic --count 10 --format html` 一条命令产出可双击打开的交互测验页，含运行时解析开关；`--format paper` 产出题目卷 + 答案解析卷 PDF。
4. `CHANGELOG.md` 记录 F1/F3/F2 三组改动；`SKILL.md` 路由表含刷题意图。
5. 无任何对 `.study/` JSON 的直接写入（只走 CLI 写事件）。

## 回滚

每个 Task 独立提交，可 `git revert <hash>` 单步回退。F1 不依赖 F3/F2；F3 渲染器独立可用；F2 依赖 F3/F4 的契约。
