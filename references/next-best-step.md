# next-best-step

V1 加权和（studylib/nextstep.py）：
P = w1·ExamWeight + w2·Urgency + w3·Weakness + w4·PrereqCentrality
  + w5·ForgettingRisk + w6·TransferGap + w7·BlindSpotRisk − w8·ExpectedTime
所有输入归一化 [0,1]；权重见 DEFAULT_WEIGHTS（weakness 1.5、blind_spot 1.2 最高——
高置信度错误优先修复是产品原则）。

候选动作：repair（weak/blocked）、drill（practiced/explained/checked 有迁移缺口）、
advance（unseen）、review（有到期卡）、rest（无事可做）。

## 输出纪律
不允许只报一个分数。推荐必须带 reasons（脚本已生成），Agent 照此解释，例如：
"建议先修复「反馈组态判断」，预计 12 分钟。原因：存在未修复错因（concept_misconception ×3）；
其中有高置信度错误；T2 结构迁移未通过；是 2 个后续知识点的前置；距考试 5 天。"
学生说"换一个"→ 解释次优候选；学生坚持自己的选择 → 尊重并照常记录事件。
