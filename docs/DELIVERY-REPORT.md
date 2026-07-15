# study-loop V1 核心闭环 — 交付报告

> 交付日期：2026-07-15
> 对应规格：`~/Downloads/study-loop-development-spec-v2.md` §45 / §50 最小可用闭环
> 验收状态：✅ **Ready**（终审通过，65/65 测试通过，demo exit 0）

---

## 1. 这是什么

study-loop 是一个**面向大学课程的、本地优先、长期有状态**的持续学习 Agent（Claude Code Skill）。

它的核心信条：

> **Explanation is not evidence.** 听懂不是掌握证据，独立作答才是。

因此它不只记录"会不会"，而是用**事件溯源 + 学习证据图谱**追踪：为什么会错、在什么条件下错、能否迁移、依赖多少提示、多久会忘，以及下一步最值得学什么。

V1 已实现**完整的最小学习闭环**：

```
course init → KC 骨架 → 真题作答 → 答题前置信度 → 高置信度答错
→ 三步归因 → 错因记忆 → 修复 → 原题二刷 → T1/T2 迁移题(过四道闸门)
→ FSRS 调度 → next-best-step → /study 推荐继续
```

---

## 2. 仓库目录树

```text
study-loop/
├── SKILL.md                      # 主 Agent 路由（轻量，规则在 references/）
├── README.md                     # 项目介绍 + Quick Start
├── requirements.txt
├── pytest.ini
├── docs/
│   ├── DELIVERY-REPORT.md        # 本文件
│   ├── USAGE.md                  # 用户操作手册
│   └── superpowers/plans/        # 实施计划（15 任务）
├── scripts/
│   ├── studylib/                 # 核心库（事件溯源 + 派生状态）
│   │   ├── __init__.py           # sys.path bootstrap（防 fsrs 包遮蔽）
│   │   ├── errors.py             # 错误分类（StudyLoopError 体系）
│   │   ├── ioutils.py            # 原子写 / JSONL / 课程锁
│   │   ├── schemas.py            # pydantic 模型 + 受控词表
│   │   ├── events.py             # append-only 事件日志 + 去重
│   │   ├── paths.py              # 课程根定位 / 全局目录
│   │   ├── course.py             # 工作区初始化 + 全局注册表
│   │   ├── registry.py           # KC/题目/来源 派生注册表
│   │   ├── evidence.py           # 学习证据构建（§11）
│   │   ├── misconceptions.py     # 错因记忆 + 双轨重测（§12/§25）
│   │   ├── state_rules.py        # KC 聚合 + 六态派生规则（§10/§14/§37）
│   │   ├── fsrs_store.py         # FSRS 确定性重放（§26）
│   │   ├── nextstep.py           # 可解释 next-best-step（§23）
│   │   ├── validation.py         # AI 出题四道闸门（§16/§43）
│   │   ├── derive.py             # 派生编排器 + state.json + rebuild（§9/§32）
│   │   ├── dashboard.py          # dashboard.md 渲染（§33）
│   │   └── cli_common.py         # CLI 公用：锁+事件+派生
│   ├── init_course.py            # 初始化课程
│   ├── event.py                  # 事件记录（kc-add/attempt/misconception/repair-*/...）
│   ├── validate_question.py      # AI 出题闸门入口
│   ├── fsrs.py                   # FSRS 卡片管理（create-card/review/due）
│   ├── derive_state.py           # 重算状态
│   ├── next_step.py              # /study 推荐入口
│   ├── render_dashboard.py       # 渲染 dashboard
│   ├── rebuild.py                # 从事件全量重建
│   ├── misconception.py          # 错因表
│   └── evidence.py               # 单点证据查询
├── references/                   # 主 Agent 运行时读取的规则手册
│   ├── architecture.md  evidence-graph.md  misconception-memory.md
│   ├── adaptive-diagnosis.md(占位)  transfer-ladder.md  hint-ladder.md
│   ├── question-validation.md  provenance.md  fsrs-policy.md
│   ├── next-best-step.md  sprint-policy.md(占位)
│   └── profiles/                 # 学科 profile（占位，V1 用混合向量）
├── agents/                       # AI 出题三卡（主 Agent 派发用）
│   ├── question-generator.md  independent-solver.md  adversarial-reviewer.md
├── templates/
│   └── dashboard.md.j2           # dashboard 模板
├── demo/
│   └── demo.sh                   # 端到端 10 步演示（set -euo pipefail）
└── tests/                        # 65 个测试
    ├── conftest.py               # home/course fixture
    ├── test_e2e_scenario_a.py    # 端到端闭环 + 场景 C
    └── test_*.py                 # 各模块单元测试
```

