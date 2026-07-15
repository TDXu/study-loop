# study-loop V1 核心闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 study-loop 规格书（`~/Downloads/study-loop-development-spec-v2.md`）的 P0 架构基础 + §45/§50 V1 最小可用闭环：course init → 事件日志 → KC/题目注册 → 作答+置信度 → 错因归因 → 修复 → 原题重测 → T1/T2 迁移题验证入库 → FSRS → next-best-step → `/study` 推荐。

**Architecture:** 事件溯源架构——`events.jsonl` 是唯一真相，所有派生状态（kc.json / errors.jsonl / cards.jsonl / state.json / dashboard.md）由 `derive` 纯函数从事件流重算。业务逻辑全部在 `scripts/studylib/` 库中，spec 命名的脚本（init_course.py、event.py、derive_state.py 等）是薄 Typer CLI 壳。AI（主 Agent）只通过 CLI 写事件，绝不直接改 JSON。

**Tech Stack:** Python 3.11+（本机 3.13.9）、pydantic 2.x、typer、fsrs 6.3.1（py-fsrs）、jinja2、filelock、pyyaml、pytest。

## Global Constraints

- 所有机器文件含 `"schema_version": "2.0"`（attempt package 为 "1.0"，V1 未实现）。
- 事件日志 append-only；禁止 AI/脚本就地修改历史事件。
- 所有 JSON/文本写入必须原子：临时文件 → fsync → `os.replace`。
- 状态派生与写入必须持有课程级锁 `.study/locks/state.lock`（filelock，超时 10s → `StateLockTimeout`）。
- 不引入数据库、不引入 xelatex；Markdown 为可读产物，JSON/JSONL 为机器状态。
- 脚本必须可 `python3 scripts/<name>.py` 独立运行（脚本头部 `sys.path.insert` 指向 scripts/ 以导入 studylib）。
- 全局目录 `~/.study-loop/` 必须可用环境变量 `STUDY_LOOP_HOME` 覆盖（测试隔离用）。
- 原题（past_exam/homework/teacher_emphasis）必须可进 FSRS，不能只调度 AI 生成题。
- AI 生成题（source_type=synthetic）必须通过 `validate_question.py` 四道闸门检查后才能注册。
- 简单换数字（changed_dimensions ⊆ {surface_context}）不得标为 T2+。
- 每个 commit message 末尾加 trailer：`Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`。
- 开发目录：`/Users/td_xu/Desktop/SKill/study-loop`（下文所有相对路径以此为根）。
- V1 明确不做（后续计划再做）：MarkItDown 材料摄入（ingest.py）、自适应诊断（diagnose.py）、HTML attempt 导入（import_attempt.py）、考后回传（exam_feedback.py）、跨课程指纹、冲刺矩阵、quiz.html/mock_exam.html 模板、主观题 rubric 批改（answer_graded 仅保留事件类型）、学科 profile 校正流程（course.yaml 存默认向量）。

---

### Task 1: 仓库骨架与测试环境

**Files:**
- Create: `.gitignore`, `requirements.txt`, `pytest.ini`, `tests/conftest.py`, `tests/test_smoke.py`, `scripts/studylib/__init__.py`

**Interfaces:**
- Produces: `tests/conftest.py` 提供 `home` fixture（隔离 STUDY_LOOP_HOME）；scripts/ 已加入 sys.path，后续测试可 `from studylib import ...`。

- [ ] **Step 1: git init 与骨架文件**

```bash
cd /Users/td_xu/Desktop/SKill/study-loop
git init
mkdir -p scripts/studylib tests templates references agents
```

`.gitignore`:
```text
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
.venv/
```

`requirements.txt`:
```text
pydantic>=2.5
typer>=0.9
fsrs>=6.0,<7
jinja2>=3.1
filelock>=3.12
pyyaml>=6.0
pytest>=8.0
```

`pytest.ini`:
```ini
[pytest]
testpaths = tests
addopts = -q
```

`scripts/studylib/__init__.py`:
```python
"""study-loop core library. CLI scripts in scripts/ are thin wrappers around this package."""
SCHEMA_VERSION = "2.0"
```

`tests/conftest.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pytest


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "study-home"
    monkeypatch.setenv("STUDY_LOOP_HOME", str(h))
    return h
```

- [ ] **Step 2: 写冒烟测试**

`tests/test_smoke.py`:
```python
def test_import_studylib():
    import studylib
    assert studylib.SCHEMA_VERSION == "2.0"


def test_deps_available():
    import pydantic, typer, fsrs, jinja2, filelock, yaml  # noqa: F401
```

- [ ] **Step 3: 安装依赖并运行测试**

Run: `python3 -m pip install -r requirements.txt && python3 -m pytest tests/test_smoke.py -v`
Expected: 2 passed

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: repo skeleton, deps, test harness

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: 存储原语（原子写入 / JSONL / 课程锁 / 错误类型）

**Files:**
- Create: `scripts/studylib/errors.py`, `scripts/studylib/ioutils.py`
- Test: `tests/test_ioutils.py`

**Interfaces:**
- Produces:
  - `errors.py`: `StudyLoopError` 基类及子类 `CourseNotFound, InvalidWorkspace, InvalidSchema, DuplicateEvent, UnknownQuestion, UnknownKC, StateLockTimeout, ValidationFailed`（均继承 `StudyLoopError(Exception)`）。
  - `ioutils.now_iso() -> str`（本地时区 ISO8601，秒精度）
  - `ioutils.atomic_write_text(path: Path, text: str) -> None`
  - `ioutils.atomic_write_json(path: Path, obj) -> None`（indent=2, ensure_ascii=False, 尾随换行）
  - `ioutils.write_jsonl(path: Path, rows: list[dict]) -> None`（整体原子重写）
  - `ioutils.append_jsonl(path: Path, obj: dict) -> None`（追加 + fsync）
  - `ioutils.read_jsonl(path: Path) -> list[dict]`（不存在返回 []）
  - `ioutils.course_lock(course_root: Path, timeout: float = 10.0) -> FileLock`（锁文件 `.study/locks/state.lock`）

- [ ] **Step 1: 写失败测试**

`tests/test_ioutils.py`:
```python
import json
from pathlib import Path

import pytest


def test_atomic_write_and_read_json(tmp_path):
    from studylib.ioutils import atomic_write_json
    p = tmp_path / "a" / "b.json"
    atomic_write_json(p, {"x": "中文", "n": 1})
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data == {"x": "中文", "n": 1}
    assert not list(p.parent.glob("*.tmp*")), "temp file must be cleaned up"


def test_jsonl_append_and_read(tmp_path):
    from studylib.ioutils import append_jsonl, read_jsonl
    p = tmp_path / "log.jsonl"
    assert read_jsonl(p) == []
    append_jsonl(p, {"a": 1})
    append_jsonl(p, {"b": "二"})
    assert read_jsonl(p) == [{"a": 1}, {"b": "二"}]


def test_write_jsonl_atomic_rewrite(tmp_path):
    from studylib.ioutils import write_jsonl, read_jsonl
    p = tmp_path / "rows.jsonl"
    write_jsonl(p, [{"i": 0}, {"i": 1}])
    write_jsonl(p, [{"i": 2}])
    assert read_jsonl(p) == [{"i": 2}]


def test_now_iso_has_offset():
    from studylib.ioutils import now_iso
    s = now_iso()
    assert "T" in s and ("+" in s or "-" in s[10:] or s.endswith("Z"))


def test_course_lock_creates_lockfile(tmp_path):
    from studylib.ioutils import course_lock
    with course_lock(tmp_path):
        assert (tmp_path / ".study" / "locks" / "state.lock").exists()


def test_course_lock_timeout(tmp_path):
    from studylib.errors import StateLockTimeout
    from studylib.ioutils import course_lock
    outer = course_lock(tmp_path)
    outer.acquire()
    try:
        with pytest.raises(StateLockTimeout):
            with course_lock(tmp_path, timeout=0.2):
                pass
    finally:
        outer.release()
```

注意：filelock 的 `FileLock` 同进程可重入的前提是共享同一个实例；这里 `course_lock()` 每次返回**独立实例**（`thread_local=False`），flock 按 fd 计，第二个实例 acquire 会阻塞直至超时。若实测当前 filelock 版本仍表现为可重入，把 `_CourseLock` 改为基于 `os.open(O_CREAT|O_EXCL)` 的自实现锁并保持同一接口，测试断言不变。

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/test_ioutils.py -v`
Expected: FAIL / ERROR（ModuleNotFoundError: studylib.ioutils）

- [ ] **Step 3: 实现**

`scripts/studylib/errors.py`:
```python
class StudyLoopError(Exception):
    """Base error. CLI catches this, prints args[0] + suggested action, exits 1."""


class CourseNotFound(StudyLoopError): ...
class InvalidWorkspace(StudyLoopError): ...
class InvalidSchema(StudyLoopError): ...
class DuplicateEvent(StudyLoopError): ...
class UnknownQuestion(StudyLoopError): ...
class UnknownKC(StudyLoopError): ...
class StateLockTimeout(StudyLoopError): ...
class ValidationFailed(StudyLoopError): ...
```

`scripts/studylib/ioutils.py`:
```python
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from filelock import FileLock, Timeout

