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
