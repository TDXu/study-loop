# CLAUDE.md — study-loop 项目说明（给 Claude 的工作指南）

> 本文件是 study-loop 仓库的「工作指南」。每次在本仓库工作时先读它。
> 用户手册见 `docs/USAGE.md`，主 Agent 路由见 `SKILL.md`，交付说明见 `docs/DELIVERY-REPORT.md`。

## 这是什么

study-loop 是一个**本地优先、事件溯源**的持续学习 Agent（Claude Code Skill），面向大学课程。
核心：不只追踪「会不会」，还追踪「为什么错、什么条件下错、能否迁移、依赖多少提示、多久会忘、下一步最该学什么」。
当前主要实战课程：**毛中特**（文科、选择题密集）。

## 变更纪律（重要）

**每次修改代码或新增功能后，必须在 `CHANGELOG.md` 顶部 `[Unreleased]` 下追加一条记录**：
日期 + 类型（`feat`/`fix`/`refactor`/`docs`/`chore`）+ 一句话摘要 + 涉及文件/命令 + 对应 commit 短哈希。
功能交付后，把对应条目从 `[Unreleased]` 归入带日期版本号的小节。**不要跳过这一步。**

## 架构铁律（不可违反）

1. **事件溯源**：`events.jsonl` 是唯一真相源。`.study/` 下的 `state.json` 只是快照。
   → 任何状态写入都只走 `scripts/` 下的 CLI（写事件），**绝不直接编辑 `.study/` 下的 JSON/JSONL**。
2. **听懂 ≠ 掌握**：知识点升级到 `checked`/`confirmed` 由脚本规则执行，**不得口头宣布掌握**。
3. **AI 出题四道闸门**：Generator → 盲解 Solver → 对抗 Reviewer → 机械验证，过 `validate_question.py` 才入库。
4. **原题优先**：真题/课后题优先于 AI 生成题，且必须进 FSRS。
5. **规则可升级**：改规则后用 `derive_state.py` 重算或 `rebuild.py --dry-run` 核对差异。

## 目录速查

| 路径 | 作用 |
|---|---|
| `SKILL.md` | 主 Agent 路由表（意图 → 动作） |
| `references/` | 完整规则文档（架构/证据图/FSRS/迁移阶梯/错因记忆/出题校验…） |
| `agents/` | 出题三卡：`question-generator.md` / `independent-solver.md` / `adversarial-reviewer.md` |
| `scripts/` | CLI 入口（`event.py` `next_step.py` `fsrs.py` `validate_question.py` …） |
| `scripts/studylib/` | 核心库（`schemas.py` 数据模型 / `derive.py` 派生 / `registry.py` KC/题注册表 / `validation.py` 闸门 / `nextstep.py` 推荐 / `fsrs_store.py` 间隔重复 …） |
| `templates/` | dashboard 等 Jinja 模板 |
| `tests/` | 全量 pytest 测试 |
| `tmp/` | 工作草稿（OCR/字体/候选题 JSON），**已 gitignore，不入库** |

## 关键数据模型（见 `scripts/studylib/schemas.py`）

- **KC（知识点）**：`kc_id`（英文 slug，如 `mao_living_soul`）+ `name`（中文，如「毛泽东思想活的灵魂」）+ `chapter_id` + `prerequisites` + `exam_weight` + `explained`。
- **Question**：`question_id` / `kc_ids` / `source_type` / `transfer_level`(T0–T4) / `stem` / `answer` / `solution` / `difficulty` / `estimated_minutes` / `validation`（四闸门块）。
- 选择题答案存在 `stem`（含 `A.xxx\nB.xxx`）+ `answer`（如 `ABC`）+ `solution`（解析）。

## 常用命令

```bash
# 测试
python3 -m pytest                      # 或 python3 -m pytest tests/test_xxx.py

# 课程工作区操作（在工作区目录下，自动识别）
python3 scripts/next_step.py           # 今天最该做什么 + 为什么
python3 scripts/render_dashboard.py    # 状态页
python3 scripts/derive_state.py        # 重算状态
python3 scripts/rebuild.py --dry-run   # 全量重建预演
```

## 正在推进的功能（V1→V2）

详见 `CHANGELOG.md` 的 `[Unreleased]` 与 `docs/superpowers/specs/`。当前轮次目标：
1. KC 名称中英对照显示。
2. 学习模式选择（考纲直出+复盘 / 诊断先行+针对性）+ 可选题数。
3. 选择题输出形态（本地网页可点击测验 / PDF 试卷）+ 「点击显示解析」开关。
