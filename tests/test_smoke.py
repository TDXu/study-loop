def test_import_studylib():
    import studylib
    assert studylib.SCHEMA_VERSION == "2.0"


def test_deps_available():
    import pydantic, typer, fsrs, jinja2, filelock, yaml  # noqa: F401
