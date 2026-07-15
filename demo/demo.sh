#!/usr/bin/env bash
# study-loop V1 最小闭环端到端演示（spec §50）
set -euo pipefail
SKILL="$(cd "$(dirname "$0")/.." && pwd)"
DEMO="$(mktemp -d)/模拟电子技术"
export STUDY_LOOP_HOME="$(mktemp -d)/study-home"

py() { python3 "$SKILL/scripts/$1" "${@:2}"; }

echo "== 1. 初始化课程 =="
py init_course.py "$DEMO" --course-id analog --name 模拟电子技术 --exam-date 2026-07-25
cd "$DEMO"

echo "== 2. 注册 KC 骨架（考纲优先）=="
py event.py kc-add --kc-id feedback_topology --name 反馈组态判断 --chapter ch6 --exam-weight 0.9
py event.py kc-add --kc-id deep_negative_feedback --name 深度负反馈 --chapter ch6 \
  --prereq feedback_topology --exam-weight 0.8

echo "== 3. 注册真题 =="
cat > q17.json << 'EOF'
{"question_id": "past_2023_q17", "kc_ids": ["feedback_topology"],
 "source_type": "past_exam", "transfer_level": "T0",
 "stem": "判断该电路的反馈组态", "answer": "A"}
EOF
py validate_question.py q17.json

echo "== 4. 高置信度答错 =="
py event.py attempt --question-id past_2023_q17 --wrong --confidence 0.9

echo "== 5. 三步归因入库 =="
py event.py misconception --error-id err_001 --kc feedback_topology --question past_2023_q17 \
  --wrong-assumption "输出端有反馈连接即电压反馈" --missing-premise "必须检查取样方式" \
  --error-type concept_misconception --trigger 复杂电路图 --confidence-before 0.9

echo "== 6. 修复 + 原题二刷 =="
py event.py repair-start --error-id err_001 --repair-id repair_012
py event.py repair-done --error-id err_001
py event.py attempt --question-id past_2023_q17 --correct --confidence 0.75 --retest-of err_001

echo "== 7. T1 迁移题（过四道闸门）+ 重测 =="
cat > t1.json << 'EOF'
{"question_id": "syn_t1_001", "kc_ids": ["feedback_topology"],
 "source_type": "synthetic", "transfer_level": "T1",
 "stem": "同结构换参数题", "answer": "C",
 "changed_dimensions": ["surface_context"],
 "preserved_dimensions": ["core_kc", "target_capability", "cognitive_trap"],
 "derived_from": ["kc:feedback_topology", "error:err_001", "question:past_2023_q17"],
 "validation": {"generator": {"status": "passed"},
                "independent_solver": {"status": "passed", "answer_match": true},
                "adversarial_review": {"status": "passed", "issues": []}}}
EOF
py validate_question.py t1.json --as-transfer-test
py event.py attempt --question-id syn_t1_001 --correct --confidence 0.75 --transfer --retest-of err_001

echo "== 8. 原题进 FSRS =="
py fsrs.py create-card --card-type original_question --kc feedback_topology --question-id past_2023_q17
py fsrs.py due

echo "== 9. 次日视角：/study 推荐 =="
py next_step.py

echo "== 10. Dashboard =="
cat .study/dashboard.md
echo
echo "演示完成。工作区：$DEMO"
