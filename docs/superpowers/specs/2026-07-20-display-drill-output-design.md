# study-loop V2：KC 显示 / 学习模式 / 网页·试卷输出 — 设计文档

- 日期：2026-07-20
- 状态：已与用户确认设计，待写实现计划
- 关联：`CHANGELOG.md` [Unreleased]；用户手册 `docs/USAGE.md`；主路由 `SKILL.md`

## 1. 背景与目标

study-loop V1 已交付（事件溯源、六态教学状态、FSRS、迁移阶梯、错因记忆、AI 出题四闸门）。
README 的 V1 roadmap 列出三项尚未实现的能力，正是本轮需求：

1. **KC 名称中英对照显示**（面向更广用户群体）。
2. **学习模式选择**：考纲直出 + 复盘 / 诊断先行 + 针对性出题；可选题量（5/10/…）。
3. **文科选择题输出形态选择**：本地网页可点击测验 / PDF 试卷；网页版支持「点击即显示答案解析」的运行时开关。

实战课程：**毛中特**（文科、选择题密集），已有 ~40 道候选选择题在 `tmp/q/`。

### 用户已确认的决策

| 决策点 | 选择 |
|---|---|
| 本轮范围 | 三个一起做，顺序 `F1 → F3 → F2` |
| KC 显示格式 | `kc_id（中文名）`，如 `mao_living_soul（毛泽东思想活的灵魂）` |
| 诊断选题依据 | 自适应：有掌握记录→按弱点抽；无记录→退化为按考纲权重随机 |
| 解析开关方式 | 页面内运行时开关（学生随时切） |

## 2. 总体架构

一条主线串联三项功能：

```
选题（模式 + 题量）  →  题集（drill manifest）  →  渲染（HTML | PDF）
        F2                    契约                    F3
```

外加贯穿全局的显示工具（F1）。F3 渲染器先就位，F2 的 `drill` 命令再调用它们，故实现顺序 `F1 → F3 → F2`。

`drill manifest` 是 F2 与 F3 之间的唯一契约：一个 JSON，含 `meta`（course/mode/count/generated_at）与 `questions`（Question schema 题数组；渲染不依赖 validation 块）。

## 3. F1 — KC 中英对照显示

**目标**：所有面向用户的输出中，KC 以 `kc_id（中文名）` 呈现。

**现状**：
- `nextstep.py` 推荐用 `kc_name`（中文），不含 id。
- `dashboard.py` + 模板用 `kc['name']`（中文）。
- `evidence`、`misconception` 命令及 Agent 对话常只露英文 `kc_id`。

**实现**：
- 新增 `scripts/studylib/display.py`：
  - `kc_label(kc_id, kcs) -> str`：返回 `f"{kc_id}（{name}）"`；`kcs` 中无该 id 或无 name 时退化为 `kc_id`。name 与 id 相同时只返回一次。
  - `question_label(qid, questions)`：类似工具（如需要）。
- 接入点（统一替换裸 id / 裸 name 为 label）：
  - `studylib/nextstep.py`：推荐字典新增/改用 `kc_label`（保留 `kc_name` 字段以向后兼容测试，新增 `kc_label`）。
  - `studylib/dashboard.py` `build_risks` + `templates/dashboard.md.j2`。
  - `scripts/evidence.py`、`scripts/misconception.py` 的输出。
- `SKILL.md`：在「铁律」或路由表加一条——Agent 在讲解与路由中引用 KC 时一律用 `kc_id（中文名）`。

**测试**：`tests/test_display.py` 覆盖三种情形（有中文名、无中文名、name==id）；受影响快照/断言测试同步更新。

**完成判据**：dashboard、next_step、evidence、misconception 四处输出均出现 `kc_id（中文名）` 形式。

## 4. F3 — 选择题输出：本地网页 / PDF 试卷

### 4.1 drill manifest 契约

```json
{
  "schema_version": "2.0",
  "meta": {
    "course_id": "mao-zhongte",
    "course_name": "毛中特",
    "mode": "diagnostic",
    "count": 10,
    "generated_at": "2026-07-20T14:00:00+08:00"
  },
  "questions": [
    { "question_id": "...", "kc_ids": [...], "stem": "...", "answer": "ABC",
      "solution": "...", "difficulty": 0.5, "transfer_level": "T0" }
  ]
}
```

渲染器只读 manifest，不触碰事件层。

### 4.2 本地网页可点击测验

- 模板 `templates/quiz.html.j2`（Jinja2，与 `dashboard.md.j2` 同级）。
- 自包含单文件 HTML：内联 CSS + JS，**无外部依赖、无需服务器**，双击即开。
- 题型推断：`answer` 去重后长度 = 1 → 单选 radio；> 1 → 多选 checkbox。
- 每题卡片顶部显示 KC 标签（F1 格式）；题号、难度可选展示。
- **运行时解析开关**（页面顶部 switch「即时显示解析」）：
  - 开：点击选项即在题目下方显示对错 + solution。
  - 关：做完后点「提交对答案」批量显示结果、对错、解析与总分。
  - 默认状态由生成参数 `--reveal-default on|off` 决定；学生运行时随时切换。
- 命令 `scripts/render_quiz_html.py`：
  ```
  render_quiz_html.py --manifest m.json [--out quiz.html] [--reveal-default on|off]
  ```

### 4.3 PDF 试卷（参数化重构）

