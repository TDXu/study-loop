# 变更记录 (CHANGELOG)

本文件记录 study-loop 每次修改了什么、增加了什么功能。**每次改动后必须追加一条记录**（见 `CLAUDE.md` 的「变更纪律」）。

格式约定：

- 按时间倒序（最新在上）。
- 每条记录包含：日期、类型（`feat` 新功能 / `fix` 修复 / `refactor` 重构 / `docs` 文档 / `chore` 杂项）、一句话摘要、涉及的文件/命令、以及（如有）破坏性变更。
- 关联提交：在记录末尾写上对应的 `git commit` 短哈希，方便回溯。

类型对照：

| 类型 | 含义 |
|---|---|
| `feat` | 新增功能（用户能感知的新能力） |
| `fix` | 修复 bug |
| `refactor` | 重构，不改外部行为 |
| `docs` | 文档/手册/SKILL.md 更新 |
| `chore` | 构建、依赖、git、脚手架等杂项 |

---

## [Unreleased]

### 2026-07-21 — `docs` — CLAUDE.md 新增两条工作纪律
- 功能版本更新必须同步 `README.md`（与 `CHANGELOG.md` 带版本号小节对应），避免 README 与实际能力脱节。
- 所有更新备注（`git commit` message / `CHANGELOG.md`）一律用中文；代码、标识符、命令仍用英文。
- 涉及：`CLAUDE.md`「变更纪律（重要）」小节。

## [V2.0-rc1] - 2026-07-20

### 2026-07-21 — `chore` — V2 功能合并入 main 主干（e1e3825）
- 将 `feat/v2-display-drill-output`（F1 / F2 / F3，14 commits）以 `--no-ff` 合并入 `main`；全量 `pytest` 100 passed。
- 合并后同步推送 `origin/main`。涉及命令：`git merge --no-ff` / `git push origin main`。

### 2026-07-20 — `feat` — F2 学习模式引擎 + 一站式 drill 命令
- 新增 `studylib.drill`：`select_kcs`（考纲加权 / 诊断自适应，seed 确定性）、`gather_questions`（凑题 + 缺口检测）。
- 新增 CLI `scripts/drill.py`：选题→凑题→manifest→渲染（html/paper/md），打印 KC 标签、缺口、下一步建议。
- `SKILL.md` 路由表新增「刷题/出题/模拟卷」意图（先问模式/题量/形态再出）。

### 2026-07-20 — `feat` — F3 选择题输出（网页 / PDF 试卷）
- 新增 `studylib.manifest`（drill manifest 契约）、`studylib.render_html` + `templates/quiz.html.j2`（自包含交互测验页，运行时解析开关）、`studylib.render_paper`（manifest→PDF，支持题目卷/答案解析卷，CID 字体回退免装字体）。
- 新增 CLI：`scripts/render_quiz_html.py`、`scripts/render_paper.py`；移除 `scripts/md_to_pdf.py`（其能力并入 render_paper）。
- `requirements` 加 `reportlab>=4.0`。

### 2026-07-20 — `feat` — F1 KC 中英对照显示
- 新增 `studylib.display.kc_label`；接入 next_step / dashboard / evidence / misconception 输出，统一 `kc_id（中文名）`。
- `ioutils` 新增 `read_json`。涉及：`nextstep.py` `dashboard.py` `cli_common.py` `templates/dashboard.md.j2` `scripts/evidence.py` `scripts/misconception.py`。

### 2026-07-20 — `chore` — 建立版本控制与变更纪律基线

- 将本地 git 纳入「每次修改可追踪」的工作流：新增本文件 `CHANGELOG.md` 与 `CLAUDE.md`。
- `.gitignore` 增加 `tmp/`（OCR 图片、字体、候选题 JSON 等可再生产物不入库）。
- 首次纳入版本控制的前置脚本（此前未跟踪）：
  - `scripts/ocr_pdfs.py` — OCR 习题册 PDF 抽取题目原文。
  - `scripts/gen_questions.py` / `scripts/gen_questions2.py` — 把 OCR 结果整理成候选题 JSON（毛中特：毛泽东思想 / 邓小平理论，共 ~40 题）。
  - `scripts/md_to_pdf.py` — 把模拟卷 Markdown 渲染成带中文字体的 PDF。
  - 注意：上述脚本含硬编码绝对路径（`/Users/td_xu/...`），后续会随「网页版/试卷生成」功能一起参数化。
- 计划中（本轮需求，待设计确认后实现）：
  1. KC 名称中英对照显示（`kc_id（中文名）`）。
  2. 学习模式选择：考纲直出+复盘 / 诊断先行+针对性出题，可选题数（5/10…）。
  3. 文科选择题输出形态选择：本地网页可点击测验 / PDF 试卷；网页版支持「点击即显示答案解析」开关。
