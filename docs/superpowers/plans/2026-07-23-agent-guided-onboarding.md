# Agent Guided Onboarding Implementation Plan

> **For agentic workers:** Implement this plan task-by-task with review checkpoints. This repository's working rules prohibit automatic commits, so verification will be performed without creating a commit.

**Goal:** Make the `study-loop` Agent guide beginners through one-question-at-a-time intent routing while preserving existing CLI, state, and question-validation rules.

**Architecture:** Keep the behavior in the existing `SKILL.md` routing contract. Add a small documentation contract test that protects the single-question policy and the explicit-intent fast path. Explain the same flow in `docs/USAGE.md` and both README files; do not add a new runtime router or modify Python state logic.

**Tech Stack:** Markdown prompt contracts, Python `pytest`, existing Claude Code Skill routing, GitHub README Markdown.

---

### Task 1: Add failing documentation-contract tests

**Files:**
- Modify: `C:/Users/monke/Desktop/git/agent-one/study-loop/tests/test_docs.py`
- Test: `C:/Users/monke/Desktop/git/agent-one/study-loop/tests/test_docs.py`

- [ ] **Step 1: Add the onboarding contract test**

Append these tests after `test_readme_has_quickstart()`:

```python
def test_skill_guided_onboarding_contract():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    required = [
        "每轮最多问一个问题",
        "你今天想做哪件事？",
        "用户已经明确说明目标时，直接路由",
        "不循环追问",
        "没有课程",
        "没有 KC",
        "没有到期卡",
    ]
    for phrase in required:
        assert phrase in text, f"SKILL.md 缺少引导契约：{phrase}"


def test_readmes_show_guided_onboarding():
    zh = (ROOT / "README.md").read_text(encoding="utf-8")
    en = (ROOT / "README_EN.md").read_text(encoding="utf-8")
    assert "先分流，再执行" in zh
    assert "route the intent before executing" in en
```

- [ ] **Step 2: Run only the new tests and verify the expected RED state**

Run from `C:/Users/monke/Desktop/git/agent-one/study-loop`:

```powershell
$env:PYTHONUTF8 = "1"
.venv\Scripts\python.exe -m pytest tests/test_docs.py -k "guided_onboarding" --basetemp tmp\plan-red
```

Expected: FAIL because the current `SKILL.md` and README files do not yet contain the new contract phrases.

### Task 2: Implement the guided onboarding contract

**Files:**
- Modify: `C:/Users/monke/Desktop/git/agent-one/study-loop/SKILL.md`

- [ ] **Step 1: Add the onboarding protocol after the 铁律 section**

Add a `## 新手引导协议` section containing these rules:

```markdown
## 新手引导协议

### 先判断是否需要提问

- 用户已经明确说明目标时，直接路由，不重复询问。
- 用户只说 `/study`、"继续"或"帮我学习"时，先运行 `python3 scripts/next_step.py`，再进入一次开场分流。
- 每轮最多问一个问题，选项控制在 3–5 个。
- 用户拒绝回答时，给出当前可执行的最小下一步，不循环追问。

### 开场分流

目标不明确时，只问：

```text
你今天想做哪件事？
A. 继续今天的学习
B. 做题/刷题
C. 修复一道错题
D. 查看学习状态
E. 准备考试
```

用一句话说明每个选择会触发什么流程，不把 CLI 参数直接丢给学生。

### 分支追问

- 刷题：按模式 → 题量 → 输出形态的顺序逐项确认；用户已提供的字段不再询问。
- 新课程：先确认课程名称和目录，再运行 `init_course.py`；知识点骨架按考纲逐步注册。
- 错题修复：先确认题目或错因，再进入错误假设、缺失前提、错因类型三步归因。
- 查看状态：直接调用 dashboard、错因表或单点证据命令，不询问无关信息。
- 考试准备：先读取考试日期和 `next-best-step`；缺少考试日期时只提醒如何补充。

### 状态解释

- 没有课程：说明课程工作区需要 `course.yaml`，给出 `init_course.py` 示例。
- 没有 KC：说明知识点是安排复习的骨架，建议先从考纲注册。
- 没有题目：说明需要注册真题/课后题，或明确请求生成迁移题。
- 没有到期卡：说明当前没有紧急 FSRS 复习，不把它误报成“已经掌握”。
```

