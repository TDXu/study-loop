# AI 出题质量闸门

流程：Generator → Independent Solver → Adversarial Reviewer →（适用时）Mechanical Validator → `validate_question.py` 入库。四道闸门缺一不可，`validate_question.py` 是最终裁判。

## 各闸门职责
- Gate 1 Generator（agents/question-generator.md）：产出题面、标准答案、解题思路、迁移等级、改变/保持维度、目标认知陷阱。
- Gate 2 Independent Solver（agents/independent-solver.md）：**只看题面**盲解，检查可解性、条件充分性、唯一解、与 Generator 答案一致（answer_match）。
- Gate 3 Adversarial Reviewer（agents/adversarial-reviewer.md）：专门找茬——超纲？歧义？只是换数字？意外捷径？真的考目标 KC？迁移层级虚标？
- Gate 4 Mechanical Validator（适用时）：数学 SymPy 验算 / 编程执行测试 / 选择题唯一答案检查 / 数值回代。V1 由 Agent 在会话内用工具执行并把结果写进 validation 块。

## 入库硬标准（validate_question.py 强制）
有目标 KC（已注册）、有 derived_from 来源链、有迁移层级、有标准答案、solver answer_match=true、reviewer passed、机械验证（若做了）passed、T2+ 的 changed_dimensions 必须含 surface_context 以外的维度。

## 组装示例
Agent 跑完三卡后组装 candidate JSON（validation 块记录各 gate 结论），然后：
python3 scripts/validate_question.py cand.json --as-transfer-test
未过闸门会得到逐条问题清单；修复后重试，不许绕过。
