# study-loop 使用手册

> 面向学生的日常操作指南。开发者文档见 `docs/DELIVERY-REPORT.md`，主 Agent 规则见 `SKILL.md`。
>
> 一句话：study-loop 是一个**记得你为什么会错、什么时候会忘、下一步该学什么**的学习助手。它不会因为你"听懂了"就当你掌握了——你得真正独立做对，它才认。

---

## 0. 先理解三件事

1. **听懂 ≠ 掌握。** 你说"懂了"不会让任何知识点升级。只有独立做对（且没靠提示）才算数。
2. **它会算账。** 每次你做题，它都重算状态，并告诉你**今天最该干什么、为什么**。照着做就行，不用自己想计划。
3. **错题不会被原谅。** 答错会进"错因记忆"，必须**原题重做对 + 迁移题做对**才算修复。光看一遍答案不算。

---

## 1. 安装

```bash
# 需要 Python 3.11+ 和 Claude Code
cd study-loop
python3 -m pip install -r requirements.txt
```

把 study-loop 装成 Claude Code skill（复制或软链到 skills 目录）：

```bash
ln -s "$(pwd)" ~/.claude/skills/study-loop
```

之后在任意课程目录里对 Claude 说 `/study`，它就会按本手册工作。

---

## 2. 第一次用：初始化一门课

挑一个空目录代表这门课：

```bash
python3 scripts/init_course.py ~/courses/模电 \
  --course-id analog-electronics \
  --name 模拟电子技术 \
  --exam-date 2026-07-25
cd ~/courses/模电
```

这会建好工作区：

```text
~/courses/模电/
├── course.yaml          # 课程元信息（id/名称/考试日/profile）
├── materials/           # 放你的课件/教材/真题（syllabus/slides/past-exams 等子目录）
├── notes/               # 你的笔记
├── output/              # 生成的冲刺包/模拟卷放这
└── .study/              # 系统状态（别手动改）
    ├── events.jsonl     # 学习历史（真相源）
    ├── state.json       # 当前快照
    ├── dashboard.md     # 给你看的状态页
    └── ...
```

> **V1 提醒**：自动从课件抽知识点（ingest）还没做。初始化后，让 Claude 帮你把课件/考纲读一遍，按第 3 节注册知识骨架。

---

## 3. 日常入口：`/study`

任何时候在该课程目录里说 `/study`（或直接说"继续学习"），系统会：

1. 读你的状态、错题、到期复习卡
2. 算出**今天最值得做的一件事**
3. 用一两句话告诉你做什么、为什么，然后直接开始

你不用记命令、不用选菜单。**意图不明时它最多问你一次**（预习？诊断？修复错题？刷题？复习？冲刺？）。

---

## 4. 学习闭环五步（完整流程）

### 第 1 步：搭知识骨架（每门课做一次）

把课程拆成"知识点（KC）"。考纲有的优先按考纲，标上考试权重：

```bash
python3 scripts/event.py kc-add \
  --kc-id feedback_topology \
  --name "反馈组态判断" \
  --chapter ch6 \
  --exam-weight 0.9          # 越重要权重越高，影响推荐优先级
```

有前置依赖就标出来（系统会据此判断"blocked"）：

```bash
python3 scripts/event.py kc-add --kc-id deep_neg_feedback \
  --name "深度负反馈计算" --prereq feedback_topology --exam-weight 0.7
```

> 让 Claude 读你的课件/考纲帮你批量建骨架，你确认一遍即可。

### 第 2 步：做题（核心环节）

每道题，系统会先问你有几成把握，**老实回答**——这是用来抓"以为会了"的：

| 你的回答 | 记录的置信度 |
|---|---|
| 猜的 | 0.25 |
| 不太确定 | 0.50 |
| 比较确定 | 0.75 |
| 非常确定 | 1.00 |

然后作答，用命令记录（或直接对 Claude 说，让它替你记）：

```bash
python3 scripts/event.py attempt \
  --question-id past_2023_q17 \
  --wrong \                  # --correct / --wrong 二选一
  --confidence 0.9 \         # 答题前置信度
  --time-sec 78              # 用时（可选）
```

**作答后系统自动重算状态并打印 next-best-step**——你会立刻看到"接下来建议做什么、为什么"。

### 第 3 步：答错 → 三步归因 + 修复

答错不会就这么过去。系统要求**三步归因**（错误假设 / 缺失前提 / 错因类型）：