---

## 3. 已实现功能清单

### 架构基础（P0）✅
- 事件溯源：`events.jsonl` 是唯一真相，派生状态由纯函数重算
- 原子写入 + 课程锁（filelock，超时 → StateLockTimeout）
- Schema 版本控制（所有机器文件含 `schema_version: "2.0"`）
- append-only + 事件去重（幂等导入）
- 课程工作区初始化 + 全局注册表
- `/study` 主入口（next_step.py）+ 路由表

### 核心差异化（P1）✅
- **六态教学状态**：unseen / explained / practiced / checked / confirmed / weak / blocked
  - 升级规则严格：独立作答（hint ≤ 1）才可能 checked；confirmed 需保持（两次独立正确间隔 ≥1 天）+ 迁移通过（T1/T2）+ 无高置信度活跃错因
  - **听懂/讲解永不升级**；L4/L5 提示下答对只算 practiced（场景 C 已测）
- **学习证据图谱**：KC × Question × Attempt × Confidence × Misconception × Repair × Hint × Transfer × FSRS × Exam
- **错因记忆（Misconception Memory）**：按 `KC × 错因 × 触发条件` 建模，三步归因（错误假设 / 缺失前提 / 错因类型）
- **答题前置信度 + Blind Spot Score**：`B = 置信度 × (1 − 实测表现)`，专抓"以为会了"
- **提示阶梯 L0–L5**：记录学生在多大帮助下完成
- **迁移阶梯 T0–T4**：原题 / 近迁移 / 结构迁移 / 辨析 / 远迁移
- **双轨重测**：原题二刷 + 迁移题；错题解决需 T0 通过 + (T1 或 T2) 通过；失败回退 active
- **FSRS 确定性重放**：从事件重放，rebuild 可信；原题可调度

### 题目质量系统（P2）✅
- **AI 出题四道闸门**：Generator → Independent Solver（盲解，答案一致）→ Adversarial Reviewer（查超纲/歧义/换数字冒充结构迁移）→ Mechanical Validator（可选）
- AI（主 Agent/子代理）负责推理，`validation.py` 负责结构化裁决
- T2+ 必须改 `surface_context` 以外的维度，否则拒绝（防"换数字冒充结构迁移"）
- 真题/课后题免闸门，且优先级高于 AI 生成题

### CLI 门面 ✅
- 11 个 Typer 脚本，统一锁+事件+自动派生
- 错误友好化：`StudyLoopError` → 一行人话 + exit 1，不抛原始堆栈

### 文档 ✅
- SKILL.md（轻路由）+ 9 个 references + 3 个 agent 卡片 + README
- demo.sh 端到端可跑

---

## 4. 核心数据 Schema

