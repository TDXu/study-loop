# 贡献指南

感谢你愿意改进 `study-loop`。这个项目同时包含面向人的文档、Agent 路由规则和 Python CLI；提交修改前，请先确认你改的是哪一层。

## 开始开发

```bash
git clone https://github.com/monkeydyt/study-loop.git
cd study-loop
python3 -m venv .venv
source .venv/bin/activate       # Windows PowerShell: .venv\\Scripts\\Activate.ps1
python3 -m pip install -r requirements.txt
python3 -m pytest
```

为每项工作创建独立分支：

```bash
git switch -c docs/readme-improvement
```

推荐分支前缀：`docs/`、`feat/`、`fix/`、`test/`、`chore/`。

## 修改边界

- `README.md` / `README_EN.md`：面向新用户的项目入口。
- `SKILL.md` / `CLAUDE.md`：Agent 路由和项目工作纪律。
- `references/` / `agents/`：规则和子流程提示卡。
- `scripts/` / `scripts/studylib/`：确定性 CLI 和核心逻辑。
- `templates/`：Dashboard、测验等输出模板。
- `tests/`：行为契约和回归测试。

不要直接编辑课程工作区 `.study/` 下的 JSON/JSONL；状态写入必须通过 `scripts/` 下的 CLI。不要提交密钥、`.env`、临时 OCR 文件或个人课程数据。

## 提交前检查

```bash
python3 -m pytest
git diff --check
```

如果修改了文档，请同步更新 `CHANGELOG.md` 的 `[Unreleased]`。如果修改了用户可见能力，请同步 README 和对应使用手册。

## Pull Request

Pull Request 请说明：

1. 修改解决了什么问题。
2. 涉及哪些文件和用户行为。
3. 运行了哪些测试。
4. 是否有兼容性、数据迁移或文档影响。

小而单一的 PR 更容易审查。请不要把无关格式化、重命名和功能修改混在一起。
