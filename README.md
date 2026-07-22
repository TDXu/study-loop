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

## V2：一站式刷题与多形态输出
- **KC 中英对照显示**：所有面向用户的输出统一用 `kc_id（中文名）`（如 `feedback_topology（反馈组态判断）`），贯穿 next-step / dashboard / evidence / misconception。
- **一条命令刷题**（`scripts/drill.py`）：选好模式与题量即出题，自动凑题、缺口检测、并给出下一步建议。
  - 模式：`--mode syllabus`（按考纲权重直出）/ `--mode diagnostic`（按弱点自适应）
  - 题量：`--count 5|10|...`，每 KC 题数 `--per-kc`，确定性种子 `--seed`
  - 形态：`--format html`（自包含可点击交互测验）/ `paper`（PDF 题目卷 + 答案解析卷）/ `md`
  - 网页版「点击显示解析」默认开关：`--reveal-default on|off`（学生也可在页面内随时切换）
- **PDF 试卷**：内置 CID 字体回退，免装中文字体即可出卷（`render_paper.py`）。

```bash
# 考纲直出 10 题，生成交互测验页（默认开「点击显示解析」）
python3 scripts/drill.py --mode syllabus --count 10 --format html

# 诊断先行：按弱点自适应出 5 题，出 PDF 试卷（题目卷 + 答案解析卷）
python3 scripts/drill.py --mode diagnostic --count 5 --format paper
```

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
- `scripts/` CLI 与 studylib 核心库；`templates/` dashboard 与测验模板；`tests/` 全量测试。

## 版本发布历史

### V2（2026-07-20，[V2.0-rc1]）— display / drill / output
- **F1 KC 中英对照显示**：`kc_label` 统一 `kc_id（中文名）`，接入 next-step / dashboard / evidence / misconception。
- **F2 学习模式引擎 + 一站式 drill**：`select_kcs`（考纲加权 / 诊断自适应，seed 确定性）+ `gather_questions`（凑题 + 缺口检测）；`scripts/drill.py` 一条命令贯通 选题→凑题→manifest→渲染。
- **F3 选择题输出**：自包含交互测验页（运行时「点击显示解析」开关）+ PDF 试卷渲染（题目卷/答案解析卷，CID 字体回退免装字体）；移除旧 `md_to_pdf.py`。
- 用法详见上方「V2：一站式刷题与多形态输出」。14 commits 合入 main，pytest 100 passed。

### V1（2026-07-15）— 核心学习闭环
- **架构基础**：事件溯源（`events.jsonl` 唯一真相）+ 原子写 / 课程锁 + append-only 去重 + 课程工作区 / 全局注册表 + Schema 版本控制。
- **核心差异化**：六态教学状态、学习证据图谱、错因记忆（三步归因 + 双轨重测）、答题前置信度 + Blind Spot Score、提示阶梯 L0–L5、迁移阶梯 T0–T4、FSRS 确定性重放。
- **题目质量**：AI 出题四道闸门（Generator → 盲解 Solver → 对抗 Reviewer → 机械验证）。
- **CLI 门面**：11 个 Typer 脚本，统一锁 + 事件 + 自动派生，错误友好化。
- **文档**：SKILL.md 路由 + references 规则 + agents 出题三卡 + demo 端到端。验收 65/65 测试通过，终审 Ready。

## Roadmap

### 下一步计划（规格 P2/P3，尚未实现）
- **材料摄入管线**（`ingest.py` / MarkItDown）：课件 / 教材自动转文本并注册 KC，把闭环从"手工驱动"升级为"材料驱动"。
- **完整自适应诊断**（`diagnose.py`，自评全图 + 抽测校准）：V2 的 drill `--mode diagnostic` 仅做"按弱点自适应选题"，完整诊断引擎尚未实现。
- **HTML 作答回传导入**（`import_attempt.py`）：V2 已能生成 quiz.html，但学生作答后自动回传 attempt 尚未实现。
- **考后回传与校准**（`exam_feedback.py`）：用真实考试结果反向修正 next-best-step 权重。
- **跨课程学习指纹**（`learning-fingerprint.json`）：跨课程稳定的行为模式。
- **冲刺矩阵**（`sprint-policy.md`）：剩余时间 × 准备度的考前冲刺调度（现为占位）。
- **学科 profile 向量校正**：V1 用混合向量，按学科自适应校正尚未实现（`references/profiles/` 占位）。

### 工程硬化（V1.1 延期项，非阻塞）
- 已解决的错因复发重新激活；证据 / 卡片按解析时间排序（防混合时区）；`build_questions` 防御性拷贝；`kc_updated` 的 exam_weight `float()` 强转；空 `kc_ids` / 未知 `error_id` 校验；无锁读路径的读时写竞争。

### 非目标（规格明确）
- 多用户、云同步、GUI。

## License
MIT
