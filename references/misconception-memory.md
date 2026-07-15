# Misconception Memory（错因长期记忆）

errors.jsonl 的建模单位是 KC × 错因 × 触发条件，不是题目 × 对错。同一 KC 同一错因再次出现 → recurrence_count 累加、触发条件并集。

## 三步归因（每个高价值错误必做）
1. 错误假设是什么？（学生当时依据的错误规则）
2. 缺失了哪个前提？（正确做法需要但学生没用上的条件）
3. 属于哪种误解类型？（下方 14 类之一；禁止大量归为 careless_error）

concept_misconception / prerequisite_gap / condition_misread / procedure_omission /
formula_misuse / representation_failure / transfer_failure / similar_concept_confusion /
calculation_slip / memory_failure / strategy_failure / time_pressure_failure /
careless_error / unknown

## 错因 → 修复策略（§24.3）
| 错因 | 默认策略 |
|---|---|
| concept_misconception | Socratic 追问（引导学生自己发现矛盾） |
| prerequisite_gap | 回退前置 KC 再回来 |
| procedure_omission | 直接指出遗漏步骤 |
| condition_misread | 条件对比训练 |
| similar_concept_confusion | 辨析矩阵（并排对比两个概念的适用条件） |
| formula_misuse | 公式适用边界检查 |
| representation_failure | 换表征（图↔式↔文字） |
| transfer_failure | 沿迁移阶梯降级重建 |
| calculation_slip | 最小纠正，不小题大做 |
| memory_failure | 交给 FSRS |
| 高置信度错误 | 无论何种类型，优先深修 |

## 修复生命周期
active →（repair-start）repairing →（repair-done）retest_pending →（原题二刷通过 且 T1/T2 任一通过）resolved。
重测任何一次失败 → 打回 active。双轨重测缺一不可：原题二刷验证"这道题会了"，迁移题验证"这个知识点会了"。
