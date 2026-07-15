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