- [ ] **Step 2: Update the existing `/study` opening rules**

Replace the current three-item opening behavior with a short reference to `新手引导协议`, keeping the existing `next_step.py` command and the rule that clear user intent routes directly.

- [ ] **Step 3: Run the contract tests and verify GREEN**

```powershell
$env:PYTHONUTF8 = "1"
.venv\Scripts\python.exe -m pytest tests/test_docs.py -k "guided_onboarding" --basetemp tmp\plan-green
```

Expected: 2 passed.

### Task 3: Document the beginner-facing conversation

**Files:**
- Modify: `C:/Users/monke/Desktop/git/agent-one/study-loop/docs/USAGE.md`

- [ ] **Step 1: Add a section after `## 3. 日常入口：`**

Add `### Agent 会怎样引导你` with one concrete flow:

```text
你：帮我学习
Agent：先检查今天的状态，然后问：你今天想做哪件事？
你：做题
Agent：你想按考纲复习，还是先诊断薄弱点？
你：按考纲
Agent：准备做几道？5 道、10 道，还是自定义？
```

Explain that the Agent asks only for missing information, and that a fully specified request such as “按考纲出 5 道 HTML 题” will run directly.

- [ ] **Step 2: Add the four empty-state explanations**

Document the meaning and next action for no course, no KC, no questions, and no due cards without claiming mastery.

### Task 4: Synchronize the public examples and changelog

**Files:**
- Modify: `C:/Users/monke/Desktop/git/agent-one/study-loop/README.md`
- Modify: `C:/Users/monke/Desktop/git/agent-one/study-loop/README_EN.md`
- Modify: `C:/Users/monke/Desktop/git/agent-one/study-loop/CHANGELOG.md`

- [ ] **Step 1: Add one guided onboarding example to both READMEs**

Add a short sentence near the example-request tables.

Chinese:

```text
不确定从哪里开始时，直接说“帮我学习”；Agent 会先检查状态，再用一个问题把你带到正确流程。
```

English:

```text
If you are unsure where to start, say “Help me study”; the agent checks your state first, then routes you with one question.
```

- [ ] **Step 2: Add a `[Unreleased]` changelog entry**

Record the `SKILL.md`, `docs/USAGE.md`, README, and `tests/test_docs.py` changes in Chinese.

- [ ] **Step 3: Verify README heading parity and links**

```powershell
$zh = (Select-String -Path README.md -Pattern '^## ' -AllMatches).Count
$en = (Select-String -Path README_EN.md -Pattern '^## ' -AllMatches).Count
if ($zh -ne $en) { throw "README heading count mismatch: $zh vs $en" }
```

Expected: no output and exit code 0.

### Task 5: Run the complete verification suite

**Files:**
- Read: `C:/Users/monke/Desktop/git/agent-one/study-loop/SKILL.md`
- Read: `C:/Users/monke/Desktop/git/agent-one/study-loop/docs/USAGE.md`
- Read: `C:/Users/monke/Desktop/git/agent-one/study-loop/tests/test_docs.py`

- [ ] **Step 1: Run the full test suite in the repository temp directory**

```powershell
$env:PYTHONUTF8 = "1"
New-Item -ItemType Directory -Force tmp\plan-final | Out-Null
.venv\Scripts\python.exe -m pytest --basetemp tmp\plan-final
```

Expected: all tests pass, including the new onboarding contract tests.

- [ ] **Step 2: Check whitespace and repository status**

```powershell
git diff --check
git status --short
```

Expected: `git diff --check` exits 0; only the intended B files and the previously existing uncommitted README/asset files are listed.

- [ ] **Step 3: Review the final diff for forbidden behavior changes**

Confirm that no changes touch `scripts/`, `scripts/studylib/`, `references/`, course `.study/` data, or JSON schemas. Do not commit automatically.