### state.json（当前快照，§32）
```json
{
  "schema_version": "2.0",
  "course": {"id": "analog-electronics", "name": "模拟电子技术"},
  "profile": {"quantitative": 0.3, "conceptual": 0.3, "procedural": 0.2,
              "programming": 0.0, "language": 0.0, "memory": 0.2, "confidence": 0.3},
  "current": {"phase": "repair", "last_session": "session_adhoc"},
  "exam": {"date": "2026-07-25", "days_remaining": 10},
  "readiness": {"level": "low", "score": 0.15},
  "counts": {"unseen": 0, "explained": 0, "practiced": 0,
             "checked": 0, "confirmed": 0, "weak": 1, "blocked": 0},
  "due_cards": 0,
  "active_misconceptions": 1,
  "next_best_step": {
    "action": "repair", "kc_id": "feedback_topology", "kc_name": "反馈组态判断",
    "estimated_minutes": 12, "priority_score": 3.21,
    "reasons": ["当前状态：weak", "存在未修复错因（concept_misconception ×1）",
                "其中有高置信度错误", "距考试 10 天"]
  },
  "updated_at": "2026-07-15T14:40:00+08:00"
}
```

### kc.json（每 KC 的多维状态，§10.4）
每行含：`teaching_state`、`retention{fsrs_card_ids, retrievability, due_count}`、`transfer{T0_original..T4_far}`、`calibration{self_estimate, observed_performance, gap, blind_spot}`、`assistance{last_hint_level, independent_success_rate}`、`evidence_ids`、`active_misconceptions`。

### 其他机器文件
- `events.jsonl` — 真相源（append-only，永不修改）
- `evidence.jsonl` / `errors.jsonl` / `cards.jsonl` / `questions.jsonl` / `sources.jsonl` — 派生状态（derive 整体重写）
- `dashboard.md` — 只读展示

---

## 5. CLI 使用示例（V1 最小闭环）

```bash
# 0. 安装依赖
python3 -m pip install -r requirements.txt

# 1. 初始化课程（在某目录）
python3 scripts/init_course.py ~/courses/模电 \
  --course-id analog-electronics --name 模拟电子技术 --exam-date 2026-07-25
cd ~/courses/模电

# 2. 注册知识骨架（考纲优先）
python3 scripts/event.py kc-add --kc-id feedback_topology --name 反馈组态判断 \
  --chapter ch6 --exam-weight 0.9

# 3. 注册真题
python3 scripts/validate_question.py /tmp/q17.json   # source_type=past_exam

# 4. 作答（先问置信度，这里 0.9）
python3 scripts/event.py attempt --question-id past_2023_q17 --wrong \
  --confidence 0.9 --time-sec 78

# 5. 三步归因
python3 scripts/event.py misconception --error-id err_001 --kc feedback_topology \
  --question past_2023_q17 \
  --wrong-assumption "输出端有反馈连接即电压反馈" \
  --missing-premise "必须检查反馈网络的取样方式" \
  --error-type concept_misconception --trigger "复杂电路图" \
  --confidence-before 0.9 --attribution-confidence 0.82

# 6. 修复
python3 scripts/event.py repair-start --error-id err_001 --repair-id repair_001
python3 scripts/event.py repair-done  --error-id err_001

# 7. 双轨重测：原题二刷（对）
python3 scripts/event.py attempt --question-id past_2023_q17 --correct \
  --confidence 0.8 --transfer --retest-of err_001
#            迁移题（T1 对 / T2 错，由 validate_question.py --as-transfer-test 注册）
python3 scripts/event.py attempt --question-id syn_t1 --correct \
  --confidence 0.75 --transfer --retest-of err_001

# 8. 进 FSRS
python3 scripts/fsrs.py create-card --card-type original_question \
  --kc feedback_topology --question-id past_2023_q17

# 9. /study 推荐（每次作答后 CLI 自动重算并打印 next-best-step）
python3 scripts/next_step.py
```

---

## 6. 端到端演示

```bash
bash demo/demo.sh
```

10 步真实跑通闭环，每步打印 next-best-step，结束打印 dashboard.md（含"今日建议"）。任一步失败即终止（`set -euo pipefail`）。

---

## 7. 测试结果

```text
$ python3 -m pytest
65 passed in 1.4s
```

覆盖：事件写入/去重、Schema 校验、状态派生、六态转换、Blind Spot、next-best-step、诊断选题、FSRS 创建/复习/确定性、attempt 导入、来源链、题目验证、rebuild、端到端场景 A + 场景 C。

