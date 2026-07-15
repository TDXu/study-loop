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