- 把 `scripts/md_to_pdf.py`（硬编码路径）重构为 `scripts/render_paper.py`：
  - 参数：`--manifest m.json --variant {questions,answers,both} --out <dir> [--fonts-dir <path>]`。
  - `questions`：纯题目卷；`answers`：答案 + 解析卷；`both`：两份都出。
  - 字体目录参数化（默认 `tmp/fonts/`，可覆盖），去掉写死的 `/Users/...`。
  - 复用现有 reportlab + 黑体（Body/HeitiM）样式与 `parse()`/`inline()` 逻辑。

**测试**：
- `tests/test_render_quiz_html.py`：manifest→HTML，断言开关存在、选项数正确、答案已内嵌（默认隐藏）、单/多选正确。
- `tests/test_render_paper.py`：manifest→PDF，断言文件生成、变体正确（answers 卷含 solution 文本）。

**完成判据**：同一 manifest 既能出可点击网页，也能出 PDF 题目卷/解析卷。

## 5. F2 — 学习模式引擎：考纲直出 / 诊断先行

### 5.1 选题与凑题（纯函数）

新增 `scripts/studylib/drill.py`：

- `select_kcs(kc_states, mode, count, seed) -> list[str]`：
  - `mode="syllabus"`：在全部 KC 上按 `exam_weight` 加权随机抽 `count` 个（不重复）。
  - `mode="diagnostic"`（自适应）：
    - 若存在任何非 `unseen` 的 KC（即有学习记录）：按弱点权重排序——`weak`/`blocked` 最高，其次 `practiced`/`explained`/`unseen`/`checked`，`confirmed` 最低——加权抽 `count` 个。
    - 若全部 `unseen`（新课程）：退化为 `syllabus` 行为。
  - `seed` 固定时结果确定，便于测试与复盘。
- `gather_questions(questions, kc_ids, per_kc, total) -> (list[dict], shortfall)`：
  - 从已注册题目里为每个选中 KC 取至多 `per_kc` 题，总数不超过 `total`。
  - 题量不足时返回 `shortfall`（缺哪些 KC、缺几题），**不静默触发 AI 出题闸门**。

### 5.2 drill 命令（一站式）

新增 `scripts/drill.py`：
```
drill.py --mode {syllabus,diagnostic} --count N [--per-kc M]
         [--format {html,paper,md}] [--out PATH] [--reveal-default on|off]
         [--seed INT] [--course <path>]
```
流程：resolve course → derive state → `select_kcs` → `gather_questions` → 写 manifest → 按 `--format` 调渲染器 → 打印人话总结。

总结包含：选中 KC（带中文标签）、实际题数、`shortfall` 警告、下一步建议：
- `syllabus`：做完后对同 KC 做复盘重测（迁移题）。
- `diagnostic`：据作答结果对命中的弱 KC 针对性出题/修复。

### 5.3 「问用户」落点

`SKILL.md` 路由表新增意图 **「刷题 / 出题 / 模拟卷」**：Agent 先问三件事——
1. 模式：考纲直出 / 诊断先行？
2. 题量：5 / 10 / 自定义？
3. 形态：网页可点击 / PDF 试卷？
然后跑 `drill.py`。作答后的复盘/修复仍走现有 `next_step` + `misconception` 流程。

**测试**：
- `tests/test_drill_select.py`：`select_kcs` 固定 seed 确定性、模式语义（diagnostic 优先 weak、全 unseen 时退化）、不重复。
- `gather_questions` 缺口检测、per_kc/total 上限。

**完成判据**：`drill.py --mode diagnostic --count 10 --format html` 一条命令产出可点击网页，且选题符合自适应规则。

## 6. 非目标（YAGNI）

- 网页/PDF 作答结果**不自动回写** `events.jsonl`；本轮输出形态是练习用。计分事件闭环仍是 Agent 驱动的 `event.py attempt`。schema 已预留 `attempt_package_imported`，留作未来。
- `drill` 内不自动走 AI 出题四闸门；只暴露 `shortfall`。
- 不在 `drill` 内自动建 FSRS 卡片（已有 `fsrs.py create-card`）。

## 7. 涉及文件

| 类型 | 文件 |
|---|---|
| 新增 | `scripts/studylib/display.py`、`scripts/studylib/drill.py`、`templates/quiz.html.j2`、`scripts/render_quiz_html.py`、`scripts/render_paper.py`、`tests/test_display.py`、`tests/test_drill_select.py`、`tests/test_render_quiz_html.py`、`tests/test_render_paper.py` |
| 改动 | `scripts/studylib/nextstep.py`、`scripts/studylib/dashboard.py`、`templates/dashboard.md.j2`、`scripts/evidence.py`、`scripts/misconception.py`、`SKILL.md`、`CHANGELOG.md` |
| 重构 | `scripts/md_to_pdf.py` → `scripts/render_paper.py`（保留旧文件为薄封装或删除，实现时定） |

## 8. 风险与回滚

- **F1 改 nextstep 字段**：保留 `kc_name`，新增 `kc_label`，避免破坏现有测试/消费者。
- **md_to_pdf 重构**：现有 `tmp/` 下产出的 PDF 用于对照，重构后冒烟测试保证渲染不退化。
- **HTML 安全**：题面/解析做 HTML 转义，防注入与排版错乱。
- 全程 TDD：每个纯函数与渲染器先写测试。每步 `pytest` 绿 + `CHANGELOG` 记录后再下一步，便于单步回滚（`git revert`）。