```bash
python3 scripts/event.py misconception \
  --error-id err_001 \
  --kc feedback_topology \
  --question past_2023_q17 \
  --wrong-assumption "以为输出端有反馈连接就是电压反馈" \
  --missing-premise "得检查反馈网络对输出端的取样方式" \
  --error-type concept_misconception \
  --trigger "复杂电路图" \
  --confidence-before 0.9 \
  --attribution-confidence 0.82
```

> 让 Claude 帮你做归因对话，最后由它填这条命令。`error-type` 见下表。

**错因类型**（别滥用 `careless_error`）：
`concept_misconception`（概念误解）/ `prerequisite_gap`（前置缺失）/ `condition_misread`（条件看错）/ `procedure_omission`（步骤遗漏）/ `formula_misuse`（公式误用）/ `representation_failure`（表征失败）/ `transfer_failure`（迁移失败）/ `similar_concept_confusion`（易混概念）/ `calculation_slip`（计算失误）/ `memory_failure` / `strategy_failure` / `time_pressure_failure` / `careless_error` / `unknown`

然后修复（系统按错因选策略，比如概念误解用 Socratic 追问，步骤遗漏直接讲）：

```bash
python3 scripts/event.py repair-start --error-id err_001 --repair-id repair_001
# ... 这里有 Claude 带你修复的过程 ...
python3 scripts/event.py repair-done  --error-id err_001
```

### 第 4 步：双轨重测（修复不算完）

修复后必须**过两关**才算这个错因真正解决：

- **A 轨：原题二刷**（同一道真题/课后题重做）
- **B 轨：迁移题**（同知识点、换个问法/结构的题，验证你不是背了这道题）

```bash
# A 轨：原题做对
python3 scripts/event.py attempt --question-id past_2023_q17 \
  --correct --confidence 0.8 --transfer --retest-of err_001

# B 轨：迁移题做对（迁移题要先注册，见第 6 节）
python3 scripts/event.py attempt --question-id syn_t1 \
  --correct --confidence 0.75 --transfer --retest-of err_001
```

> 规则：**T0 原题通过 + (T1 或 T2) 迁移通过 → 错因解决。** 任一关失败，错因重新激活。

### 第 5 步：进 FSRS 长期复习

重要的题（尤其真题、课后题）要进间隔重复，防遗忘：

```bash
# 建卡片（card-type：original_question / transfer_question / concept_recall 等）
python3 scripts/fsrs.py create-card \
  --card-type original_question \
  --kc feedback_topology \
  --question-id past_2023_q17

# 看今天有哪些到期
python3 scripts/fsrs.py due

# 做完一张卡，按 1-4 评分（1 完全忘了 → 4 轻松）
python3 scripts/fsrs.py review --card-id card_xxx --rating 3
```

评分参考：
- `1` 又忘了 / 答错
- `2` 答对但很吃力、不太确定（置信度 < 0.75）
- `3` 正常答对
- `4` 轻松秒杀

---

## 5. 提示阶梯（做题卡住时）

做题时如果卡住，可以请求提示。系统记录你用了几级提示——**用高级提示做对的题不算独立掌握**：

| 级别 | 含义 |
|---|---|
| L0 | 独立作答（不请求提示） |
| L1 | 元认知追问（"你判断的依据是什么？"） |
| L2 | 方向提示（"先看这里取样的是哪个量"） |
| L3 | 局部脚手架（"暂时忽略 R3，只看输出端"） |
| L4 | 半步演示（AI 做关键一步，你接着做） |
| L5 | 完整讲解 |

```bash
python3 scripts/event.py attempt --question-id q1 --correct \
  --confidence 0.7 --hint-level 3     # 用了 L3 提示
```

> L4/L5 下答对只算 `practiced`，**不会**升级到 `checked`。要真掌握，得在不靠提示时独立做对。

---

## 6. AI 出迁移题（修复用）

当真题不够、需要同知识点的变式题来验证迁移时，可以让 Claude 按 `agents/` 三卡流程出题，过四道闸门后入库：

```bash
# 候选题 JSON（含题面/答案/迁移层级/验证块），Claude 帮你生成
python3 scripts/validate_question.py /tmp/candidate.json --as-transfer-test
```

**闸门**：出题器 → 独立求解者（盲解，答案一致）→ 对抗审查者（查超纲/歧义/换数字冒充结构迁移）→ 机械验证（数学用 SymPy，可选）。任一关不过，题不存在。

> 硬规则：**T2 及以上的迁移题，必须改 `surface_context`（换数字/换背景）以外的维度**，否则拒绝。光换数字不算结构迁移。

