from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REFERENCES = [
    "architecture.md", "evidence-graph.md", "misconception-memory.md",
    "hint-ladder.md", "transfer-ladder.md", "question-validation.md",
    "provenance.md", "fsrs-policy.md", "next-best-step.md",
]
AGENTS = ["question-generator.md", "independent-solver.md", "adversarial-reviewer.md"]
SCRIPTS = [
    "init_course.py", "event.py", "derive_state.py", "fsrs.py", "next_step.py",
    "validate_question.py", "render_dashboard.py", "rebuild.py",
    "misconception.py", "evidence.py",
]


def test_skill_md_frontmatter_and_routing():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---")
    fm = text.split("---")[1]
    assert "name: study-loop" in fm
    assert "description:" in fm
    for s in SCRIPTS:
        assert s in text, f"SKILL.md 必须引用脚本 {s}"
    for r in REFERENCES:
        assert r in text, f"SKILL.md 必须引用 references/{r}"


def test_reference_and_agent_files_exist_nonempty():
    for r in REFERENCES:
        p = ROOT / "references" / r
        assert p.exists() and len(p.read_text(encoding="utf-8")) > 200, r
    for a in AGENTS:
        p = ROOT / "agents" / a
        assert p.exists() and len(p.read_text(encoding="utf-8")) > 200, a


def test_readme_has_quickstart():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "init_course.py" in text and "Quick" in text or "快速" in text
