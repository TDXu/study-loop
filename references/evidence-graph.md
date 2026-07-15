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
