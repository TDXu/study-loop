# 来源可追溯（Provenance）

必须有来源的对象：KC、知识骨架、笔记、题目、标准答案、真题权重、考试风格、AI 生成题、AI 推导结论。

来源类型：syllabus / textbook / lecture_slide / course_note / homework / past_exam /
teacher_emphasis / student_input / synthetic / external_reference。

## 登记方式
- 材料落地 materials/ 后：`event.py source-add --source-id src_012 --source-type lecture_slide --file materials/slides/chapter6.pdf --section "6.2 反馈类型"`。
- KC 注册时用 `--source-id` 关联来源。
- 真实题目注册：candidate JSON 里写 source_type（past_exam/homework/...）和 source_id。
- AI 生成题：derived_from 必须列出 ["kc:..", "error:..", "question:.."]。

## 必须支持的解释
学生问"为什么让我做这道题"，Agent 用 derived_from + 错因记录回答，例如：
"因为它针对你在 2023 年真题第 17 题暴露的『输出采样判断错误』生成，属于 T2 结构迁移，用于验证你不是只记住了原题。"
