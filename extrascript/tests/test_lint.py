"""Tests for the lint rules."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from extrascript.linter import Severity, lint_project


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a minimal valid project directory."""
    d = tmp_path / "proj"
    d.mkdir()
    manifest = {
        "timeZone": "America/New_York",
        "runtimeVersion": "V8",
        "exceptionLogging": "CLOUD",
    }
    (d / "appsscript.json").write_text(json.dumps(manifest))
    return d


def test_lint_clean_project(project_dir: Path) -> None:
    """A valid project with clean code should produce no diagnostics."""
    (project_dir / "Code.gs").write_text(
        "function hello() {\n  const msg = 'hello';\n  Logger.log(msg);\n}\n"
    )
    result = lint_project(project_dir)
    assert not result.has_errors
    assert result.warning_count == 0


def test_lint_missing_manifest(tmp_path: Path) -> None:
    """Missing appsscript.json should be an error."""
    d = tmp_path / "proj"
    d.mkdir()
    (d / "Code.gs").write_text("function foo() {}\n")

    result = lint_project(d)
    assert result.has_errors
    rules = [d.rule for d in result.diagnostics]
    assert "manifest-missing" in rules


def test_lint_invalid_manifest_json(project_dir: Path) -> None:
    """Invalid JSON in manifest should be an error."""
    (project_dir / "appsscript.json").write_text("{ invalid json")

    result = lint_project(project_dir)
    assert result.has_errors
    rules = [d.rule for d in result.diagnostics]
    assert "manifest-invalid-json" in rules


def test_lint_manifest_not_v8(project_dir: Path) -> None:
    """Non-V8 runtime should be a warning."""
    (project_dir / "appsscript.json").write_text(
        json.dumps({"timeZone": "UTC", "runtimeVersion": "DEPRECATED_ES5"})
    )

    result = lint_project(project_dir)
    warnings = [d for d in result.diagnostics if d.severity == Severity.WARNING]
    rules = [d.rule for d in warnings]
    assert "manifest-not-v8" in rules


def test_lint_no_var(project_dir: Path) -> None:
    """Using 'var' should produce a warning."""
    (project_dir / "Code.gs").write_text(
        "function foo() {\n  var x = 1;\n  return x;\n}\n"
    )

    result = lint_project(project_dir)
    rules = [d.rule for d in result.diagnostics]
    assert "no-var" in rules


def test_lint_strict_equality(project_dir: Path) -> None:
    """Using == instead of === should produce a warning."""
    (project_dir / "Code.gs").write_text(
        "function foo(x) {\n  if (x == null) {\n    return 0;\n  }\n}\n"
    )

    result = lint_project(project_dir)
    rules = [d.rule for d in result.diagnostics]
    assert "strict-equality" in rules


def test_lint_no_hardcoded_secrets(project_dir: Path) -> None:
    """Hardcoded secrets should be an error."""
    (project_dir / "Code.gs").write_text(
        "const API_KEY = 'AIzaSyD-abcdefghij1234567890ABCDEFGH_XY';\n"
    )

    result = lint_project(project_dir)
    assert result.has_errors
    rules = [d.rule for d in result.diagnostics]
    assert "no-hardcoded-secrets" in rules


def test_lint_empty_catch(project_dir: Path) -> None:
    """Empty catch blocks should be a warning."""
    (project_dir / "Code.gs").write_text(
        "function foo() {\n  try {\n    doSomething();\n  } catch (e) {}\n}\n"
    )

    result = lint_project(project_dir)
    rules = [d.rule for d in result.diagnostics]
    assert "no-empty-catch" in rules


def test_lint_function_too_long(project_dir: Path) -> None:
    """Functions longer than 50 lines should get an info diagnostic."""
    lines = ["function longFunc() {"]
    for i in range(55):
        lines.append(f"  const x{i} = {i};")
    lines.append("}")
    (project_dir / "Code.gs").write_text("\n".join(lines) + "\n")

    result = lint_project(project_dir)
    rules = [d.rule for d in result.diagnostics]
    assert "function-too-long" in rules


def test_lint_html_secrets(project_dir: Path) -> None:
    """Hardcoded secrets in HTML files should be detected."""
    (project_dir / "Page.html").write_text(
        '<script>const key = "AIzaSyD-abcdefghij1234567890ABCDEFGH_XY";</script>\n'
    )

    result = lint_project(project_dir)
    assert result.has_errors
    rules = [d.rule for d in result.diagnostics]
    assert "no-hardcoded-secrets" in rules


def test_lint_password_detection(project_dir: Path) -> None:
    """Hardcoded passwords should be detected."""
    (project_dir / "Code.gs").write_text("const password = 'mysecretpassword';\n")

    result = lint_project(project_dir)
    assert result.has_errors


def test_lint_strict_equality_not_in_string(project_dir: Path) -> None:
    """== inside a string literal should not trigger the rule."""
    (project_dir / "Code.gs").write_text("const msg = 'a == b';\n")

    result = lint_project(project_dir)
    rules = [d.rule for d in result.diagnostics]
    assert "strict-equality" not in rules