from .errors import StateLockTimeout


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def atomic_write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f"{path.name}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def atomic_write_json(path: Path, obj) -> None:
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    atomic_write_text(path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def append_jsonl(path: Path, obj: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_jsonl(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


class _CourseLock:
    """Non-reentrant course-level lock; raises StateLockTimeout on timeout."""

    def __init__(self, course_root: Path, timeout: float):
        lock_dir = Path(course_root) / ".study" / "locks"
        lock_dir.mkdir(parents=True, exist_ok=True)
        self._lock = FileLock(str(lock_dir / "state.lock"), thread_local=False)
        self._timeout = timeout

    def acquire(self):
        try:
            self._lock.acquire(timeout=self._timeout)
        except Timeout as e:
            raise StateLockTimeout(
                f"course is locked by another study-loop process: {self._lock.lock_file}"
            ) from e

    def release(self):
        self._lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
        return False


def course_lock(course_root: Path, timeout: float = 10.0) -> _CourseLock:
    return _CourseLock(course_root, timeout)
```

注意：两个 `course_lock()` 返回的对象各自持有独立 `FileLock(thread_local=False)`，同进程二次 acquire 即超时（flock 按 fd 计）。若实测 filelock 在同进程对同一路径仍表现为可重入，将 `_CourseLock` 改为基于 `os.open(O_CREAT|O_EXCL)` 的自实现锁并保持同一接口。

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m pytest tests/test_ioutils.py -v`
Expected: 6 passed（若锁超时测试因 filelock 行为不稳定，按 Step 3 注意事项修正后必须全绿）

- [ ] **Step 5: Commit**

```bash
git add scripts/studylib/errors.py scripts/studylib/ioutils.py tests/test_ioutils.py
git commit -m "feat: atomic write, jsonl store, course lock, error taxonomy

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Schema 与词表（pydantic 模型）

**Files:**
- Create: `scripts/studylib/schemas.py`
- Test: `tests/test_schemas.py`

**Interfaces:**
- Produces:
  - 常量：`SCHEMA_VERSION="2.0"`，集合 `EVENT_TYPES`（§8.4 全部 30 个）、`ERROR_TYPES`（§12.3 全部 14 个）、`CHANGED_DIMENSIONS`（§15.7 全部 8 个）、`SOURCE_TYPES`（§17.2 全部 10 个）、`CARD_TYPES`（§26.2 全部 5 个）、元组 `TRANSFER_LEVELS=("T0","T1","T2","T3","T4")`、映射 `TRANSFER_KEY={"T0":"T0_original","T1":"T1_near","T2":"T2_structural","T3":"T3_discrimination","T4":"T4_far"}`。
  - `Event(BaseModel)`: 字段 `schema_version, event_id, timestamp, event_type, course_id, session_id="session_adhoc", actor="student", source="main_session", payload: dict`；`event_type` 校验必须 ∈ EVENT_TYPES。
  - `ValidationBlock(BaseModel)`: `generator: dict, independent_solver: dict, adversarial_review: dict, mechanical_validator: dict | None = None`。
  - `Question(BaseModel)`: `schema_version, question_id, kc_ids: list[str], source_type, transfer_level="T0", stem, answer, solution="", difficulty=0.5, estimated_minutes=5.0, changed_dimensions=[], preserved_dimensions=[], derived_from=[], source_id=None, validation: ValidationBlock|None=None`；`source_type` ∈ SOURCE_TYPES、`transfer_level` ∈ TRANSFER_LEVELS、`changed_dimensions` 每项 ∈ CHANGED_DIMENSIONS。

- [ ] **Step 1: 写失败测试**

`tests/test_schemas.py`:
```python
import pytest
from pydantic import ValidationError


def test_vocab_sizes():
    from studylib import schemas as S
    assert len(S.EVENT_TYPES) == 30
    assert len(S.ERROR_TYPES) == 14
    assert len(S.CHANGED_DIMENSIONS) == 8
    assert len(S.SOURCE_TYPES) == 10
    assert len(S.CARD_TYPES) == 5
    assert S.TRANSFER_LEVELS == ("T0", "T1", "T2", "T3", "T4")
    assert S.TRANSFER_KEY["T2"] == "T2_structural"


def test_event_roundtrip_and_defaults():
    from studylib.schemas import Event
    ev = Event(
        event_id="evt_x", timestamp="2026-07-15T14:32:18+08:00",
        event_type="question_attempted", course_id="c1",
        payload={"question_id": "q1", "correct": False},
    )
    d = ev.model_dump()
    assert d["schema_version"] == "2.0"
    assert d["session_id"] == "session_adhoc"
    assert d["actor"] == "student"


def test_event_rejects_unknown_type():
    from studylib.schemas import Event
    with pytest.raises(ValidationError):
        Event(event_id="e", timestamp="t", event_type="nope", course_id="c")


def test_question_validation_vocab():
    from studylib.schemas import Question
    q = Question(
        question_id="syn_q_018", kc_ids=["feedback_topology"], source_type="synthetic",
        transfer_level="T2", stem="...", answer="B",
        changed_dimensions=["question_direction", "information_structure"],
        preserved_dimensions=["core_kc", "target_capability", "cognitive_trap"],
        derived_from=["kc:feedback_topology", "error:err_001", "question:past_2023_q17"],
    )
    assert q.transfer_level == "T2"
    with pytest.raises(ValidationError):
        Question(question_id="q", kc_ids=["k"], source_type="not_a_source",
                 stem="s", answer="a")
    with pytest.raises(ValidationError):
        Question(question_id="q", kc_ids=["k"], source_type="synthetic",
                 stem="s", answer="a", changed_dimensions=["magic"])
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/test_schemas.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

`scripts/studylib/schemas.py`:
```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

SCHEMA_VERSION = "2.0"

EVENT_TYPES = {
    "course_initialized", "material_ingested", "source_registered", "kc_created",
    "kc_updated", "profile_updated", "session_started", "session_finished",
    "question_registered", "question_presented", "confidence_recorded",
    "question_attempted", "answer_graded", "hint_requested",
    "misconception_identified", "repair_started", "repair_step_completed",
    "repair_completed", "transfer_test_created", "transfer_test_attempted",
    "fsrs_card_created", "fsrs_reviewed", "milestone_created", "milestone_updated",
    "mock_exam_created", "mock_exam_completed", "exam_feedback_submitted",
    "state_recalibrated", "attempt_package_imported", "state_rebuilt",
}

ERROR_TYPES = {
    "concept_misconception", "prerequisite_gap", "condition_misread",
    "procedure_omission", "formula_misuse", "representation_failure",
    "transfer_failure", "similar_concept_confusion", "calculation_slip",
    "memory_failure", "strategy_failure", "time_pressure_failure",
    "careless_error", "unknown",
}

TRANSFER_LEVELS = ("T0", "T1", "T2", "T3", "T4")

TRANSFER_KEY = {
    "T0": "T0_original", "T1": "T1_near", "T2": "T2_structural",
    "T3": "T3_discrimination", "T4": "T4_far",
}

CHANGED_DIMENSIONS = {
    "surface_context", "information_structure", "question_direction",
    "condition_combination", "reasoning_order", "representation",
    "distractor_mechanism", "required_identification",
}

SOURCE_TYPES = {
    "syllabus", "textbook", "lecture_slide", "course_note", "homework",
    "past_exam", "teacher_emphasis", "student_input", "synthetic",
    "external_reference",
}

CARD_TYPES = {
    "original_question", "transfer_question", "concept_recall",
    "procedure_recall", "misconception_check",
}


class Event(BaseModel):
    schema_version: str = SCHEMA_VERSION
    event_id: str
    timestamp: str
    event_type: str
    course_id: str
    session_id: str = "session_adhoc"
    actor: str = "student"
    source: str = "main_session"
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def _known_event_type(cls, v: str) -> str:
        if v not in EVENT_TYPES:
            raise ValueError(f"unknown event_type: {v}")
        return v


class ValidationBlock(BaseModel):
    generator: dict[str, Any]
    independent_solver: dict[str, Any]
    adversarial_review: dict[str, Any]
    mechanical_validator: dict[str, Any] | None = None


class Question(BaseModel):
    schema_version: str = SCHEMA_VERSION
    question_id: str
    kc_ids: list[str]
    source_type: str
    transfer_level: Literal["T0", "T1", "T2", "T3", "T4"] = "T0"
    stem: str
    answer: str
    solution: str = ""
    difficulty: float = 0.5
    estimated_minutes: float = 5.0
    changed_dimensions: list[str] = Field(default_factory=list)
    preserved_dimensions: list[str] = Field(default_factory=list)
    derived_from: list[str] = Field(default_factory=list)
    source_id: str | None = None
    validation: ValidationBlock | None = None

    @field_validator("source_type")
    @classmethod
    def _known_source_type(cls, v: str) -> str:
        if v not in SOURCE_TYPES:
            raise ValueError(f"unknown source_type: {v}")
        return v

    @field_validator("changed_dimensions")
    @classmethod
    def _known_dimensions(cls, v: list[str]) -> list[str]:
        bad = [d for d in v if d not in CHANGED_DIMENSIONS]
        if bad:
            raise ValueError(f"unknown changed_dimensions: {bad}")
        return v
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m pytest tests/test_schemas.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/studylib/schemas.py tests/test_schemas.py
git commit -m "feat: pydantic schemas and controlled vocabularies (spec §8/§12/§15/§17/§26)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: 事件存储（append-only + 去重）

**Files:**
- Create: `scripts/studylib/events.py`
- Test: `tests/test_events.py`

**Interfaces:**
- Consumes: `ioutils.append_jsonl/read_jsonl/now_iso`, `schemas.Event`, `errors.DuplicateEvent`
- Produces:
  - `events.events_path(root: Path) -> Path`（`root/.study/events.jsonl`）
  - `events.new_event(course_id: str, event_type: str, payload: dict | None = None, *, session_id="session_adhoc", actor="student", source="main_session") -> dict`（生成 `evt_` + uuid4 hex 前 12 位的 event_id、本地时区时间戳）
  - `events.append_event(root: Path, event: dict, *, check_duplicate: bool = False) -> dict`（pydantic 校验后追加；check_duplicate=True 时扫描重复 event_id → `DuplicateEvent`）
  - `events.read_events(root: Path) -> list[dict]`

- [ ] **Step 1: 写失败测试**

`tests/test_events.py`:
```python
import pytest


def test_new_event_shape(tmp_path):
    from studylib.events import new_event
    ev = new_event("c1", "kc_created", {"kc_id": "k1", "name": "K"})
    assert ev["event_id"].startswith("evt_") and len(ev["event_id"]) == 16
    assert ev["schema_version"] == "2.0"
    assert ev["event_type"] == "kc_created"
    assert ev["payload"]["kc_id"] == "k1"


def test_append_and_read(tmp_path):
    from studylib.events import append_event, new_event, read_events
    e1 = append_event(tmp_path, new_event("c1", "course_initialized", {}))
    e2 = append_event(tmp_path, new_event("c1", "kc_created", {"kc_id": "k1"}))
    evs = read_events(tmp_path)
    assert [e["event_id"] for e in evs] == [e1["event_id"], e2["event_id"]]


def test_duplicate_event_rejected(tmp_path):
    from studylib.errors import DuplicateEvent
    from studylib.events import append_event, new_event
    ev = new_event("c1", "course_initialized", {})
    append_event(tmp_path, ev)
    with pytest.raises(DuplicateEvent):
        append_event(tmp_path, ev, check_duplicate=True)


def test_append_rejects_bad_event(tmp_path):
    from studylib.errors import InvalidSchema
    from studylib.events import append_event
    with pytest.raises(InvalidSchema):
        append_event(tmp_path, {"event_type": "nope"})
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/test_events.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

`scripts/studylib/events.py`:
```python
from __future__ import annotations

import uuid
from pathlib import Path

from pydantic import ValidationError

from .errors import DuplicateEvent, InvalidSchema
from .ioutils import append_jsonl, now_iso, read_jsonl
from .schemas import Event


def events_path(root: Path) -> Path:
    return Path(root) / ".study" / "events.jsonl"


def new_event(
    course_id: str,
    event_type: str,
    payload: dict | None = None,
    *,
    session_id: str = "session_adhoc",
    actor: str = "student",
    source: str = "main_session",
) -> dict:
    return Event(
        event_id=f"evt_{uuid.uuid4().hex[:12]}",
        timestamp=now_iso(),
        event_type=event_type,
        course_id=course_id,
        session_id=session_id,
        actor=actor,
        source=source,
        payload=payload or {},
    ).model_dump()


def append_event(root: Path, event: dict, *, check_duplicate: bool = False) -> dict:
    try:
        ev = Event.model_validate(event).model_dump()
    except ValidationError as e:
        raise InvalidSchema(f"invalid event: {e}") from e
    if check_duplicate:
        seen = {x["event_id"] for x in read_jsonl(events_path(root))}
        if ev["event_id"] in seen:
            raise DuplicateEvent(f"duplicate event_id: {ev['event_id']}")
    append_jsonl(events_path(root), ev)
    return ev


def read_events(root: Path) -> list[dict]:
    return read_jsonl(events_path(root))
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m pytest tests/test_events.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/studylib/events.py tests/test_events.py
git commit -m "feat: append-only event store with dedup (spec §8)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: 课程工作区初始化与全局注册表

**Files:**
- Create: `scripts/studylib/paths.py`, `scripts/studylib/course.py`
- Test: `tests/test_course.py`
- Modify: `tests/conftest.py`（追加 `course` fixture）

**Interfaces:**
- Consumes: `events.append_event/new_event`, `ioutils.atomic_write_text/atomic_write_json/now_iso`, `errors.CourseNotFound/InvalidWorkspace`
- Produces:
  - `paths.study_home() -> Path`（env `STUDY_LOOP_HOME` 或 `~/.study-loop`）
  - `paths.find_course_root(start: Path | None = None) -> Path`（向上找 `course.yaml`，找不到 → `CourseNotFound`）
  - `paths.study_dir(root: Path) -> Path`
  - `course.init_course(path: Path, course_id: str, name: str, exam_date: str | None = None) -> Path`（建目录树、写 course.yaml、写 course_initialized 事件、全局注册）
  - `course.load_course(root: Path) -> dict`
  - `course.register_course_globally(course_id: str, root: Path) -> None`（更新 `study_home()/registry.json`）
  - `course.DEFAULT_PROFILE: dict`（六维混合向量 + confidence，§18.1 结构）

- [ ] **Step 1: 写失败测试**

`tests/test_course.py`:
```python
import json

import pytest
import yaml


def test_init_course_scaffold(tmp_path, home):
    from studylib.course import init_course
    root = init_course(tmp_path / "模电", "analog-electronics", "模拟电子技术", "2026-07-25")
    for d in [
        "materials/syllabus", "materials/textbook", "materials/slides",
        "materials/homework", "materials/past-exams", "materials/notes",
        "notes", "output", ".study/locks", ".study/cache",
    ]:
        assert (root / d).is_dir(), d
    cy = yaml.safe_load((root / "course.yaml").read_text(encoding="utf-8"))
    assert cy["id"] == "analog-electronics"
    assert cy["name"] == "模拟电子技术"
    assert cy["exam_date"] == "2026-07-25"
    assert cy["schema_version"] == "2.0"
    assert set(cy["profile"]) == {
        "quantitative", "conceptual", "procedural", "programming",
        "language", "memory", "confidence",
    }


def test_init_writes_event_and_registry(tmp_path, home):
    from studylib.course import init_course
    from studylib.events import read_events
    root = init_course(tmp_path / "c", "c1", "课程一", None)
    evs = read_events(root)
    assert evs[0]["event_type"] == "course_initialized"
    reg = json.loads((home / "registry.json").read_text(encoding="utf-8"))
    assert reg["courses"]["c1"]["path"] == str(root)


def test_init_refuses_existing_workspace(tmp_path, home):
    from studylib.course import init_course
    from studylib.errors import InvalidWorkspace
    init_course(tmp_path / "c", "c1", "课程一", None)
    with pytest.raises(InvalidWorkspace):
        init_course(tmp_path / "c", "c1", "课程一", None)


def test_find_course_root(tmp_path, home):
    from studylib.course import init_course
    from studylib.errors import CourseNotFound
    from studylib.paths import find_course_root
    root = init_course(tmp_path / "c", "c1", "课程一", None)
    sub = root / "materials" / "slides"
    assert find_course_root(sub) == root
    with pytest.raises(CourseNotFound):
        find_course_root(tmp_path / "elsewhere")
```

`tests/conftest.py` 追加（保留原有内容）:
```python
@pytest.fixture
def course(tmp_path, home):
    from studylib.course import init_course
    return init_course(tmp_path / "模电", "analog-electronics", "模拟电子技术", "2026-07-25")
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/test_course.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

`scripts/studylib/paths.py`:
```python
from __future__ import annotations

import os
from pathlib import Path

from .errors import CourseNotFound


def study_home() -> Path:
    return Path(os.environ.get("STUDY_LOOP_HOME", str(Path.home() / ".study-loop")))


def find_course_root(start: Path | None = None) -> Path:
    p = Path(start or Path.cwd()).resolve()
    for cand in (p, *p.parents):
        if (cand / "course.yaml").is_file():
            return cand
    raise CourseNotFound(
        f"course.yaml not found from {p}. cd into a course workspace or run init_course.py first."
    )


def study_dir(root: Path) -> Path:
    return Path(root) / ".study"
```

`scripts/studylib/course.py`:
```python
from __future__ import annotations

import json
from pathlib import Path

import yaml

from .errors import InvalidWorkspace
from .events import append_event, new_event
from .ioutils import atomic_write_json, atomic_write_text, now_iso
from .paths import study_home
from .schemas import SCHEMA_VERSION

DEFAULT_PROFILE = {
    "quantitative": 0.3, "conceptual": 0.3, "procedural": 0.2,
    "programming": 0.0, "language": 0.0, "memory": 0.2,
    "confidence": 0.3,
}

WORKSPACE_DIRS = [
    "materials/syllabus", "materials/textbook", "materials/slides",
    "materials/homework", "materials/past-exams", "materials/notes",
    "notes", "output", ".study/locks", ".study/cache",
]


def init_course(path: Path, course_id: str, name: str, exam_date: str | None = None) -> Path:
    root = Path(path)
    if (root / "course.yaml").exists():
        raise InvalidWorkspace(f"course.yaml already exists in {root}")
    for d in WORKSPACE_DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)
    doc = {
        "schema_version": SCHEMA_VERSION,
        "id": course_id,
        "name": name,
        "exam_date": exam_date,
        "created_at": now_iso(),
        "profile": dict(DEFAULT_PROFILE),
    }
    atomic_write_text(root / "course.yaml", yaml.safe_dump(doc, allow_unicode=True, sort_keys=False))
    append_event(root, new_event(course_id, "course_initialized", {"name": name, "exam_date": exam_date}))
    register_course_globally(course_id, root)
    return root


def load_course(root: Path) -> dict:
    return yaml.safe_load((Path(root) / "course.yaml").read_text(encoding="utf-8"))


def register_course_globally(course_id: str, root: Path) -> None:
    home = study_home()
    home.mkdir(parents=True, exist_ok=True)
    reg_path = home / "registry.json"
    if reg_path.exists():
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
    else:
        reg = {"schema_version": SCHEMA_VERSION, "courses": {}}
    reg["courses"][course_id] = {"path": str(Path(root)), "registered_at": now_iso()}
    atomic_write_json(reg_path, reg)
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m pytest tests/test_course.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/studylib/paths.py scripts/studylib/course.py tests/test_course.py tests/conftest.py
git commit -m "feat: course workspace init and global registry (spec §6.2/§6.3)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: 派生注册表（KC / 题目 / 来源）

**Files:**
- Create: `scripts/studylib/registry.py`
- Test: `tests/test_registry.py`

**Interfaces:**
- Consumes: 事件 dict 列表（`events.read_events` 的输出）
- Produces:
  - `registry.build_kcs(events: list[dict]) -> dict[str, dict]`：从 `kc_created`/`kc_updated` 构建。每个 KC dict 字段：`kc_id, name, chapter_id, prerequisites: list[str], exam_weight: float(默认0.5), source_ids: list[str], explained: bool`。`kc_updated` payload 支持 `{"kc_id":..., "update":"explained"}` 置 explained=True，及覆盖 `name/exam_weight/prerequisites/chapter_id`；未知 kc_id → `UnknownKC`。
  - `registry.build_questions(events) -> dict[str, dict]`：从 `question_registered` 和 `transfer_test_created` 构建；payload 即 Question dict（键为 question_id）。
  - `registry.build_sources(events) -> list[dict]`：`source_registered` 的 payload 列表。

- [ ] **Step 1: 写失败测试**

`tests/test_registry.py`:
```python
import pytest


def _ev(etype, payload):
    from studylib.events import new_event
    return new_event("c1", etype, payload)


def test_build_kcs_create_update_explained():
    from studylib.registry import build_kcs
    events = [
        _ev("kc_created", {"kc_id": "k1", "name": "反馈组态判断", "chapter_id": "ch6",
                           "prerequisites": [], "exam_weight": 0.9}),
        _ev("kc_created", {"kc_id": "k2", "name": "深度负反馈", "chapter_id": "ch6",
                           "prerequisites": ["k1"]}),
        _ev("kc_updated", {"kc_id": "k1", "update": "explained"}),
        _ev("kc_updated", {"kc_id": "k2", "exam_weight": 0.8}),
    ]
    kcs = build_kcs(events)
    assert kcs["k1"]["explained"] is True
    assert kcs["k1"]["exam_weight"] == 0.9
    assert kcs["k2"]["prerequisites"] == ["k1"]
    assert kcs["k2"]["exam_weight"] == 0.8
    assert kcs["k2"]["explained"] is False


def test_kc_updated_unknown_raises():
    from studylib.errors import UnknownKC
    from studylib.registry import build_kcs
    with pytest.raises(UnknownKC):
        build_kcs([_ev("kc_updated", {"kc_id": "ghost", "update": "explained"})])


def test_build_questions_from_both_event_types():
    from studylib.registry import build_questions
    q1 = {"question_id": "past_2023_q17", "kc_ids": ["k1"], "source_type": "past_exam",
          "transfer_level": "T0", "stem": "s", "answer": "A"}
    q2 = {"question_id": "syn_q_018", "kc_ids": ["k1"], "source_type": "synthetic",
          "transfer_level": "T2", "stem": "s2", "answer": "B",
          "retest_of_error_id": "err_001"}
    qs = build_questions([_ev("question_registered", q1), _ev("transfer_test_created", q2)])
    assert set(qs) == {"past_2023_q17", "syn_q_018"}
    assert qs["syn_q_018"]["transfer_level"] == "T2"


def test_build_sources():
    from studylib.registry import build_sources
    src = {"source_id": "src_012", "source_type": "lecture_slide",
           "file": "materials/slides/chapter6.pdf", "sha256": "sha256:x", "pages": [12, 13]}
    assert build_sources([_ev("source_registered", src)]) == [src]
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/test_registry.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

`scripts/studylib/registry.py`:
```python
from __future__ import annotations

from .errors import UnknownKC


def build_kcs(events: list[dict]) -> dict[str, dict]:
    kcs: dict[str, dict] = {}
    for e in events:
        t = e["event_type"]
        p = e["payload"]
        if t == "kc_created":
            kcs[p["kc_id"]] = {
                "kc_id": p["kc_id"],
                "name": p.get("name", p["kc_id"]),
                "chapter_id": p.get("chapter_id"),
                "prerequisites": list(p.get("prerequisites", [])),
                "exam_weight": float(p.get("exam_weight", 0.5)),
                "source_ids": list(p.get("source_ids", [])),
                "explained": False,
            }
        elif t == "kc_updated":
            kc = kcs.get(p["kc_id"])
            if kc is None:
                raise UnknownKC(f"kc_updated for unknown kc_id: {p['kc_id']}")
            if p.get("update") == "explained":
                kc["explained"] = True
            for field in ("name", "exam_weight", "prerequisites", "chapter_id"):
                if field in p:
                    kc[field] = p[field]
    return kcs


def build_questions(events: list[dict]) -> dict[str, dict]:
    qs: dict[str, dict] = {}
    for e in events:
        if e["event_type"] in ("question_registered", "transfer_test_created"):
            p = e["payload"]
            qs[p["question_id"]] = p
    return qs


def build_sources(events: list[dict]) -> list[dict]:
    return [e["payload"] for e in events if e["event_type"] == "source_registered"]
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m pytest tests/test_registry.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/studylib/registry.py tests/test_registry.py
git commit -m "feat: derive KC/question/source registries from events (spec §9/§17)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: 证据构建与 Misconception Memory

**Files:**
- Create: `scripts/studylib/evidence.py`, `scripts/studylib/misconceptions.py`
- Test: `tests/test_evidence.py`, `tests/test_misconceptions.py`

**Interfaces:**
- Consumes: 事件列表、`registry.build_questions` 的输出
- Produces:
  - `evidence.build_evidence(events: list[dict], questions: dict[str, dict]) -> list[dict]`：把每个 `question_attempted`/`transfer_test_attempted` 事件变成一条证据（§11 schema）。字段：`schema_version, evidence_id("evd_"+event_id[4:]), course_id, kc_ids（取 payload.kc_ids，缺省回退题目注册的 kc_ids）, evidence_type="question_attempt", question_id, result{correct,score}, confidence_before, hint_level(默认0), response_time_sec, transfer_level（从题目注册表查，未注册题默认"T0"）, source_event_id, weight=1.0, created_at`。
  - `misconceptions.build_misconceptions(events, questions) -> dict[str, dict]`（error_id → §12.4 schema dict）。规则：
    - `misconception_identified`：按 `(kc_ids[0], error_type, wrong_assumption)` 合并——已存在则 `recurrence_count+=1`、更新 `last_seen_at`、并集 `trigger_conditions`、追加 `origin_question_ids`；否则新建（error_id = payload.error_id 或 `"err_"+event_id[4:]`，`repair_status="active"`，`recurrence_count=1`）。
    - `repair_started` payload `{error_id, repair_id}` → status="repairing"，repair_history 追加 repair_id。
    - `repair_completed` payload `{error_id}` → status="retest_pending"。
    - `question_attempted`/`transfer_test_attempted` 带 `payload.retest_of_error_id`：查题目 transfer_level；答对 → `retests_passed` 追加 `{"question_id", "level"}`；答错 → status 回 "active"，且 level≠"T0" 时 `transfer_failures` 追加 question_id。
    - 收尾：status=="retest_pending" 且 retests_passed 同时覆盖 "T0" 和（"T1" 或 "T2"）→ status="resolved"。
  - `misconceptions.active_high_confidence(miscs: dict, kc_id: str, threshold: float = 0.75) -> bool`：该 KC 是否存在未 resolved 且 `confidence_before >= threshold` 的错因。

- [ ] **Step 1: 写失败测试**

`tests/test_evidence.py`:
```python
def _attempt(qid, correct, *, conf=None, hint=0, kc_ids=None, retest=None, etype="question_attempted"):
    from studylib.events import new_event
    p = {"question_id": qid, "correct": correct, "hint_level": hint}
    if conf is not None:
        p["confidence_before"] = conf
    if kc_ids:
        p["kc_ids"] = kc_ids
    if retest:
        p["retest_of_error_id"] = retest
    return new_event("c1", etype, p)


QS = {
    "past_2023_q17": {"question_id": "past_2023_q17", "kc_ids": ["k1"],
                      "source_type": "past_exam", "transfer_level": "T0"},
    "syn_q_018": {"question_id": "syn_q_018", "kc_ids": ["k1"],
                  "source_type": "synthetic", "transfer_level": "T2"},
}


def test_evidence_from_attempt():
    from studylib.evidence import build_evidence
    ev = _attempt("past_2023_q17", False, conf=0.9)
    rows = build_evidence([ev], QS)
    assert len(rows) == 1
    r = rows[0]
    assert r["evidence_id"] == "evd_" + ev["event_id"][4:]
    assert r["kc_ids"] == ["k1"]
    assert r["result"] == {"correct": False, "score": 0.0}
    assert r["confidence_before"] == 0.9
    assert r["transfer_level"] == "T0"
    assert r["source_event_id"] == ev["event_id"]


def test_evidence_transfer_level_from_registry():
    from studylib.evidence import build_evidence
    rows = build_evidence([_attempt("syn_q_018", True, etype="transfer_test_attempted")], QS)
    assert rows[0]["transfer_level"] == "T2"
    assert rows[0]["result"]["score"] == 1.0


def test_evidence_unregistered_question_defaults_t0():
    from studylib.evidence import build_evidence
    rows = build_evidence([_attempt("mystery_q", True, kc_ids=["k9"])], {})
    assert rows[0]["transfer_level"] == "T0"
    assert rows[0]["kc_ids"] == ["k9"]
```

`tests/test_misconceptions.py`:
```python
def _ev(etype, payload):
    from studylib.events import new_event
    return new_event("c1", etype, payload)


MISC = {
    "kc_ids": ["k1"], "origin_question_id": "past_2023_q17",
    "wrong_assumption": "输出端存在反馈连接即可视为电压反馈",
    "missing_premise": "必须检查反馈网络对输出端的取样方式",
    "error_type": "concept_misconception",
    "trigger_conditions": ["复杂电路图"],
    "confidence_before": 0.9, "attribution_confidence": 0.82,
}

QS = {
    "past_2023_q17": {"question_id": "past_2023_q17", "kc_ids": ["k1"],
                      "source_type": "past_exam", "transfer_level": "T0"},
    "syn_t1": {"question_id": "syn_t1", "kc_ids": ["k1"],
               "source_type": "synthetic", "transfer_level": "T1"},
    "syn_t2": {"question_id": "syn_t2", "kc_ids": ["k1"],
               "source_type": "synthetic", "transfer_level": "T2"},
}


def test_new_misconception_defaults():
    from studylib.misconceptions import build_misconceptions
    ms = build_misconceptions([_ev("misconception_identified", MISC)], QS)
    (m,) = ms.values()
    assert m["repair_status"] == "active"
    assert m["recurrence_count"] == 1
    assert m["error_type"] == "concept_misconception"
    assert m["error_id"].startswith("err_")


def test_recurrence_merges_by_kc_and_type():
    from studylib.misconceptions import build_misconceptions
    again = dict(MISC, trigger_conditions=["多个输出节点"], origin_question_id="hw_q3")
    ms = build_misconceptions(
        [_ev("misconception_identified", MISC), _ev("misconception_identified", again)], QS)
    (m,) = ms.values()
    assert m["recurrence_count"] == 2
    assert set(m["trigger_conditions"]) == {"复杂电路图", "多个输出节点"}


def test_repair_and_dual_track_retest_resolves():
    from studylib.misconceptions import build_misconceptions
    e0 = _ev("misconception_identified", dict(MISC, error_id="err_001"))
    events = [
        e0,
        _ev("repair_started", {"error_id": "err_001", "repair_id": "repair_012"}),
        _ev("repair_completed", {"error_id": "err_001"}),
        _ev("question_attempted", {"question_id": "past_2023_q17", "correct": True,
                                   "retest_of_error_id": "err_001"}),
        _ev("transfer_test_attempted", {"question_id": "syn_t1", "correct": True,
                                        "retest_of_error_id": "err_001"}),
    ]
    ms = build_misconceptions(events, QS)
    m = ms["err_001"]
    assert m["repair_status"] == "resolved"
    assert m["repair_history"] == ["repair_012"]


def test_failed_transfer_retest_reactivates():
    from studylib.misconceptions import build_misconceptions
    events = [
        _ev("misconception_identified", dict(MISC, error_id="err_001")),
        _ev("repair_completed", {"error_id": "err_001"}),
        _ev("transfer_test_attempted", {"question_id": "syn_t2", "correct": False,
                                        "retest_of_error_id": "err_001"}),
    ]
    m = build_misconceptions(events, QS)["err_001"]
    assert m["repair_status"] == "active"
    assert m["transfer_failures"] == ["syn_t2"]


def test_active_high_confidence_helper():
    from studylib.misconceptions import active_high_confidence, build_misconceptions
    ms = build_misconceptions([_ev("misconception_identified", dict(MISC, error_id="err_001"))], QS)
    assert active_high_confidence(ms, "k1") is True
    assert active_high_confidence(ms, "k2") is False
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/test_evidence.py tests/test_misconceptions.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

`scripts/studylib/evidence.py`:
```python
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
```

`scripts/studylib/misconceptions.py`:
```python
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
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m pytest tests/test_evidence.py tests/test_misconceptions.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/studylib/evidence.py scripts/studylib/misconceptions.py tests/test_evidence.py tests/test_misconceptions.py
git commit -m "feat: evidence builder and misconception memory with dual-track retest (spec §11/§12/§25)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: KC 聚合与六态派生规则

**Files:**
- Create: `scripts/studylib/state_rules.py`
- Test: `tests/test_state_rules.py`

**Interfaces:**
- Consumes: `registry.build_kcs` 输出、`evidence.build_evidence` 输出、`misconceptions.build_misconceptions` 输出 + `active_high_confidence`
- Produces:
  - `state_rules.DeriveConfig`（dataclass，可调阈值）：`independent_hint_max=1, weak_success_floor=0.5, retention_min_days=1.0, high_conf_threshold=0.75, transfer_window=3`
  - `state_rules.kc_aggregate(kc_id: str, evidence: list[dict], cfg: DeriveConfig) -> dict`：按时间排序该 KC 的证据并聚合。返回键：`attempts`（排序后的证据行）、`independent_corrects`（correct 且 hint_level<=independent_hint_max 的行）、`observed`（正确率或 None）、`self_estimate`（confidence_before 均值或 None）、`gap`（self-observed 或 None）、`blind_spot`（self×(1-observed) 或 0.0）、`transfer_mean`（{T0..T4: 最近 transfer_window 次该层正确率或 None}）、`transfer_last`（{T0..T4: 最近一次该层是否正确或 None}）、`last_hint_level`、`independent_success_rate`（hint==0 且 correct / 总次数，或 None）、`retention_ok`（两次独立正确间隔 ≥ retention_min_days 天）、`recent_transfer_failure`（任一 T1+ 层最近一次为错）。
  - `state_rules.teaching_state(kc: dict, agg: dict, prereq_states: dict[str, str], high_conf_active: bool, cfg) -> str`：按 §37 规则返回 `unseen/explained/practiced/checked/confirmed/weak/blocked` 之一。判定次序：blocked → unseen → weak → confirmed → checked → practiced → explained（blocked 优先于 unseen：前置薄弱的未学 KC 判 blocked，防止被 advance 推荐选中）。
  - `state_rules.compute_kc_states(kcs, evidence, miscs, retention_by_kc=None, cfg=None) -> dict[str, dict]`：按前置拓扑序逐个判定（前置状态影响 blocked），产出 kc.json 行（§10.4 结构）：`schema_version, kc_id, name, chapter_id, prerequisites, exam_weight, teaching_state, retention{fsrs_card_ids,retrievability,due_count}, transfer{T0_original..T4_far}（取 transfer_mean 按 TRANSFER_KEY 改名）, calibration{self_estimate,observed_performance,gap,blind_spot}, assistance{last_hint_level,independent_success_rate}, evidence_ids, active_misconceptions（未 resolved 的 error_id 列表）, updated_at`。

- [ ] **Step 1: 写失败测试**

`tests/test_state_rules.py`:
```python
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=8))
T0 = datetime(2026, 7, 10, 10, 0, 0, tzinfo=TZ)


def _row(kc, correct, *, hint=0, level="T0", conf=None, at_hours=0):
    return {
        "kc_ids": [kc], "result": {"correct": correct, "score": 1.0 if correct else 0.0},
        "hint_level": hint, "transfer_level": level, "confidence_before": conf,
        "created_at": (T0 + timedelta(hours=at_hours)).isoformat(),
        "evidence_id": f"evd_{kc}_{at_hours}", "question_id": f"q_{at_hours}",
    }


def _kc(kc_id, prereqs=(), explained=False, weight=0.5):
    return {"kc_id": kc_id, "name": kc_id, "chapter_id": None,
            "prerequisites": list(prereqs), "exam_weight": weight,
            "source_ids": [], "explained": explained}


def _states(kcs, evidence, miscs=None):
    from studylib.state_rules import compute_kc_states
    return compute_kc_states(kcs, evidence, miscs or {})


def test_unseen_and_explained():
    kcs = {"a": _kc("a"), "b": _kc("b", explained=True)}
    out = _states(kcs, [])
    assert out["a"]["teaching_state"] == "unseen"
    assert out["b"]["teaching_state"] == "explained"


def test_practiced_when_only_assisted_success():
    # L4 提示下答对 → 不允许 checked（spec §14.1 / 场景 C）
    out = _states({"a": _kc("a")}, [_row("a", True, hint=4)])
    assert out["a"]["teaching_state"] == "practiced"


def test_checked_on_independent_correct():
    out = _states({"a": _kc("a")}, [_row("a", True, hint=1)])
    assert out["a"]["teaching_state"] == "checked"


def test_weak_on_last_wrong_and_high_conf_misconception():
    out = _states({"a": _kc("a")}, [_row("a", True), _row("a", False, conf=0.9, at_hours=1)])
    assert out["a"]["teaching_state"] == "weak"
    miscs = {"err_1": {"error_id": "err_1", "kc_ids": ["a"], "repair_status": "active",
                       "confidence_before": 0.9}}
    out2 = _states({"a": _kc("a")}, [_row("a", True)], miscs)
    assert out2["a"]["teaching_state"] == "weak"
    assert out2["a"]["active_misconceptions"] == ["err_1"]


def test_confirmed_needs_retention_and_transfer():
    rows = [
        _row("a", True, at_hours=0),
        _row("a", True, level="T1", at_hours=30),  # 隔 >1 天 + T1 通过
    ]
    out = _states({"a": _kc("a")}, rows)
    assert out["a"]["teaching_state"] == "confirmed"
    # 无迁移证据 → 只能 checked
    rows_no_transfer = [_row("a", True, at_hours=0), _row("a", True, at_hours=30)]
    out2 = _states({"a": _kc("a")}, rows_no_transfer)
    assert out2["a"]["teaching_state"] == "checked"


def test_blocked_by_weak_prerequisite():
    kcs = {"pre": _kc("pre"), "post": _kc("post", prereqs=["pre"])}
    rows = [_row("pre", False), _row("post", True, hint=4, at_hours=1)]
    out = _states(kcs, rows)
    assert out["pre"]["teaching_state"] == "weak"
    assert out["post"]["teaching_state"] == "blocked"


def test_transfer_vector_and_calibration_shape():
    rows = [_row("a", False, conf=0.9), _row("a", True, level="T1", conf=0.8, at_hours=1)]
    out = _states({"a": _kc("a")}, rows)
    kc = out["a"]
    assert kc["transfer"]["T0_original"] == 0.0
    assert kc["transfer"]["T1_near"] == 1.0
    assert kc["transfer"]["T3_discrimination"] is None
    assert kc["calibration"]["self_estimate"] == 0.85
    assert kc["calibration"]["observed_performance"] == 0.5
    assert abs(kc["calibration"]["gap"] - 0.35) < 1e-9
    assert kc["retention"] == {"fsrs_card_ids": [], "retrievability": None, "due_count": 0}
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/test_state_rules.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

`scripts/studylib/state_rules.py`:
```python
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
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m pytest tests/test_state_rules.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/studylib/state_rules.py tests/test_state_rules.py
git commit -m "feat: KC aggregation and six-state teaching rules (spec §10/§13/§37)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: FSRS 存储（确定性重放）

**Files:**
- Create: `scripts/studylib/fsrs_store.py`
- Test: `tests/test_fsrs_store.py`

**Interfaces:**
- Consumes: `fsrs`（py-fsrs 6.x：`Scheduler.review_card(card, rating, review_datetime=...)`、`Card.to_dict()/from_dict()`、`Scheduler.get_card_retrievability(card)`）、事件列表
- Produces:
  - `fsrs_store.new_card_payload(card_type: str, kc_ids: list[str], question_id: str | None = None) -> dict`：校验 card_type ∈ CARD_TYPES（否则 `InvalidSchema`），返回 `fsrs_card_created` 的 payload：`{card_id: "card_"+uuid12, card_type, question_id, kc_ids, fsrs: Card().to_dict()}`。
  - `fsrs_store.replay_cards(events: list[dict]) -> dict[str, dict]`：从 `fsrs_card_created`（payload.fsrs 恢复 Card）与 `fsrs_reviewed`（payload: `{card_id, rating: 1-4, review_time: iso}`，重放 `review_card`，review_datetime 统一转 UTC）确定性重建。每行：`{schema_version, card_id, card_type, question_id, kc_ids, created_at, review_count, last_review, fsrs: card.to_dict(), due: <iso str>}`。
  - `fsrs_store.due_cards(cards: dict[str, dict], now: datetime | None = None) -> list[dict]`：due <= now（UTC）的卡，按 due 升序。
  - `fsrs_store.retention_by_kc(cards, now=None) -> dict[str, dict]`：每 KC `{"fsrs_card_ids": [...], "retrievability": <该KC所有卡的最小可提取度, 无卡则不出现>, "due_count": n}`。
  - `fsrs_store.rating_from_result(correct: bool, confidence: float | None) -> int`：默认评分策略（供 CLI/Agent 参考）：错 → 1(Again)；对且 confidence>=0.75 → 3(Good)；对且 confidence<0.75 → 2(Hard)。Agent 可显式传 rating 覆盖。

- [ ] **Step 1: 写失败测试**

`tests/test_fsrs_store.py`:
```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/test_fsrs_store.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

`scripts/studylib/fsrs_store.py`:
```python
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
```

注意：若 `Scheduler.get_card_retrievability` 在当前 fsrs 版本不接受 `current_datetime` 关键字（以实际签名为准），改为位置参数或省略该参数并接受"以当前时刻计算"，同时把 `test_due_cards_and_retention_by_kc` 里对 retrievability 的断言保持为范围断言（0~1），不要断言具体值。

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m pytest tests/test_fsrs_store.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/studylib/fsrs_store.py tests/test_fsrs_store.py
git commit -m "feat: deterministic FSRS replay store (spec §26)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: next-best-step（可解释加权评分）

**Files:**
- Create: `scripts/studylib/nextstep.py`
- Test: `tests/test_nextstep.py`

**Interfaces:**
- Consumes: `course.load_course` 的 dict、`state_rules.compute_kc_states` 输出、misconceptions dict、`fsrs_store.due_cards` 输出
- Produces:
  - `nextstep.DEFAULT_WEIGHTS: dict`（w1..w8：exam_weight=1.0, urgency=1.0, weakness=1.5, prereq_centrality=0.8, forgetting_risk=1.0, transfer_gap=0.8, blind_spot=1.2, expected_time=0.5）
  - `nextstep.days_to_exam(course: dict, today: date | None = None) -> int | None`
  - `nextstep.compute_next_best_step(course: dict, kc_states: dict[str, dict], miscs: dict[str, dict], due: list[dict], weights: dict | None = None) -> dict`：返回 `{action, kc_id, kc_name, estimated_minutes, priority_score, reasons: list[str]}`。规则：
    - 候选动作按 KC 状态：weak/blocked → `repair`；practiced/explained → `drill`；checked 且迁移有缺口 → `drill`；unseen → `advance`；confirmed → 跳过。
    - 有到期卡 → 追加一个 `review` 候选（estimated_minutes = max(5, 2×到期数)）。
    - 无任何候选 → `{"action": "rest", "reasons": ["没有到期复习，也没有待修复/待推进的知识点"]}`。
    - 每个候选 score = w1·ExamWeight + w2·Urgency + w3·Weakness + w4·PrereqCentrality + w5·ForgettingRisk + w6·TransferGap + w7·BlindSpotRisk − w8·TimeNorm，全部输入归一化 [0,1]。
    - `reasons` 不允许为空：从贡献显著的因子生成人话（如"存在未修复错因（concept_misconception ×3）""其中有高置信度错误""T2 结构迁移未通过""3 张相关卡片到期""是 2 个后续知识点的前置""距考试 10 天""考试权重高"），并总是包含当前状态说明（如"当前状态：weak"）。
  - 组件归一化定义（写进实现注释）：Urgency = clamp(1 − days/60)（无考试日期取 0.3）；Weakness = {weak:1.0, blocked:0.9, practiced:0.6, explained:0.5, unseen:0.4, checked:0.2, confirmed:0.0}；PrereqCentrality = 出度/最大出度；ForgettingRisk = 1 − retrievability（无卡取 0，有到期卡但无 retrievability 取 0.8）；TransferGap：T1/T2 均无证据 → 0.6，有证据 → 1 − min(有证据的层级)（最差层级决定缺口），全通过为 0；BlindSpotRisk = calibration.blind_spot；TimeNorm = estimated_minutes/60 截断到 1。estimated_minutes：repair=12、drill=10、advance=15。

- [ ] **Step 1: 写失败测试**

`tests/test_nextstep.py`:
```python
COURSE = {"id": "c1", "name": "模电", "exam_date": None, "profile": {}}


def _kc_state(kc_id, state, *, weight=0.5, blind=0.0, t1=None, t2=None,
              retention=None, prereqs=()):
    return {
        "kc_id": kc_id, "name": kc_id, "chapter_id": None,
        "prerequisites": list(prereqs), "exam_weight": weight,
        "teaching_state": state,
        "retention": retention or {"fsrs_card_ids": [], "retrievability": None, "due_count": 0},
        "transfer": {"T0_original": None, "T1_near": t1, "T2_structural": t2,
                     "T3_discrimination": None, "T4_far": None},
        "calibration": {"self_estimate": None, "observed_performance": None,
                        "gap": None, "blind_spot": blind},
        "assistance": {"last_hint_level": 0, "independent_success_rate": None},
        "evidence_ids": [], "active_misconceptions": [],
    }


def test_repair_beats_confirmed():
    from studylib.nextstep import compute_next_best_step
    kc_states = {
        "good": _kc_state("good", "confirmed", weight=0.9),
        "bad": _kc_state("bad", "weak", weight=0.9, blind=0.3),
    }
    miscs = {"err_1": {"error_id": "err_1", "kc_ids": ["bad"], "repair_status": "active",
                       "error_type": "concept_misconception", "recurrence_count": 3,
                       "confidence_before": 0.9}}
    rec = compute_next_best_step(COURSE, kc_states, miscs, [])
    assert rec["action"] == "repair"
    assert rec["kc_id"] == "bad"
    assert rec["reasons"], "recommendation must be explainable"
    assert any("错因" in r or "高置信度" in r for r in rec["reasons"])


def test_review_when_only_due_cards():
    from studylib.nextstep import compute_next_best_step
    kc_states = {"good": _kc_state("good", "confirmed")}
    due = [{"card_id": "card_1", "kc_ids": ["good"], "due": "2026-01-01T00:00:00+00:00"}]
    rec = compute_next_best_step(COURSE, kc_states, {}, due)
    assert rec["action"] == "review"
    assert any("到期" in r for r in rec["reasons"])


def test_rest_when_nothing_to_do():
    from studylib.nextstep import compute_next_best_step
    rec = compute_next_best_step(COURSE, {"g": _kc_state("g", "confirmed")}, {}, [])
    assert rec["action"] == "rest"


def test_urgency_uses_exam_date():
    from studylib.nextstep import days_to_exam
    from datetime import date
    assert days_to_exam({"exam_date": "2026-07-25"}, today=date(2026, 7, 15)) == 10
    assert days_to_exam({"exam_date": None}) is None


def test_advance_for_unseen():
    from studylib.nextstep import compute_next_best_step
    rec = compute_next_best_step(COURSE, {"u": _kc_state("u", "unseen")}, {}, [])
    assert rec["action"] == "advance"
    assert rec["kc_id"] == "u"
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/test_nextstep.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

`scripts/studylib/nextstep.py`:
```python
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
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m pytest tests/test_nextstep.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/studylib/nextstep.py tests/test_nextstep.py
git commit -m "feat: explainable weighted next-best-step (spec §23)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 11: 派生编排器、state.json、dashboard 与 rebuild

**Files:**
- Create: `scripts/studylib/derive.py`, `scripts/studylib/dashboard.py`, `templates/dashboard.md.j2`
- Test: `tests/test_derive.py`

**Interfaces:**
- Consumes: 前面所有模块
- Produces:
  - `derive.derive(root: Path, *, write: bool = True, cfg: DeriveConfig | None = None) -> dict`：读事件 → 构建全部派生物 → `write=True` 时原子写 `.study/{kc.json, state.json, evidence.jsonl, errors.jsonl, cards.jsonl, questions.jsonl, sources.jsonl}` 并渲染 `.study/dashboard.md`。返回 `{"state", "kc", "misconceptions", "evidence", "cards", "questions", "sources"}`。**注意：本函数不加锁；调用方（CLI/rebuild）负责持有 `course_lock`。**
  - `derive.build_state(course, kc_states, miscs, due, events) -> dict`：§32 结构 + `counts`（七态计数）+ `due_cards`（数量）+ `active_misconceptions`（数量）+ `next_best_step` + `updated_at`。`current.phase` 由最后一个事件类型映射（attempt/registered→drill、repair_*/misconception→repair、fsrs_reviewed→review、其余→init）；`readiness.score` = Σ(exam_weight×状态分)/Σ(exam_weight)，状态分 {confirmed:1.0, checked:0.75, practiced:0.4, explained:0.25, weak:0.15, blocked:0.05, unseen:0.0}；level：<0.4 low，<0.7 medium，否则 high。
  - `derive.rebuild(root, *, dry_run: bool = False) -> dict`：从事件全量重算；dry_run 只返回差异摘要 `{"changed_kc_states": {kc: [old, new]}, "state_changed": bool}` 不落盘；非 dry_run 先追加 `state_rebuilt` 事件再重算落盘。
  - `dashboard.render(state: dict, kc_states: dict, miscs: dict, due: list) -> str`：Jinja2 渲染 `templates/dashboard.md.j2`（模板路径 = 本文件 `parents[2]/templates`）。风险列表：weak 且 calibration.gap≥0.3 → "「{name}」：高置信度盲区"；blocked → "「{name}」：前置未稳定"；到期卡 → "{n} 张卡片到期"；复发≥2 的活跃错因 → "错因复发：{error_type}（×{n}）"。

- [ ] **Step 1: 写失败测试**

`tests/test_derive.py`:
```python
import json


def _seed_minimal_flow(root):
    """kc + 真题 + 高置信度错误 + 归因，构成最小派生输入。"""
    from studylib.events import append_event, new_event
    cid = "analog-electronics"
    append_event(root, new_event(cid, "kc_created",
                                 {"kc_id": "feedback_topology", "name": "反馈组态判断",
                                  "chapter_id": "chapter_06", "exam_weight": 0.9}))
    append_event(root, new_event(cid, "question_registered",
                                 {"question_id": "past_2023_q17", "kc_ids": ["feedback_topology"],
                                  "source_type": "past_exam", "transfer_level": "T0",
                                  "stem": "判断反馈组态", "answer": "A"}))
    append_event(root, new_event(cid, "confidence_recorded",
                                 {"question_id": "past_2023_q17", "confidence_before": 0.9}))
    append_event(root, new_event(cid, "question_attempted",
                                 {"question_id": "past_2023_q17", "answer": "B", "correct": False,
                                  "confidence_before": 0.9, "hint_level": 0}))
    append_event(root, new_event(cid, "misconception_identified",
                                 {"error_id": "err_001", "kc_ids": ["feedback_topology"],
                                  "origin_question_id": "past_2023_q17",
                                  "wrong_assumption": "输出端有反馈连接即电压反馈",
                                  "missing_premise": "必须检查取样方式",
                                  "error_type": "concept_misconception",
                                  "trigger_conditions": ["复杂电路图"],
                                  "confidence_before": 0.9, "attribution_confidence": 0.82}))


def test_derive_writes_all_artifacts(course):
    from studylib.derive import derive
    _seed_minimal_flow(course)
    result = derive(course)
    study = course / ".study"
    for f in ["state.json", "kc.json", "evidence.jsonl", "errors.jsonl",
              "cards.jsonl", "questions.jsonl", "sources.jsonl", "dashboard.md"]:
        assert (study / f).exists(), f

    state = json.loads((study / "state.json").read_text(encoding="utf-8"))
    assert state["schema_version"] == "2.0"
    assert state["course"]["id"] == "analog-electronics"
    assert state["exam"]["date"] == "2026-07-25"
    assert state["counts"]["weak"] == 1
    assert state["active_misconceptions"] == 1
    nbs = state["next_best_step"]
    assert nbs["action"] == "repair"
    assert nbs["kc_id"] == "feedback_topology"
    assert nbs["reasons"]

    kc = json.loads((study / "kc.json").read_text(encoding="utf-8"))
    assert kc["feedback_topology"]["teaching_state"] == "weak"
    assert result["state"]["next_best_step"]["action"] == "repair"


def test_dashboard_contains_recommendation(course):
    from studylib.derive import derive
    _seed_minimal_flow(course)
    derive(course)
    text = (course / ".study" / "dashboard.md").read_text(encoding="utf-8")
    assert "今日建议" in text
    assert "反馈组态判断" in text
    assert "为什么" in text


def test_rebuild_dry_run_reports_no_diff_after_derive(course):
    from studylib.derive import derive, rebuild
    _seed_minimal_flow(course)
    derive(course)
    diff = rebuild(course, dry_run=True)
    assert diff["changed_kc_states"] == {}


def test_rebuild_writes_event_and_state(course):
    from studylib.derive import derive, rebuild
    from studylib.events import read_events
    _seed_minimal_flow(course)
    derive(course)
    rebuild(course)
    assert any(e["event_type"] == "state_rebuilt" for e in read_events(course))
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/test_derive.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

`templates/dashboard.md.j2`:
```jinja
# 今日建议

{% if s.next_best_step.action == "rest" -%}
暂无紧急任务。可以休息，或自由推进新章节。
{%- else -%}
**{{ s.next_best_step.action }}**：{{ s.next_best_step.kc_name or "到期复习" }}
预计：{{ s.next_best_step.estimated_minutes }} 分钟

为什么：
{% for r in s.next_best_step.reasons -%}
- {{ r }}
{% endfor -%}
{%- endif %}

# 考试

{% if s.exam.date -%}
日期：{{ s.exam.date }}（剩余 {{ s.exam.days_remaining }} 天）
{%- else -%}
未设置考试日期
{%- endif %}
准备度：{{ s.readiness.level }}（{{ "%.2f"|format(s.readiness.score) }}）

# 当前风险

{% if risks -%}
{% for r in risks -%}
{{ loop.index }}. {{ r }}
{% endfor -%}
{%- else -%}
暂无
{%- endif %}

# 掌握证据

- Confirmed: {{ s.counts.confirmed }} KC
- Checked: {{ s.counts.checked }} KC
- Weak: {{ s.counts.weak }} KC
- Blocked: {{ s.counts.blocked }} KC
- Practiced: {{ s.counts.practiced }} / Explained: {{ s.counts.explained }} / Unseen: {{ s.counts.unseen }}

# 到期复习

{{ s.due_cards }} 张卡片到期

_更新于 {{ s.updated_at }}_
```

`scripts/studylib/dashboard.py`:
```python
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
```

`scripts/studylib/derive.py`:
```python
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
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m pytest tests/test_derive.py -v`
Expected: 4 passed。随后跑全量：`python3 -m pytest`，全部通过。

- [ ] **Step 5: Commit**

```bash
git add scripts/studylib/derive.py scripts/studylib/dashboard.py templates/dashboard.md.j2 tests/test_derive.py
git commit -m "feat: derive orchestrator, state snapshot, dashboard, rebuild (spec §9/§32/§33)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 12: AI 出题质量闸门（validation 库）

**Files:**
- Create: `scripts/studylib/validation.py`
- Test: `tests/test_validation.py`

**Interfaces:**
- Consumes: `schemas.Question/ValidationBlock`, `registry.build_kcs`, `events.append_event/new_event/read_events`, `errors.ValidationFailed/InvalidSchema`
- Produces:
  - `validation.validate_candidate(kcs: dict[str, dict], cand: dict) -> list[str]`：返回问题列表（空 = 通过）。检查（§43）：Question schema 合法；所有 kc_ids 已注册；answer 非空；`source_type=="synthetic"` 时——`derived_from` 非空、`validation` 块存在、`generator.status=="passed"`、`independent_solver.status=="passed"` 且 `answer_match is True`、`adversarial_review.status=="passed"`、`mechanical_validator`（若存在）`status=="passed"`；`transfer_level ∈ {T2,T3,T4}` 时 `set(changed_dimensions) - {"surface_context"}` 非空（简单换数字不能冒充结构迁移）。
  - `validation.register_question(root: Path, cand: dict, *, as_transfer_test: bool = False, session_id: str = "session_adhoc") -> dict`：校验（从 root 读事件构建 kcs），有问题 → `ValidationFailed`（消息含全部问题，一行一个）；通过 → 追加 `transfer_test_created`（as_transfer_test=True）或 `question_registered` 事件，payload = `{**cand, **Question(**cand).model_dump()}`（规范化字段覆盖、额外键保留），返回该事件。**不派生、不加锁**——调用方负责。

- [ ] **Step 1: 写失败测试**

`tests/test_validation.py`:
```python
import pytest

KCS = {"feedback_topology": {"kc_id": "feedback_topology", "name": "反馈组态判断",
                             "prerequisites": [], "exam_weight": 0.9,
                             "chapter_id": None, "source_ids": [], "explained": False}}

PASSED = {"generator": {"status": "passed"},
          "independent_solver": {"status": "passed", "answer_match": True},
          "adversarial_review": {"status": "passed", "issues": []},
          "mechanical_validator": {"type": "sympy", "status": "passed"}}


def _syn(**over):
    q = {"question_id": "syn_q_018", "kc_ids": ["feedback_topology"],
         "source_type": "synthetic", "transfer_level": "T2",
         "stem": "反向推断反馈类型", "answer": "B",
         "changed_dimensions": ["question_direction", "information_structure"],
         "preserved_dimensions": ["core_kc", "target_capability", "cognitive_trap"],
         "derived_from": ["kc:feedback_topology", "error:err_001", "question:past_2023_q17"],
         "validation": dict(PASSED)}
    q.update(over)
    return q


def test_real_question_needs_no_validation_block():
    from studylib.validation import validate_candidate
    q = {"question_id": "past_2023_q17", "kc_ids": ["feedback_topology"],
         "source_type": "past_exam", "transfer_level": "T0",
         "stem": "判断反馈组态", "answer": "A"}
    assert validate_candidate(KCS, q) == []


def test_synthetic_requires_gates():
    from studylib.validation import validate_candidate
    assert validate_candidate(KCS, _syn(validation=None))
    bad_solver = dict(PASSED, independent_solver={"status": "passed", "answer_match": False})
    issues = validate_candidate(KCS, _syn(validation=bad_solver))
    assert any("solver" in i.lower() or "答案" in i for i in issues)


def test_number_swap_cannot_claim_t2():
    from studylib.validation import validate_candidate
    issues = validate_candidate(KCS, _syn(changed_dimensions=["surface_context"]))
    assert any("surface_context" in i or "换数字" in i for i in issues)


def test_unknown_kc_rejected():
    from studylib.validation import validate_candidate
    issues = validate_candidate(KCS, _syn(kc_ids=["ghost_kc"]))
    assert any("ghost_kc" in i for i in issues)


def test_register_question_appends_correct_event(course):
    from studylib.errors import ValidationFailed
    from studylib.events import append_event, new_event, read_events
    from studylib.validation import register_question
    append_event(course, new_event("analog-electronics", "kc_created",
                                   {"kc_id": "feedback_topology", "name": "反馈组态判断"}))
    ev = register_question(course, _syn(), as_transfer_test=True)
    assert ev["event_type"] == "transfer_test_created"
    assert read_events(course)[-1]["payload"]["question_id"] == "syn_q_018"
    with pytest.raises(ValidationFailed):
        register_question(course, _syn(validation=None))
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/test_validation.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

`scripts/studylib/validation.py`:
```python
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
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m pytest tests/test_validation.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/studylib/validation.py tests/test_validation.py
git commit -m "feat: AI question quality gates (spec §16/§43)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 13: CLI 脚本层（spec 命名的薄壳）

**Files:**
- Create: `scripts/studylib/cli_common.py`, `scripts/init_course.py`, `scripts/event.py`, `scripts/derive_state.py`, `scripts/fsrs.py`, `scripts/next_step.py`, `scripts/validate_question.py`, `scripts/render_dashboard.py`, `scripts/rebuild.py`, `scripts/misconception.py`, `scripts/evidence.py`
- Test: `tests/test_cli_smoke.py`

**Interfaces:**
- Consumes: 全部 studylib 模块
- Produces（命令面，主 Agent 在 SKILL.md 中引用的就是这些）：
  - `python3 scripts/init_course.py PATH --course-id ID --name NAME [--exam-date YYYY-MM-DD]`
  - `python3 scripts/event.py kc-add --kc-id K --name N [--chapter CH] [--prereq P ...] [--exam-weight W] [--course PATH]`
  - `python3 scripts/event.py kc-explained --kc-id K`
  - `python3 scripts/event.py source-add --source-id S --source-type T --file F [--section SEC]`
  - `python3 scripts/event.py attempt --question-id Q (--correct|--wrong) [--confidence 0.9] [--hint-level 0] [--time-sec 78] [--retest-of ERR] [--transfer] [--session S]`
  - `python3 scripts/event.py hint --question-id Q --level 2`
  - `python3 scripts/event.py misconception --error-id E --kc K --question Q --wrong-assumption WA --missing-premise MP --error-type ET [--trigger COND ...] [--confidence-before 0.9] [--attribution-confidence 0.8]`
  - `python3 scripts/event.py repair-start --error-id E --repair-id R` / `repair-step --error-id E [--note TXT]` / `repair-done --error-id E`
  - `python3 scripts/derive_state.py [--course PATH]`
  - `python3 scripts/fsrs.py create-card --card-type T --kc K [--question-id Q]` / `review --card-id C --rating 1..4` / `due`
  - `python3 scripts/next_step.py [--course PATH]`
  - `python3 scripts/validate_question.py CANDIDATE.json [--as-transfer-test] [--course PATH]`
  - `python3 scripts/render_dashboard.py [--course PATH]`
  - `python3 scripts/rebuild.py [--course PATH] [--dry-run]`
  - `python3 scripts/misconception.py list [--course PATH]`（活跃错因表）
  - `python3 scripts/evidence.py list --kc K [--course PATH]`
  - `cli_common.commit_events(root, events) -> state dict`（加锁 → 逐个 append → derive → 返回 state）；`cli_common.echo_next(state)`；`cli_common.guard(fn)` 装饰器（StudyLoopError → 人话 + exit 1）；`cli_common.resolve_root(path) -> Path`。

- [ ] **Step 1: 写失败测试（子进程冒烟）**

`tests/test_cli_smoke.py`:
```python
import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def run(args, cwd, env_home):
    import os
    env = dict(os.environ, STUDY_LOOP_HOME=str(env_home))
    return subprocess.run([sys.executable, *args], cwd=cwd, env=env,
                          capture_output=True, text=True)


def test_cli_full_smoke(tmp_path):
    home = tmp_path / "home"
    course_dir = tmp_path / "模电"

    r = run([SCRIPTS / "init_course.py", str(course_dir), "--course-id", "analog",
             "--name", "模拟电子技术", "--exam-date", "2026-07-25"], tmp_path, home)
    assert r.returncode == 0, r.stderr

    r = run([SCRIPTS / "event.py", "kc-add", "--kc-id", "feedback_topology",
             "--name", "反馈组态判断", "--exam-weight", "0.9"], course_dir, home)
    assert r.returncode == 0, r.stderr

    cand = course_dir / "q.json"
    cand.write_text(json.dumps({
        "question_id": "past_2023_q17", "kc_ids": ["feedback_topology"],
        "source_type": "past_exam", "transfer_level": "T0",
        "stem": "判断反馈组态", "answer": "A",
    }, ensure_ascii=False), encoding="utf-8")
    r = run([SCRIPTS / "validate_question.py", str(cand)], course_dir, home)
    assert r.returncode == 0, r.stderr

    r = run([SCRIPTS / "event.py", "attempt", "--question-id", "past_2023_q17",
             "--wrong", "--confidence", "0.9"], course_dir, home)
    assert r.returncode == 0, r.stderr
    assert "repair" in r.stdout or "下一步" in r.stdout

    r = run([SCRIPTS / "event.py", "misconception", "--error-id", "err_001",
             "--kc", "feedback_topology", "--question", "past_2023_q17",
             "--wrong-assumption", "有反馈连接即电压反馈",
             "--missing-premise", "必须检查取样方式",
             "--error-type", "concept_misconception"], course_dir, home)
    assert r.returncode == 0, r.stderr

    state = json.loads((course_dir / ".study" / "state.json").read_text(encoding="utf-8"))
    assert state["next_best_step"]["action"] == "repair"
    assert state["counts"]["weak"] == 1

    r = run([SCRIPTS / "fsrs.py", "create-card", "--card-type", "original_question",
             "--kc", "feedback_topology", "--question-id", "past_2023_q17"], course_dir, home)
    assert r.returncode == 0, r.stderr
    r = run([SCRIPTS / "fsrs.py", "due"], course_dir, home)
    assert r.returncode == 0 and "card_" in r.stdout

    r = run([SCRIPTS / "rebuild.py", "--dry-run"], course_dir, home)
    assert r.returncode == 0, r.stderr

    r = run([SCRIPTS / "next_step.py"], course_dir, home)
    assert r.returncode == 0 and "repair" in r.stdout


def test_cli_friendly_error_outside_course(tmp_path):
    r = run([SCRIPTS / "next_step.py"], tmp_path, tmp_path / "home")
    assert r.returncode == 1
    assert "course.yaml" in r.stderr + r.stdout
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/test_cli_smoke.py -v`
Expected: FAIL（脚本不存在）

- [ ] **Step 3: 实现**

`scripts/studylib/cli_common.py`:
```python
from __future__ import annotations

import functools
from pathlib import Path

import typer

from . import derive as derive_mod
from .errors import StudyLoopError
from .events import append_event
from .ioutils import course_lock
from .paths import find_course_root


def resolve_root(path: Path | None) -> Path:
    return find_course_root(path)


def commit_events(root: Path, events: list[dict]) -> dict:
    with course_lock(root):
        for ev in events:
            append_event(root, ev)
        result = derive_mod.derive(root)
    return result["state"]


def echo_next(state: dict) -> None:
    nbs = state["next_best_step"]
    if nbs["action"] == "rest":
        typer.echo(f"下一步建议：rest —— {nbs['reasons'][0]}")
        return
    target = nbs.get("kc_name") or "到期复习"
    typer.echo(f"下一步建议：{nbs['action']}「{target}」（约 {nbs['estimated_minutes']} 分钟）")
    typer.echo("原因：")
    for r in nbs["reasons"]:
        typer.echo(f"  - {r}")


def guard(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except StudyLoopError as e:
            typer.echo(f"错误：{e}", err=True)
            raise typer.Exit(code=1)
    return wrapper
```

每个脚本头部统一三行 bootstrap（下略注释）。`scripts/init_course.py`:
```python
#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typer

from studylib import derive as derive_mod
from studylib.cli_common import guard
from studylib.course import init_course
from studylib.ioutils import course_lock

app = typer.Typer(add_completion=False)


@app.command()
@guard
def main(
    path: Path = typer.Argument(..., help="课程工作区目录"),
    course_id: str = typer.Option(..., "--course-id"),
    name: str = typer.Option(..., "--name"),
    exam_date: str = typer.Option(None, "--exam-date", help="YYYY-MM-DD"),
):
    root = init_course(path, course_id, name, exam_date)
    with course_lock(root):
        derive_mod.derive(root)
    typer.echo(f"课程工作区已创建：{root}")


if __name__ == "__main__":
    app()
```

`scripts/event.py`:
```python
#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typer

from studylib.cli_common import commit_events, echo_next, guard, resolve_root
from studylib.course import load_course
from studylib.events import new_event
from studylib.schemas import ERROR_TYPES

app = typer.Typer(add_completion=False)


def _ctx(course: Path | None):
    root = resolve_root(course)
    return root, load_course(root)["id"]


@app.command("kc-add")
@guard
def kc_add(
    kc_id: str = typer.Option(..., "--kc-id"),
    name: str = typer.Option(..., "--name"),
    chapter: str = typer.Option(None, "--chapter"),
    prereq: list[str] = typer.Option([], "--prereq"),
    exam_weight: float = typer.Option(0.5, "--exam-weight"),
    source_id: list[str] = typer.Option([], "--source-id"),
    course: Path = typer.Option(None, "--course"),
):
    root, cid = _ctx(course)
    state = commit_events(root, [new_event(cid, "kc_created", {
        "kc_id": kc_id, "name": name, "chapter_id": chapter,
        "prerequisites": list(prereq), "exam_weight": exam_weight,
        "source_ids": list(source_id)})])
    typer.echo(f"KC 已注册：{kc_id}")
    echo_next(state)


@app.command("kc-explained")
@guard
def kc_explained(
    kc_id: str = typer.Option(..., "--kc-id"),
    course: Path = typer.Option(None, "--course"),
):
    root, cid = _ctx(course)
    state = commit_events(root, [new_event(cid, "kc_updated", {"kc_id": kc_id, "update": "explained"})])
    echo_next(state)


@app.command("source-add")
@guard
def source_add(
    source_id: str = typer.Option(..., "--source-id"),
    source_type: str = typer.Option(..., "--source-type"),
    file: str = typer.Option(..., "--file"),
    section: str = typer.Option(None, "--section"),
    course: Path = typer.Option(None, "--course"),
):
    root, cid = _ctx(course)
    commit_events(root, [new_event(cid, "source_registered", {
        "source_id": source_id, "source_type": source_type, "file": file, "section": section})])
    typer.echo(f"来源已登记：{source_id}")


@app.command()
@guard
def attempt(
    question_id: str = typer.Option(..., "--question-id"),
    correct: bool = typer.Option(..., "--correct/--wrong"),
    confidence: float = typer.Option(None, "--confidence", min=0.0, max=1.0),
    hint_level: int = typer.Option(0, "--hint-level", min=0, max=5),
    time_sec: int = typer.Option(None, "--time-sec"),
    retest_of: str = typer.Option(None, "--retest-of"),
    transfer: bool = typer.Option(False, "--transfer", help="记为 transfer_test_attempted"),
    session: str = typer.Option("session_adhoc", "--session"),
    course: Path = typer.Option(None, "--course"),
):
    root, cid = _ctx(course)
    events = []
    if confidence is not None:
        events.append(new_event(cid, "confidence_recorded",
                                {"question_id": question_id, "confidence_before": confidence},
                                session_id=session))
    payload = {"question_id": question_id, "correct": correct, "hint_level": hint_level}
    if confidence is not None:
        payload["confidence_before"] = confidence
    if time_sec is not None:
        payload["response_time_sec"] = time_sec
    if retest_of:
        payload["retest_of_error_id"] = retest_of
    etype = "transfer_test_attempted" if transfer else "question_attempted"
    events.append(new_event(cid, etype, payload, session_id=session))
    state = commit_events(root, events)
    typer.echo("已记录：" + ("答对" if correct else "答错"))
    echo_next(state)


@app.command()
@guard
def hint(
    question_id: str = typer.Option(..., "--question-id"),
    level: int = typer.Option(..., "--level", min=1, max=5),
    course: Path = typer.Option(None, "--course"),
):
    root, cid = _ctx(course)
    commit_events(root, [new_event(cid, "hint_requested", {"question_id": question_id, "level": level})])
    typer.echo(f"已记录 L{level} 提示")


@app.command()
@guard
def misconception(
    error_id: str = typer.Option(None, "--error-id"),
    kc: list[str] = typer.Option(..., "--kc"),
    question: str = typer.Option(None, "--question"),
    wrong_assumption: str = typer.Option(..., "--wrong-assumption"),
    missing_premise: str = typer.Option(..., "--missing-premise"),
    error_type: str = typer.Option(..., "--error-type"),
    trigger: list[str] = typer.Option([], "--trigger"),
    confidence_before: float = typer.Option(None, "--confidence-before"),
    attribution_confidence: float = typer.Option(None, "--attribution-confidence"),
    course: Path = typer.Option(None, "--course"),
):
    if error_type not in ERROR_TYPES:
        typer.echo(f"错误：未知错因类型 {error_type}（可选：{sorted(ERROR_TYPES)}）", err=True)
        raise typer.Exit(code=1)
    root, cid = _ctx(course)
    payload = {"kc_ids": list(kc), "origin_question_id": question,
               "wrong_assumption": wrong_assumption, "missing_premise": missing_premise,
               "error_type": error_type, "trigger_conditions": list(trigger),
               "confidence_before": confidence_before,
               "attribution_confidence": attribution_confidence}
    if error_id:
        payload["error_id"] = error_id
    state = commit_events(root, [new_event(cid, "misconception_identified", payload)])
    typer.echo("错因已入库（Misconception Memory）")
    echo_next(state)


@app.command("repair-start")
@guard
def repair_start(
    error_id: str = typer.Option(..., "--error-id"),
    repair_id: str = typer.Option(..., "--repair-id"),
    course: Path = typer.Option(None, "--course"),
):
    root, cid = _ctx(course)
    commit_events(root, [new_event(cid, "repair_started", {"error_id": error_id, "repair_id": repair_id})])
    typer.echo(f"修复开始：{repair_id}")


@app.command("repair-step")
@guard
def repair_step(
    error_id: str = typer.Option(..., "--error-id"),
    note: str = typer.Option(None, "--note"),
    course: Path = typer.Option(None, "--course"),
):
    root, cid = _ctx(course)
    commit_events(root, [new_event(cid, "repair_step_completed", {"error_id": error_id, "note": note})])


@app.command("repair-done")
@guard
def repair_done(
    error_id: str = typer.Option(..., "--error-id"),
    course: Path = typer.Option(None, "--course"),
):
    root, cid = _ctx(course)
    state = commit_events(root, [new_event(cid, "repair_completed", {"error_id": error_id})])
    typer.echo("修复完成，进入重测（原题二刷 + 迁移验证）")
    echo_next(state)


if __name__ == "__main__":
    app()
```

`scripts/derive_state.py`:
```python
#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typer

from studylib import derive as derive_mod
from studylib.cli_common import echo_next, guard, resolve_root
from studylib.ioutils import course_lock

app = typer.Typer(add_completion=False)


@app.command()
@guard
def main(course: Path = typer.Option(None, "--course")):
    root = resolve_root(course)
    with course_lock(root):
        result = derive_mod.derive(root)
    typer.echo(f"状态已派生：{root / '.study'}")
    echo_next(result["state"])


if __name__ == "__main__":
    app()
```

`scripts/fsrs.py`:
```python
#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typer

from studylib.cli_common import commit_events, echo_next, guard, resolve_root
from studylib.course import load_course
from studylib.events import new_event, read_events
from studylib.fsrs_store import due_cards, new_card_payload, replay_cards
from studylib.ioutils import now_iso

app = typer.Typer(add_completion=False)


@app.command("create-card")
@guard
def create_card(
    card_type: str = typer.Option(..., "--card-type"),
    kc: list[str] = typer.Option(..., "--kc"),
    question_id: str = typer.Option(None, "--question-id"),
    course: Path = typer.Option(None, "--course"),
):
    root = resolve_root(course)
    cid = load_course(root)["id"]
    payload = new_card_payload(card_type, list(kc), question_id)
    commit_events(root, [new_event(cid, "fsrs_card_created", payload)])
    typer.echo(f"卡片已创建：{payload['card_id']}")


@app.command()
@guard
def review(
    card_id: str = typer.Option(..., "--card-id"),
    rating: int = typer.Option(..., "--rating", min=1, max=4),
    course: Path = typer.Option(None, "--course"),
):
    root = resolve_root(course)
    cid = load_course(root)["id"]
    state = commit_events(root, [new_event(cid, "fsrs_reviewed", {
        "card_id": card_id, "rating": rating, "review_time": now_iso()})])
    typer.echo("复习已记录")
    echo_next(state)


@app.command()
@guard
def due(course: Path = typer.Option(None, "--course")):
    root = resolve_root(course)
    cards = replay_cards(read_events(root))
    rows = due_cards(cards)
    if not rows:
        typer.echo("没有到期卡片")
        return
    for c in rows:
        typer.echo(f"{c['card_id']}  {c['card_type']}  kc={','.join(c['kc_ids'])}  due={c['due']}")


if __name__ == "__main__":
    app()
```

`scripts/next_step.py`:
```python
#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typer

from studylib import derive as derive_mod
from studylib.cli_common import echo_next, guard, resolve_root
from studylib.ioutils import course_lock

app = typer.Typer(add_completion=False)


@app.command()
@guard
def main(course: Path = typer.Option(None, "--course")):
    root = resolve_root(course)
    with course_lock(root):
        result = derive_mod.derive(root)
    echo_next(result["state"])


if __name__ == "__main__":
    app()
```

`scripts/validate_question.py`:
```python
#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typer

from studylib import derive as derive_mod
from studylib.cli_common import guard, resolve_root
from studylib.ioutils import course_lock
from studylib.validation import register_question

app = typer.Typer(add_completion=False)


@app.command()
@guard
def main(
    candidate: Path = typer.Argument(..., help="候选题 JSON 文件"),
    as_transfer_test: bool = typer.Option(False, "--as-transfer-test"),
    course: Path = typer.Option(None, "--course"),
):
    root = resolve_root(course)
    cand = json.loads(candidate.read_text(encoding="utf-8"))
    with course_lock(root):
        ev = register_question(root, cand, as_transfer_test=as_transfer_test)
        derive_mod.derive(root)
    typer.echo(f"题目已通过闸门并注册：{ev['payload']['question_id']}（{ev['event_type']}）")


if __name__ == "__main__":
    app()
```

`scripts/render_dashboard.py`:
```python
#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typer

from studylib import derive as derive_mod
from studylib.cli_common import guard, resolve_root
from studylib.ioutils import course_lock

app = typer.Typer(add_completion=False)


@app.command()
@guard
def main(course: Path = typer.Option(None, "--course")):
    root = resolve_root(course)
    with course_lock(root):
        derive_mod.derive(root)
    typer.echo((root / ".study" / "dashboard.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    app()
```

`scripts/rebuild.py`:
```python
#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typer

from studylib.cli_common import guard, resolve_root
from studylib.derive import rebuild as rebuild_fn
from studylib.ioutils import course_lock

app = typer.Typer(add_completion=False)


@app.command()
@guard
def main(
    course: Path = typer.Option(None, "--course"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    root = resolve_root(course)
    with course_lock(root):
        summary = rebuild_fn(root, dry_run=dry_run)
    typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
```

`scripts/misconception.py`:
```python
#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typer

from studylib.cli_common import guard, resolve_root
from studylib.ioutils import read_jsonl

app = typer.Typer(add_completion=False)


@app.command("list")
@guard
def list_cmd(course: Path = typer.Option(None, "--course")):
    root = resolve_root(course)
    rows = read_jsonl(root / ".study" / "errors.jsonl")
    active = [m for m in rows if m.get("repair_status") != "resolved"]
    if not active:
        typer.echo("没有活跃错因")
        return
    for m in active:
        typer.echo(f"{m['error_id']}  [{m['repair_status']}]  {m['error_type']}  "
                   f"kc={','.join(m['kc_ids'])}  ×{m.get('recurrence_count', 1)}")
        typer.echo(f"    错误假设：{m.get('wrong_assumption', '')}")


if __name__ == "__main__":
    app()
```

`scripts/evidence.py`:
```python
#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typer

from studylib.cli_common import guard, resolve_root
from studylib.ioutils import read_jsonl

app = typer.Typer(add_completion=False)


@app.command("list")
@guard
def list_cmd(
    kc: str = typer.Option(..., "--kc"),
    course: Path = typer.Option(None, "--course"),
):
    root = resolve_root(course)
    rows = [r for r in read_jsonl(root / ".study" / "evidence.jsonl") if kc in r["kc_ids"]]
    if not rows:
        typer.echo(f"KC {kc} 暂无证据")
        return
    for r in rows:
        mark = "✓" if r["result"]["correct"] else "✗"
        conf = r.get("confidence_before")
        typer.echo(f"{mark} {r['created_at']}  {r['question_id']}  {r['transfer_level']}  "
                   f"hint=L{r['hint_level']}  conf={conf if conf is not None else '-'}")


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m pytest tests/test_cli_smoke.py -v`
Expected: 2 passed。随后全量 `python3 -m pytest`，全部通过。

- [ ] **Step 5: Commit**

```bash
git add scripts/ tests/test_cli_smoke.py
git commit -m "feat: thin Typer CLI layer over studylib (spec §5/§6.1)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 14: SKILL.md、references、agents 卡片与 README

**Files:**
- Create: `SKILL.md`, `references/architecture.md`, `references/evidence-graph.md`, `references/misconception-memory.md`, `references/hint-ladder.md`, `references/transfer-ladder.md`, `references/question-validation.md`, `references/provenance.md`, `references/fsrs-policy.md`, `references/next-best-step.md`, `agents/question-generator.md`, `agents/independent-solver.md`, `agents/adversarial-reviewer.md`, `README.md`
- Test: `tests/test_docs.py`

**Interfaces:**
- Produces: 主 Agent 的行为契约。SKILL.md 必须轻（只做路由），完整规则在 references/（spec §34）。

- [ ] **Step 1: 写失败测试**

`tests/test_docs.py`:
```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REFERENCES = [
    "architecture.md", "evidence-graph.md", "misconception-memory.md",
    "hint-ladder.md", "transfer-ladder.md", "question-validation.md",
    "provenance.md", "fsrs-policy.md", "next-best-step.md",
]
AGENTS = ["question-generator.md", "independent-solver.md", "adversarial-reviewer.md"]
SCRIPTS = [
    "init_course.py", "event.py", "derive_state.py", "fsrs.py", "next_step.py",
    "validate_question.py", "render_dashboard.py", "rebuild.py",
    "misconception.py", "evidence.py",
]


def test_skill_md_frontmatter_and_routing():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---")
    fm = text.split("---")[1]
    assert "name: study-loop" in fm
    assert "description:" in fm
    for s in SCRIPTS:
        assert s in text, f"SKILL.md 必须引用脚本 {s}"
    for r in REFERENCES:
        assert r in text, f"SKILL.md 必须引用 references/{r}"


def test_reference_and_agent_files_exist_nonempty():
    for r in REFERENCES:
        p = ROOT / "references" / r
        assert p.exists() and len(p.read_text(encoding="utf-8")) > 200, r
    for a in AGENTS:
        p = ROOT / "agents" / a
        assert p.exists() and len(p.read_text(encoding="utf-8")) > 200, a


def test_readme_has_quickstart():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "init_course.py" in text and "Quick" in text or "快速" in text
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/test_docs.py -v`
Expected: FAIL（文件不存在）

- [ ] **Step 3: 写文档**

`SKILL.md`（完整内容）:
```markdown
---
name: study-loop
description: 面向大学课程的本地优先持续学习 Agent。当用户说 /study、要求复习/刷题/修复错题/诊断掌握情况/准备考试，或提到 study-loop 时使用。基于事件日志与学习证据做教学决策，不以"听懂"为掌握证据。
---

# study-loop 主 Agent 路由

你是 study-loop 的主 Agent：负责决策与解释，执行交给脚本与子流程。核心原则见 references/architecture.md。

## 铁律

1. 你只通过 `scripts/` 下的 CLI 写事件，绝不直接编辑 `.study/` 下任何 JSON/JSONL。
2. 每次记录事件后 CLI 会自动重算状态并打印 next-best-step——把它解释给学生，不要扔菜单。
3. 听懂≠掌握：升级 checked/confirmed 的规则由脚本执行，你不得口头宣布掌握。
4. AI 生成题必须走 agents/ 三卡流程 + `validate_question.py` 闸门，通过才存在。
5. 原题（真题/课后题）优先于 AI 生成题，且必须进 FSRS。

## 会话开场（/study 默认行为）

1. `python3 scripts/next_step.py`（自动识别当前目录课程、重算状态）。
2. 把推荐和原因用一两句话讲给学生，直接开始；意图不明时只问一次。
3. 学生明确说了要做什么 → 直接路由到对应流程。

## 路由表

| 学生意图 | 你要做的事 | 参考 |
|---|---|---|
| 新课程 | `python3 scripts/init_course.py <目录> --course-id .. --name .. --exam-date ..`，然后逐个 `event.py kc-add` 注册骨架（考纲优先），`event.py source-add` 登记来源 | references/provenance.md |
| 讲解教学 | 当帧教学；讲完 `event.py kc-explained --kc-id ..` | references/evidence-graph.md |
| 做题/刷题 | 出示题目 → 先问置信度（猜的/不太确定/比较确定/非常确定 → 0.25/0.5/0.75/1.0）→ 学生作答 → `event.py attempt --question-id .. --correct|--wrong --confidence .. [--hint-level ..] [--transfer] [--retest-of ..]` | references/hint-ladder.md |
| 学生答错 | 三步归因（错误假设/缺失前提/错因类型）→ `event.py misconception ...` → 按错因选修复策略 → `event.py repair-start/repair-done` → 双轨重测（原题二刷 + 迁移题） | references/misconception-memory.md |
| 生成迁移题 | 按 agents/question-generator.md 出题 → agents/independent-solver.md 盲解 → agents/adversarial-reviewer.md 审查 → 组装 validation 块 → `validate_question.py cand.json --as-transfer-test` | references/transfer-ladder.md, references/question-validation.md |
| 复习到期卡 | `fsrs.py due` → 逐卡提问 → `fsrs.py review --card-id .. --rating 1..4`（评分策略见 references/fsrs-policy.md） | references/fsrs-policy.md |
| 看状态 | `python3 scripts/render_dashboard.py`；错因表 `misconception.py list`；单点证据 `evidence.py list --kc ..` | references/next-best-step.md |
| 状态可疑/升级后 | 先 `python3 scripts/derive_state.py` 重算；仍可疑再 `python3 scripts/rebuild.py --dry-run` 看差异，确认后去掉 --dry-run | references/architecture.md |

## 何时派 Subagent

批量出题+验证、KC DAG 批量注册、全量重建审计等无交互重任务派 Subagent（给它对应 agents/*.md 卡片和本文件的铁律）；教学、诊断问答、Socratic 修复、逐题批改留在主会话。

## 数据位置

课程工作区 = 含 `course.yaml` 的目录；状态在 `.study/`（dashboard.md 可直接给学生看）；全局注册表在 `~/.study-loop/registry.json`。
```

`references/architecture.md`:
```markdown
# 架构与不变量

## 真相层级
events.jsonl（append-only 历史事实）→ 派生状态（state.json / kc.json / errors.jsonl / cards.jsonl / questions.jsonl / sources.jsonl）→ dashboard.md（只读展示）。

任何学习行为：先写事件，再由 derive 重算派生状态。禁止直接把 kc.json 的某个状态改成想要的值——那不是记录，是伪造证据。

## 为什么事件优先
- 规则可以升级：`rebuild.py` 用新规则从全部历史重算，不依赖旧快照。
- 可审计：每个 KC 状态都能回答"凭什么"（evidence_ids → source_event_id → 事件）。
- 崩溃安全：JSONL 追加 + 原子快照写入 + 课程锁。

## 分工
- 主 Agent：读状态、判意图、解释推荐、执行教学对话。
- 脚本（scripts/）：事件写入、状态派生、FSRS 调度、质量闸门——一切需要确定性的东西。
- Subagent：批量出题、批量验证、批量注册等无交互重任务。

## 六态 + FSRS + 迁移的关系
- 六态（teaching_state）回答"下一步该教什么"。
- FSRS 只回答"什么时候复习"，不代表理解（fsrs-policy.md）。
- 迁移阶梯回答"是否真的理解"（transfer-ladder.md）。
三者独立建模，都存在 kc.json 里。

## 可调阈值
六态判定阈值集中在 `scripts/studylib/state_rules.py` 的 `DeriveConfig`：
independent_hint_max=1, weak_success_floor=0.5, retention_min_days=1.0,
high_conf_threshold=0.75, transfer_window=3。改动后跑 `rebuild.py --dry-run` 预览影响。
```

`references/evidence-graph.md`:
```markdown
# 学习证据图谱与六态规则

每个 KC 不是一个 mastery 分数，而是四组独立证据：
- teaching_state（六态）
- retention（FSRS retrievability / 到期卡）
- transfer（T0~T4 各层最近正确率）
- calibration（自评 vs 实际，blind_spot = 自评 × (1−实际)）
- assistance（提示依赖、独立正确率）

## 六态派生规则（V1，由 state_rules.py 执行）
- unseen：无任何学习事件。
- explained：讲过（kc-explained），但没有作答证据。
- practiced：有作答，但没有"独立正确"（正确且 hint_level ≤ 1）。**L4/L5 帮助下答对只能是 practiced。**
- checked：至少一次独立正确，且最近一次作答是对的。
- confirmed：checked + 两次独立正确间隔 ≥ 1 天（保持）+ 最近一次 T1 或 T2 迁移通过 + 无高置信度活跃错因。
- weak：最近一次答错，或存在高置信度（≥0.75）活跃错因，或 ≥2 次作答且正确率 <0.5，或任一 T1+ 层最近一次失败。
- blocked：某个前置 KC 处于 weak/blocked，且本 KC 尚无独立正确。

## 升级禁令（§14.1）
学生说"懂了"、看完答案复述、L4/L5 帮助下完成、只会做原题——都不构成 checked/confirmed。规则由脚本执行，Agent 不得越权宣布。

## 置信度四象限
对+高置信 = 真掌握候选；对+低置信 = 认知不稳定；错+低置信 = 普通漏洞；**错+高置信 = 高价值稳定误区，优先修复**。
作答前必须收集置信度：猜的 0.25 / 不太确定 0.5 / 比较确定 0.75 / 非常确定 1.0。
```

`references/misconception-memory.md`:
```markdown
# Misconception Memory（错因长期记忆）

errors.jsonl 的建模单位是 KC × 错因 × 触发条件，不是题目 × 对错。同一 KC 同一错因再次出现 → recurrence_count 累加、触发条件并集。

## 三步归因（每个高价值错误必做）
1. 错误假设是什么？（学生当时依据的错误规则）
2. 缺失了哪个前提？（正确做法需要但学生没用上的条件）
3. 属于哪种误解类型？（下方 14 类之一；禁止大量归为 careless_error）

concept_misconception / prerequisite_gap / condition_misread / procedure_omission /
formula_misuse / representation_failure / transfer_failure / similar_concept_confusion /
calculation_slip / memory_failure / strategy_failure / time_pressure_failure /
careless_error / unknown

## 错因 → 修复策略（§24.3）
| 错因 | 默认策略 |
|---|---|
| concept_misconception | Socratic 追问（引导学生自己发现矛盾） |
| prerequisite_gap | 回退前置 KC 再回来 |
| procedure_omission | 直接指出遗漏步骤 |
| condition_misread | 条件对比训练 |
| similar_concept_confusion | 辨析矩阵（并排对比两个概念的适用条件） |
| formula_misuse | 公式适用边界检查 |
| representation_failure | 换表征（图↔式↔文字） |
| transfer_failure | 沿迁移阶梯降级重建 |
| calculation_slip | 最小纠正，不小题大做 |
| memory_failure | 交给 FSRS |
| 高置信度错误 | 无论何种类型，优先深修 |

## 修复生命周期
active →（repair-start）repairing →（repair-done）retest_pending →（原题二刷通过 且 T1/T2 任一通过）resolved。
重测任何一次失败 → 打回 active。双轨重测缺一不可：原题二刷验证"这道题会了"，迁移题验证"这个知识点会了"。
```

`references/hint-ladder.md`:
```markdown
# Hint Ladder（提示阶梯）

L0 独立作答（不给任何提示）
L1 元认知追问——"你刚才的判断依据是什么？"
L2 方向提示——"先判断这里取样的是哪个输出物理量。"
L3 局部脚手架——"暂时忽略 R3，只看输出端和反馈网络的连接。"
L4 半步演示——AI 做关键一步，学生继续。
L5 完整讲解——完整思路与答案。

## 使用规则
- 永远从 L0 开始；学生卡住时一次只升一级。
- 每次给提示：`event.py hint --question-id .. --level N`，最终作答时把最高级别写进 `attempt --hint-level N`。
- hint_level ≤ 1 的正确才算"独立正确"（可支撑 checked）。
- L4/L5 帮助下答对：记录照常，但状态最多 practiced，之后必须安排 L0 独立重测。
- 学生要答案时先确认是否愿意再试一级更低的提示；学生坚持 → 给 L5，如实记录。
```

`references/transfer-ladder.md`:
```markdown
# Transfer Ladder（迁移阶梯）

T0 原题复现：完全相同的题。历年真题/课后原题/教师重点题优先保留，必须允许进 FSRS。
T1 近迁移：同 KC 同结构，只换数值/对象/表述/简单背景。**只换数字只能算 T1。**
T2 结构迁移：至少改变一项——信息结构 / 已知条件 / 设问方向 / 推理顺序 / 表征方式（正向→反向、完整图→局部描述、公式→图形、显式→隐含条件）。
T3 辨析迁移：加入相邻 KC、易混概念、干扰条件、冗余信息或原错误触发条件——检查学生知道"何时用哪个知识"。
T4 远迁移：陌生情境，题目不提示目标 KC，学生须自行识别。

## 生成迁移题的 Schema 要求
每道生成题必须声明 transfer_level、changed_dimensions（⊆ surface_context / information_structure / question_direction / condition_combination / reasoning_order / representation / distractor_mechanism / required_identification）、preserved_dimensions（core_kc / target_capability / cognitive_trap）、derived_from（kc:.. / error:.. / question:..）。

## 双轨重测节奏（修复后）
原题二刷 → T1 → T2 →（错因涉及辨析时）T3。不强制所有 KC 到 T4；由考试权重、错因、复发历史和学生时间预算决定。
```

`references/question-validation.md`:
```markdown
# AI 出题质量闸门

流程：Generator → Independent Solver → Adversarial Reviewer →（适用时）Mechanical Validator → `validate_question.py` 入库。四道闸门缺一不可，`validate_question.py` 是最终裁判。

## 各闸门职责
- Gate 1 Generator（agents/question-generator.md）：产出题面、标准答案、解题思路、迁移等级、改变/保持维度、目标认知陷阱。
- Gate 2 Independent Solver（agents/independent-solver.md）：**只看题面**盲解，检查可解性、条件充分性、唯一解、与 Generator 答案一致（answer_match）。
- Gate 3 Adversarial Reviewer（agents/adversarial-reviewer.md）：专门找茬——超纲？歧义？只是换数字？意外捷径？真的考目标 KC？迁移层级虚标？
- Gate 4 Mechanical Validator（适用时）：数学 SymPy 验算 / 编程执行测试 / 选择题唯一答案检查 / 数值回代。V1 由 Agent 在会话内用工具执行并把结果写进 validation 块。

## 入库硬标准（validate_question.py 强制）
有目标 KC（已注册）、有 derived_from 来源链、有迁移层级、有标准答案、solver answer_match=true、reviewer passed、机械验证（若做了）passed、T2+ 的 changed_dimensions 必须含 surface_context 以外的维度。

## 组装示例
Agent 跑完三卡后组装 candidate JSON（validation 块记录各 gate 结论），然后：
python3 scripts/validate_question.py cand.json --as-transfer-test
未过闸门会得到逐条问题清单；修复后重试，不许绕过。
```

`references/provenance.md`:
```markdown
# 来源可追溯（Provenance）

必须有来源的对象：KC、知识骨架、笔记、题目、标准答案、真题权重、考试风格、AI 生成题、AI 推导结论。

来源类型：syllabus / textbook / lecture_slide / course_note / homework / past_exam /
teacher_emphasis / student_input / synthetic / external_reference。

## 登记方式
- 材料落地 materials/ 后：`event.py source-add --source-id src_012 --source-type lecture_slide --file materials/slides/chapter6.pdf --section "6.2 反馈类型"`。
- KC 注册时用 `--source-id` 关联来源。
- 真实题目注册：candidate JSON 里写 source_type（past_exam/homework/...）和 source_id。
- AI 生成题：derived_from 必须列出 ["kc:..", "error:..", "question:.."]。

## 必须支持的解释
学生问"为什么让我做这道题"，Agent 用 derived_from + 错因记录回答，例如：
"因为它针对你在 2023 年真题第 17 题暴露的『输出采样判断错误』生成，属于 T2 结构迁移，用于验证你不是只记住了原题。"
```

`references/fsrs-policy.md`:
```markdown
# FSRS 策略

FSRS 只负责"什么时候复习"，不负责"是否理解"。理解由六态和迁移阶梯判断。

## 卡片类型（五种）
original_question（原题，尤其真题/课后题/教师重点题——必须建卡，不能只调度 AI 题）、
transfer_question、concept_recall、procedure_recall、misconception_check。

## 何时建卡
- 错题修复完成并通过原题二刷 → 给原题建 original_question 卡。
- 通过的迁移题 → transfer_question 卡。
- 核心概念/流程首次 checked → concept_recall / procedure_recall 卡。
- 高复发错因 → misconception_check 卡（卡面即触发条件场景）。

## 评分映射（fsrs.py review --rating）
1 Again：答错或完全想不起。
2 Hard：答对但置信度 <0.75 或明显吃力。
3 Good：独立顺利答对（默认）。
4 Easy：秒答且能解释为什么。
代码默认策略见 `studylib.fsrs_store.rating_from_result`；Agent 可根据观察覆盖。

## 复习会话
`fsrs.py due` 列到期卡 → 逐卡提问（不给提示，L0）→ `fsrs.py review` 记录。
复习中暴露的错误照常走三步归因，不因为"只是复习"而跳过。
```

`references/next-best-step.md`:
```markdown
# next-best-step

V1 加权和（studylib/nextstep.py）：
P = w1·ExamWeight + w2·Urgency + w3·Weakness + w4·PrereqCentrality
  + w5·ForgettingRisk + w6·TransferGap + w7·BlindSpotRisk − w8·ExpectedTime
所有输入归一化 [0,1]；权重见 DEFAULT_WEIGHTS（weakness 1.5、blind_spot 1.2 最高——
高置信度错误优先修复是产品原则）。

候选动作：repair（weak/blocked）、drill（practiced/explained/checked 有迁移缺口）、
advance（unseen）、review（有到期卡）、rest（无事可做）。

## 输出纪律
不允许只报一个分数。推荐必须带 reasons（脚本已生成），Agent 照此解释，例如：
"建议先修复「反馈组态判断」，预计 12 分钟。原因：存在未修复错因（concept_misconception ×3）；
其中有高置信度错误；T2 结构迁移未通过；是 2 个后续知识点的前置；距考试 5 天。"
学生说"换一个"→ 解释次优候选；学生坚持自己的选择 → 尊重并照常记录事件。
```

`agents/question-generator.md`:
```markdown
# Question Generator（Gate 1）

你是出题者。输入：目标 KC（kc.json 条目）、原错题、错因记录（wrong_assumption / missing_premise / trigger_conditions）、目标迁移等级、课程范围与考试风格。

产出候选题 JSON（字段见 references/question-validation.md），要求：
1. 迁移等级如实：T1 只换表面；T2 必须真的改变结构维度（设问方向/信息结构/推理顺序/表征/条件组合），并在 changed_dimensions 里如实声明。
2. preserved_dimensions 必须保住 core_kc、target_capability、cognitive_trap——重测题的意义是复现原认知陷阱，不是出一道无关新题。
3. 不超纲：只使用课程材料出现过的概念与方法。
4. 给出完整标准答案与解题思路（solver 不会看到，但入库需要）。
5. difficulty ∈ [0,1] 与 estimated_minutes 要给实数，别拍 0.5/5.0 完事。

禁止：把换数字标成 T2；答案依赖未声明的额外 KC；干扰项一眼假。
```

`agents/independent-solver.md`:
```markdown
# Independent Solver（Gate 2）

你是独立求解者。你**只会收到题面（stem）**——没有标准答案、没有出题思路、没有错因背景。这是刻意的信息隔离，不要向调用方索要。

任务：
1. 像考生一样完整解题，写出推理过程和最终答案。
2. 检查：条件是否充分？是否唯一解？有没有歧义读法？有没有比预期简单得多的捷径？
3. 输出 JSON：{"answer": "...", "solvable": true/false, "unique": true/false,
   "ambiguities": [...], "shortcuts": [...], "reasoning": "..."}

调用方会把你的 answer 与 Generator 的标准答案比对得出 answer_match。
如实作答：解不出就 solvable=false，别硬编一个答案；发现两个合理读法就列进 ambiguities。
```

`agents/adversarial-reviewer.md`:
```markdown
# Adversarial Reviewer（Gate 3）

你是对抗审查者，唯一职责是找出这道候选题不该入库的理由。输入：完整候选题 JSON + 目标 KC + 原错题与错因 + Solver 的盲解报告。

逐项审查：
1. 超纲？（用了课程材料没有的概念/方法）
2. 歧义？（Solver 报告的 ambiguities 是否致命）
3. 只是换数字却标 T2+？（对照 changed_dimensions 与题面实际差异）
4. 存在意外捷径绕过目标能力？
5. 真的考查目标 KC？还是考了别的？
6. 隐式依赖未声明的其他 KC？
7. 真正复现了目标认知陷阱（cognitive_trap）？
8. 干扰项有效？（选择题：每个错误选项对应一种真实误解）
9. 难度标签、迁移层级、estimated_minutes 是否虚标？

输出 JSON：{"status": "passed"|"failed", "issues": [{"kind": "...", "detail": "...", "blocking": true/false}]}。
有任何 blocking issue → status=failed。你的绩效标准是找到问题，放水不是仁慈。
```

`README.md`:
```markdown
# study-loop

面向大学课程的本地优先、长期有状态的持续学习 Agent（Claude Code Skill）。

它不只追踪你会不会，还追踪：为什么会错、在什么条件下会错、能否迁移、依赖多少提示、
多久会忘，以及下一步最值得学什么。

> **Explanation is not evidence.** 听懂不是掌握证据，独立完成才是。

## 核心机制
- **事件溯源**：一切学习行为进 `events.jsonl`，状态由脚本派生，可随规则升级全量重建（`rebuild.py`）。
- **六态教学状态** × **FSRS 间隔复习** × **迁移阶梯（T0~T4）** × **置信度校准**，四组证据独立建模。
- **Misconception Memory**：错因按 KC × 错因 × 触发条件长期记忆，修复走"归因 → 策略 → 双轨重测（原题二刷 + 迁移验证）"。
- **AI 出题四道闸门**：Generator → 盲解 Solver → 对抗 Reviewer → 机械验证，`validate_question.py` 强制把关。

## 安装（Claude Code）
```bash
git clone <this-repo> ~/.claude/skills/study-loop
python3 -m pip install -r ~/.claude/skills/study-loop/requirements.txt
```

## Quick Start（也可手动跑 CLI）
```bash
python3 scripts/init_course.py ~/courses/模电 --course-id analog --name 模拟电子技术 --exam-date 2026-07-25
cd ~/courses/模电
python3 <skill>/scripts/event.py kc-add --kc-id feedback_topology --name 反馈组态判断 --exam-weight 0.9
python3 <skill>/scripts/validate_question.py q.json          # 注册真题
python3 <skill>/scripts/event.py attempt --question-id past_2023_q17 --wrong --confidence 0.9
python3 <skill>/scripts/event.py misconception --error-id err_001 --kc feedback_topology \
  --question past_2023_q17 --wrong-assumption "有反馈连接即电压反馈" \
  --missing-premise "必须检查取样方式" --error-type concept_misconception
python3 <skill>/scripts/next_step.py                          # → 建议 repair，并解释为什么
cat .study/dashboard.md
```
在 Claude Code 中直接说 `/study` 或"帮我复习模电"。

## 目录
- `SKILL.md` 主 Agent 路由；`references/` 完整规则；`agents/` 出题三卡；
- `scripts/` CLI 与 studylib 核心库；`templates/` dashboard 模板；`tests/` 全量测试。

## V1 边界（Roadmap）
未实现（按 spec P1-P3 顺序推进）：MarkItDown 材料摄入、自适应诊断选题、HTML 交互测验
attempt 导入、冲刺矩阵、考后回传校准、跨课程学习指纹、学科 profile 向量校正。

## License
MIT
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m pytest tests/test_docs.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add SKILL.md references/ agents/ README.md tests/test_docs.py
git commit -m "docs: SKILL.md routing, references, agent cards, README (spec §34)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 15: 端到端场景 A 集成测试与演示

**Files:**
- Create: `tests/test_e2e_scenario_a.py`, `demo/demo.sh`

**Interfaces:**
- Consumes: 全部模块。验收 spec §42.2 场景 A + 场景 C 关键断言 + §45 最小闭环。

- [ ] **Step 1: 写集成测试**

`tests/test_e2e_scenario_a.py`:
```python
"""spec §42.2 场景 A：完整错题闭环（+场景 C 提示依赖断言）。"""
import json

CID = "analog-electronics"

PASSED_GATES = {"generator": {"status": "passed"},
                "independent_solver": {"status": "passed", "answer_match": True},
                "adversarial_review": {"status": "passed", "issues": []}}


def _ev(root, etype, payload):
    from studylib.events import append_event, new_event
    return append_event(root, new_event(CID, etype, payload))


def test_full_misconception_loop(course):
    from studylib.derive import derive
    from studylib.fsrs_store import new_card_payload
    from studylib.validation import register_question

    # 注册 KC（带前置关系）与真题
    _ev(course, "kc_created", {"kc_id": "feedback_topology", "name": "反馈组态判断",
                               "chapter_id": "chapter_06", "exam_weight": 0.9})
    _ev(course, "kc_created", {"kc_id": "deep_negative_feedback", "name": "深度负反馈",
                               "chapter_id": "chapter_06", "exam_weight": 0.8,
                               "prerequisites": ["feedback_topology"]})
    register_question(course, {
        "question_id": "past_2023_q17", "kc_ids": ["feedback_topology"],
        "source_type": "past_exam", "transfer_level": "T0",
        "stem": "判断该电路的反馈组态", "answer": "A"})

    # 高置信度答错 → 三步归因 → 修复
    _ev(course, "confidence_recorded", {"question_id": "past_2023_q17", "confidence_before": 0.9})
    _ev(course, "question_attempted", {"question_id": "past_2023_q17", "answer": "B",
                                       "correct": False, "confidence_before": 0.9, "hint_level": 0})
    _ev(course, "misconception_identified", {
        "error_id": "err_001", "kc_ids": ["feedback_topology"],
        "origin_question_id": "past_2023_q17",
        "wrong_assumption": "输出端存在反馈连接即可视为电压反馈",
        "missing_premise": "必须检查反馈网络对输出端的取样方式",
        "error_type": "concept_misconception",
        "trigger_conditions": ["复杂电路图"],
        "confidence_before": 0.9, "attribution_confidence": 0.82})

    mid = derive(course)
    assert mid["state"]["next_best_step"]["action"] == "repair"
    assert mid["kc"]["feedback_topology"]["teaching_state"] == "weak"
    assert mid["kc"]["deep_negative_feedback"]["teaching_state"] == "blocked"

    _ev(course, "repair_started", {"error_id": "err_001", "repair_id": "repair_012"})
    _ev(course, "repair_completed", {"error_id": "err_001"})

    # 原题二刷正确
    _ev(course, "question_attempted", {"question_id": "past_2023_q17", "correct": True,
                                       "confidence_before": 0.75, "hint_level": 0,
                                       "retest_of_error_id": "err_001"})

    # T1 迁移题（过闸门）→ 正确；T2 → 错误
    register_question(course, {
        "question_id": "syn_t1_001", "kc_ids": ["feedback_topology"],
        "source_type": "synthetic", "transfer_level": "T1",
        "stem": "换数值的同结构题", "answer": "C",
        "changed_dimensions": ["surface_context"],
        "preserved_dimensions": ["core_kc", "target_capability", "cognitive_trap"],
        "derived_from": ["kc:feedback_topology", "error:err_001", "question:past_2023_q17"],
        "validation": dict(PASSED_GATES)}, as_transfer_test=True)
    register_question(course, {
        "question_id": "syn_t2_001", "kc_ids": ["feedback_topology"],
        "source_type": "synthetic", "transfer_level": "T2",
        "stem": "反向推断：已知组态求电路特征", "answer": "D",
        "changed_dimensions": ["question_direction", "information_structure"],
        "preserved_dimensions": ["core_kc", "target_capability", "cognitive_trap"],
        "derived_from": ["kc:feedback_topology", "error:err_001", "question:past_2023_q17"],
        "validation": dict(PASSED_GATES)}, as_transfer_test=True)

    _ev(course, "transfer_test_attempted", {"question_id": "syn_t1_001", "correct": True,
                                            "confidence_before": 0.75, "hint_level": 0,
                                            "retest_of_error_id": "err_001"})
    _ev(course, "transfer_test_attempted", {"question_id": "syn_t2_001", "correct": False,
                                            "confidence_before": 0.75, "hint_level": 0,
                                            "retest_of_error_id": "err_001"})

    # 原题进 FSRS（原题必须可调度）
    _ev(course, "fsrs_card_created",
        new_card_payload("original_question", ["feedback_topology"], "past_2023_q17"))

    final = derive(course)
    kc = final["kc"]["feedback_topology"]
    err = final["misconceptions"]["err_001"]
    state = final["state"]

    # T2 失败 → 错因回到 active、KC weak、推荐继续修复（§42.2 场景 A 结尾）
    assert err["repair_status"] == "active"
    assert "syn_t2_001" in err["transfer_failures"]
    assert kc["teaching_state"] == "weak"
    assert kc["transfer"]["T1_near"] == 1.0
    assert kc["transfer"]["T2_structural"] == 0.0
    assert state["next_best_step"]["action"] == "repair"
    assert state["next_best_step"]["kc_id"] == "feedback_topology"
    assert any("T2" in r or "迁移" in r for r in state["next_best_step"]["reasons"])
    assert kc["retention"]["fsrs_card_ids"], "原题必须有 FSRS 卡"

    # 派生文件与事件真相一致：errors.jsonl 里就是这条错因
    errors_rows = [json.loads(line) for line in
                   (course / ".study" / "errors.jsonl").read_text(encoding="utf-8").splitlines()]
    assert errors_rows[0]["error_id"] == "err_001"


def test_scenario_c_hint_dependence(course):
    """L4 后答对 → 不允许 checked；随后独立答对 → checked。"""
    from studylib.derive import derive
    _ev(course, "kc_created", {"kc_id": "k_hint", "name": "提示依赖测试"})
    _ev(course, "question_registered", {"question_id": "q_h", "kc_ids": ["k_hint"],
                                        "source_type": "homework", "transfer_level": "T0",
                                        "stem": "s", "answer": "a"})
    _ev(course, "hint_requested", {"question_id": "q_h", "level": 4})
    _ev(course, "question_attempted", {"question_id": "q_h", "correct": True, "hint_level": 4})
    assert derive(course)["kc"]["k_hint"]["teaching_state"] == "practiced"
    _ev(course, "question_attempted", {"question_id": "q_h", "correct": True, "hint_level": 0})
    assert derive(course)["kc"]["k_hint"]["teaching_state"] == "checked"
```

- [ ] **Step 2: 运行确认失败（或直接通过）**

Run: `python3 -m pytest tests/test_e2e_scenario_a.py -v`
Expected: 若前面任务实现正确应 2 passed；任何失败都说明模块间集成有 bug，修复模块实现（不许改弱断言）直到通过。

- [ ] **Step 3: 写演示脚本**

`demo/demo.sh`:
```bash
#!/usr/bin/env bash
# study-loop V1 最小闭环端到端演示（spec §50）
set -euo pipefail
SKILL="$(cd "$(dirname "$0")/.." && pwd)"
DEMO="$(mktemp -d)/模拟电子技术"
export STUDY_LOOP_HOME="$(mktemp -d)/study-home"

py() { python3 "$SKILL/scripts/$1" "${@:2}"; }

echo "== 1. 初始化课程 =="
py init_course.py "$DEMO" --course-id analog --name 模拟电子技术 --exam-date 2026-07-25
cd "$DEMO"

echo "== 2. 注册 KC 骨架（考纲优先）=="
py event.py kc-add --kc-id feedback_topology --name 反馈组态判断 --chapter ch6 --exam-weight 0.9
py event.py kc-add --kc-id deep_negative_feedback --name 深度负反馈 --chapter ch6 \
  --prereq feedback_topology --exam-weight 0.8

echo "== 3. 注册真题 =="
cat > q17.json << 'EOF'
{"question_id": "past_2023_q17", "kc_ids": ["feedback_topology"],
 "source_type": "past_exam", "transfer_level": "T0",
 "stem": "判断该电路的反馈组态", "answer": "A"}
EOF
py validate_question.py q17.json

echo "== 4. 高置信度答错 =="
py event.py attempt --question-id past_2023_q17 --wrong --confidence 0.9

echo "== 5. 三步归因入库 =="
py event.py misconception --error-id err_001 --kc feedback_topology --question past_2023_q17 \
  --wrong-assumption "输出端有反馈连接即电压反馈" --missing-premise "必须检查取样方式" \
  --error-type concept_misconception --trigger 复杂电路图 --confidence-before 0.9

echo "== 6. 修复 + 原题二刷 =="
py event.py repair-start --error-id err_001 --repair-id repair_012
py event.py repair-done --error-id err_001
py event.py attempt --question-id past_2023_q17 --correct --confidence 0.75 --retest-of err_001

echo "== 7. T1 迁移题（过四道闸门）+ 重测 =="
cat > t1.json << 'EOF'
{"question_id": "syn_t1_001", "kc_ids": ["feedback_topology"],
 "source_type": "synthetic", "transfer_level": "T1",
 "stem": "同结构换参数题", "answer": "C",
 "changed_dimensions": ["surface_context"],
 "preserved_dimensions": ["core_kc", "target_capability", "cognitive_trap"],
 "derived_from": ["kc:feedback_topology", "error:err_001", "question:past_2023_q17"],
 "validation": {"generator": {"status": "passed"},
                "independent_solver": {"status": "passed", "answer_match": true},
                "adversarial_review": {"status": "passed", "issues": []}}}
EOF
py validate_question.py t1.json --as-transfer-test
py event.py attempt --question-id syn_t1_001 --correct --confidence 0.75 --transfer --retest-of err_001

echo "== 8. 原题进 FSRS =="
py fsrs.py create-card --card-type original_question --kc feedback_topology --question-id past_2023_q17
py fsrs.py due

echo "== 9. 次日视角：/study 推荐 =="
py next_step.py

echo "== 10. Dashboard =="
cat .study/dashboard.md
echo
echo "演示完成。工作区：$DEMO"
```

- [ ] **Step 4: 运行演示与全量测试**

Run: `chmod +x demo/demo.sh && bash demo/demo.sh && python3 -m pytest`
Expected: 演示打印 10 个步骤、dashboard 含"今日建议"；全量测试通过（约 40+ 用例）。

- [ ] **Step 5: Commit**

```bash
git add tests/test_e2e_scenario_a.py demo/demo.sh
git commit -m "test: end-to-end scenario A misconception loop + demo (spec §42/§45/§50)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## 完成定义（对照 spec §44/§50）

全部任务完成后必须交付：仓库目录树、已实现/未实现功能清单、数据 Schema 位置（schemas.py + 各 references）、CLI 使用示例（README）、一条完整端到端演示（demo/demo.sh 实际输出）、测试结果（pytest 全绿）、已知限制与下一阶段计划（README Roadmap）。

---