---

## 7. 看状态

随时查看你的学习全貌：

```bash
# 推荐页（今天做什么、为什么、风险、掌握证据、到期复习）
python3 scripts/render_dashboard.py
# 或直接读生成的文件
cat .study/dashboard.md

# 今天的下一步建议（/study 的核心）
python3 scripts/next_step.py

# 错因表（哪些错因还没解决、复发几次）
python3 scripts/misconception.py

# 单个知识点的所有证据
python3 scripts/evidence.py --kc feedback_topology
```

**掌握证据会显示六态分布**：
- `confirmed` 真掌握了（保持 + 迁移都过）
- `checked` 基础独立验证过
- `practiced` 练过但证据不足（含靠提示做对的）
- `explained` 讲过但没独立证据
- `weak` 近期错 / 高置信度盲区 / 迁移失败
- `blocked` 前置没稳，当前学不动
- `unseen` 还没碰

---

## 8. 状态出问题了？

```bash
# 先重算（最常见，事件多了快照没跟上）
python3 scripts/derive_state.py

# 还可疑：从事件全量重建（先 dry-run 看差异，确认后再真跑）
python3 scripts/rebuild.py --dry-run
python3 scripts/rebuild.py
```

> 原理：`events.jsonl` 是真相，state.json 只是快照。重建永远可信——这也是为什么**别手动改 `.study/` 下的 JSON**。

---

## 9. 典型一天

```text
1. cd ~/courses/模电 && /study
   → 系统："今天先修「反馈组态判断」，你昨天高置信度答错了，12 分钟。"
2. 跟着 Claude 做归因 + Socratic 修复
3. 原题二刷 → 对；迁移题 → 对 → 错因解决 ✅
4. 系统："2 张卡到期，先复习。" → 做完评分
5. 系统："剩下时间推进「深度负反馈」，它是反馈组态的下一步。"
```

整个过程你只管学和答，计划、修复、复习节奏都由系统算好并解释给你。

---

## 10. 还没有的功能（V1）

这些规格里规划了但 V1 还没做，遇到请手工绕过：

- **自动读课件抽知识点**：V1 要你/Claude 手工建骨架。
- **自适应诊断**（自动出诊断卷）：V1 靠手工或对话做题。
- **HTML 测验页 / 模拟卷**：V1 没有交互式网页。
- **考前冲刺矩阵**（按剩余时间×准备度）：V1 用 next-best-step 顶替。
- **考后回传**（拿真实成绩校准系统）：V1 没做。

详见 `docs/DELIVERY-REPORT.md` 第 9 节。

---

## 命令速查

| 场景 | 命令 |
|---|---|
| 初始化课程 | `python3 scripts/init_course.py <目录> --course-id .. --name .. [--exam-date ..]` |
| 加知识点 | `python3 scripts/event.py kc-add --kc-id .. --name .. [--chapter ..] [--prereq ..] [--exam-weight ..]` |
| 标记已讲解 | `python3 scripts/event.py kc-explained --kc-id ..` |
| 登记来源 | `python3 scripts/event.py source-add ...` |
| 作答 | `python3 scripts/event.py attempt --question-id .. --correct\|--wrong [--confidence ..] [--hint-level ..] [--transfer] [--retest-of ..]` |
| 记错因 | `python3 scripts/event.py misconception --kc .. --wrong-assumption .. --missing-premise .. --error-type .. [--error-id ..]` |
| 修复 | `python3 scripts/event.py repair-start --error-id .. --repair-id ..` → `repair-done --error-id ..` |
| 出迁移题 | `python3 scripts/validate_question.py <题.json> --as-transfer-test` |
| 建复习卡 | `python3 scripts/fsrs.py create-card --card-type .. --kc .. [--question-id ..]` |
| 到期卡 | `python3 scripts/fsrs.py due` |
| 评分复习 | `python3 scripts/fsrs.py review --card-id .. --rating 1..4` |
| 今天做什么 | `python3 scripts/next_step.py` |
| 看状态 | `python3 scripts/render_dashboard.py` |
| 看错因 | `python3 scripts/misconception.py` |
| 看某点证据 | `python3 scripts/evidence.py --kc ..` |
| 重算 | `python3 scripts/derive_state.py` |
| 重建 | `python3 scripts/rebuild.py [--dry-run]` |

> 所有命令都支持 `--course <路径>` 指定课程目录（默认自动识别当前目录所在课程）。
> 出错时会打印一行人话提示并退出码 1，不会甩原始报错堆栈。