---

## 8. 终审结论与处理记录

**终审判定：Ready，可交付。**

终审（opus，跨模块一致性 + §0/§38/§45 全系统核验）核验四条不变量全部成立：
1. ✅ 无派生 JSON 绕过 `derive` 的路径（所有写状态 CLI 都过 `course_lock` + `derive`）
2. ✅ 事件不被修改（下游只读，无就地写）
3. ✅ 每个 CLI 的 `derive` 都在 `course_lock` 内
4. ✅ AI 无法绕过出题闸门（唯一注册路径是 `validate_question.py` → `validation.py`）

**终审已修复（2 个必修项）：**
| Commit | 内容 |
|---|---|
| `3cc3a34` | 清理 `scripts/studylib/__init__.py` 中的死代码块（`_scripts_dirs` 扫描循环与 `_sp_dirs` 集合，结果从未使用） |
| `238dd01` | `__init__.py` 路径定位从 `rsplit("/studylib/")`（仅 POSIX）改为 `Path(__file__).resolve().parent.parent`（跨平台） |

**Critical / Important：**
- Critical：无
- Important（**延期到 V1.1，不阻塞交付**）：**已解决的错因复发不会重新激活**——同一 `(kc, 错因, 错误假设)` 的 `misconception_identified` 复发时，只更新 `recurrence_count` 等字段，不把 `resolved` 状态打回 `active`。这超出 §45 最小闭环（闭环是"解决导向"而非"复发导向"），V1.1 修复（见下）。

---

## 9. 已知限制（V1 边界）

V1 是**最小可用闭环**，以下能力**未实现**（规格中标为后续阶段 P2/P3）：

- **材料摄入管线**：`ingest.py`（MarkItDown 转换 + 缓存）未实现。当前需手工或借助主 Agent 把课件/教材转成文本再注册 KC。
- **自适应诊断**：`diagnose.py`（自评全图 + 抽测校准）未实现。当前作答是手工或对话驱动。
- **HTML attempt 包导入**：`import_attempt.py`（quiz.html → 自动回传）未实现。
- **考后回传与校准**：`exam_feedback.py`（真实考试结果反向修正系统）未实现。
- **跨课程学习指纹**：`learning-fingerprint.json`（跨课稳定行为模式）未实现。
- **冲刺矩阵**：`sprint-policy.md`（剩余时间 × 准备度）为占位，未实现。
- **HTML 测验/模拟卷模板**：`quiz.html` / `mock_exam.html` 未实现。
- **多用户 / 云同步 / GUI**：规格明确列为非目标。

工程层面延期项（V1.1，非阻塞）：
1. 错因复发重新激活（Important，见上）
2. 证据/卡片按解析时间排序（防混合时区）
3. `build_questions` 对 payload 做防御性拷贝
4. `kc_updated` 的 exam_weight 补 `float()` 强转
5. 空 `kc_ids` / 未知 `error_id` 的校验
6. 无锁读路径的读时写竞争（单用户 V1 可接受）

---

## 10. 下一阶段计划（V1.1 → V2）

按规格 §46 的阶段排序：

- **P2 收尾**：补齐 ingest（材料摄入）、adaptive-diagnosis、HTML attempt 导入——把闭环从"手工驱动"升级为"材料驱动 + 自动诊断"。
- **P3 长期智能**：考后回传 + 跨课程指纹 + 基于真实考试校准 next-best-step 权重。
- **冲刺阶段**：实现冲刺矩阵，闭环最后一环。
- **V1.1 工程硬化**：上述 6 个延期项。

---

## 11. 怎么用

- **日常使用**：见 [`docs/USAGE.md`](./USAGE.md)（面向学生的操作手册）。
- **开发/二次开发**：见 [`SKILL.md`](../SKILL.md) + `references/`（主 Agent 运行时规则）+ `docs/superpowers/plans/`（15 任务实施计划）。
