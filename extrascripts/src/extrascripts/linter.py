"""Lint rules for Google Apps Script code.

Catches common mistakes in Apps Script projects before pushing to Google.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class Diagnostic:
    """A single lint finding."""

    rule: str
    message: str
    severity: Severity
    file: str
    line: int = 0  # 0 means file-level

    def __str__(self) -> str:
        loc = f"{self.file}:{self.line}" if self.line else self.file
        return f"{loc}: {self.severity.value}: [{self.rule}] {self.message}"


@dataclass
class LintResult:
    """Aggregated lint results for a project."""

    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for d in self.diagnostics if d.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for d in self.diagnostics if d.severity == Severity.WARNING)

    @property
    def has_errors(self) -> bool:
        return self.error_count > 0

    def add(self, diagnostic: Diagnostic) -> None:
        self.diagnostics.append(diagnostic)


def lint_project(folder: Path) -> LintResult:
    """Run all lint rules on an Apps Script project folder.

    Args:
        folder: Path to the project folder (containing project.json).

    Returns:
        LintResult with all diagnostics.
    """
    result = LintResult()

    # Check manifest
    _lint_manifest(folder, result)

    # Check each .gs file
    for path in sorted(folder.iterdir()):
        if path.suffix == ".gs" and path.is_file():
            source = path.read_text()
            _lint_gs_file(path.name, source, result)

    # Check each .html file
    for path in sorted(folder.iterdir()):
        if path.suffix == ".html" and path.is_file():
            source = path.read_text()
            _lint_html_file(path.name, source, result)

    return result


# --- Manifest checks ---


def _lint_manifest(folder: Path, result: LintResult) -> None:
    """Validate the appsscript.json manifest."""
    manifest_path = folder / "appsscript.json"

    if not manifest_path.exists():
        result.add(
            Diagnostic(
                rule="manifest-missing",
                message="appsscript.json is required in every Apps Script project",
                severity=Severity.ERROR,
                file="appsscript.json",
            )
        )
        return

    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as e:
        result.add(
            Diagnostic(
                rule="manifest-invalid-json",
                message=f"appsscript.json is not valid JSON: {e}",
                severity=Severity.ERROR,
                file="appsscript.json",
            )
        )
        return

    if not isinstance(manifest, dict):
        result.add(
            Diagnostic(
                rule="manifest-invalid-json",
                message="appsscript.json must be a JSON object",
                severity=Severity.ERROR,
                file="appsscript.json",
            )
        )
        return

    # Check timeZone
    if "timeZone" not in manifest:
        result.add(
            Diagnostic(
                rule="manifest-no-timezone",
                message="Missing 'timeZone' field (e.g. \"America/New_York\")",
                severity=Severity.WARNING,
                file="appsscript.json",
            )
        )

    # Check runtimeVersion
    runtime = manifest.get("runtimeVersion", "")
    if runtime != "V8":
        result.add(
            Diagnostic(
                rule="manifest-not-v8",
                message=f"runtimeVersion is '{runtime}' - V8 is recommended "
                "for modern JavaScript support (const/let, arrow functions, etc.)",
                severity=Severity.WARNING,
                file="appsscript.json",
            )
        )

    # Validate oauthScopes is a list if present
    scopes = manifest.get("oauthScopes")
    if scopes is not None and not isinstance(scopes, list):
        result.add(
            Diagnostic(
                rule="manifest-invalid-scopes",
                message="'oauthScopes' must be an array of scope URL strings",
                severity=Severity.ERROR,
                file="appsscript.json",
            )
        )


# --- JavaScript (.gs) checks ---

# Regex patterns for lint rules
_VAR_PATTERN = re.compile(r"^\s*var\s+", re.MULTILINE)
_LOOSE_EQ_PATTERN = re.compile(r"(?<!=)[!=]=(?!=)")
_SECRET_PATTERNS = [
    re.compile(r"""['"]AIza[0-9A-Za-z_-]{35}['"]"""),  # Google API key
    re.compile(r"""['"]sk[-_][a-zA-Z0-9]{20,}['"]"""),  # Secret key pattern
    re.compile(r"""(?i)password\s*=\s*['"][^'"]+['"]"""),  # Hardcoded password
    re.compile(r"""(?i)api[_-]?key\s*=\s*['"][^'"]+['"]"""),  # API key assignment
    re.compile(r"""(?i)secret\s*=\s*['"][^'"]+['"]"""),  # Secret assignment
]
_EMPTY_CATCH_PATTERN = re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}", re.MULTILINE)
_FUNCTION_PATTERN = re.compile(r"^\s*function\s+\w+\s*\(", re.MULTILINE)


def _lint_gs_file(filename: str, source: str, result: LintResult) -> None:
    """Run lint rules on a .gs file."""
    lines = source.split("\n")

    for i, line in enumerate(lines, start=1):
        line_stripped = line.strip()

        # Skip comments
        if line_stripped.startswith("//") or line_stripped.startswith("/*"):
            continue

        # no-var: suggest const/let
        if _VAR_PATTERN.match(line):
            result.add(
                Diagnostic(
                    rule="no-var",
                    message="Use 'const' or 'let' instead of 'var' (V8 runtime)",
                    severity=Severity.WARNING,
                    file=filename,
                    line=i,
                )
            )

        # strict-equality: == or != (but not === or !==)
        if _LOOSE_EQ_PATTERN.search(line) and not _is_likely_in_string(
            line, _LOOSE_EQ_PATTERN
        ):
            result.add(
                Diagnostic(
                    rule="strict-equality",
                    message="Use '===' / '!==' instead of '==' / '!='",
                    severity=Severity.WARNING,
                    file=filename,
                    line=i,
                )
            )

        # no-hardcoded-secrets
        for pattern in _SECRET_PATTERNS:
            if pattern.search(line):
                result.add(
                    Diagnostic(
                        rule="no-hardcoded-secrets",
                        message="Possible hardcoded secret or API key. "
                        "Use PropertiesService.getScriptProperties() instead.",
                        severity=Severity.ERROR,
                        file=filename,
                        line=i,
                    )
                )
                break  # One finding per line is enough

    # empty-catch: catch blocks with no body
    for match in _EMPTY_CATCH_PATTERN.finditer(source):
        line_num = source[: match.start()].count("\n") + 1
        result.add(
            Diagnostic(
                rule="no-empty-catch",
                message="Empty catch block silences errors. "
                "Log or handle the error, or add a comment explaining why.",
                severity=Severity.WARNING,
                file=filename,
                line=line_num,
            )
        )

    # function-length: functions longer than 50 lines
    _check_function_length(filename, source, result)


def _lint_html_file(filename: str, source: str, result: LintResult) -> None:
    """Run lint rules on an .html file."""
    lines = source.split("\n")

    for i, line in enumerate(lines, start=1):
        # Check for hardcoded secrets in HTML too
        for pattern in _SECRET_PATTERNS:
            if pattern.search(line):
                result.add(
                    Diagnostic(
                        rule="no-hardcoded-secrets",
                        message="Possible hardcoded secret or API key in HTML template.",
                        severity=Severity.ERROR,
                        file=filename,
                        line=i,
                    )
                )
                break


def _check_function_length(filename: str, source: str, result: LintResult) -> None:
    """Warn about functions longer than 50 lines."""
    lines = source.split("\n")
    max_lines = 50

    i = 0
    while i < len(lines):
        match = _FUNCTION_PATTERN.match(lines[i])
        if match:
            func_start = i
            # Find matching closing brace (simple brace counting)
            brace_count = 0
            found_open = False
            j = i
            while j < len(lines):
                for ch in lines[j]:
                    if ch == "{":
                        brace_count += 1
                        found_open = True
                    elif ch == "}":
                        brace_count -= 1
                if found_open and brace_count == 0:
                    func_length = j - func_start + 1
                    if func_length > max_lines:
                        # Extract function name
                        name_match = re.search(r"function\s+(\w+)", lines[func_start])
                        func_name = name_match.group(1) if name_match else "anonymous"
                        result.add(
                            Diagnostic(
                                rule="function-too-long",
                                message=f"Function '{func_name}' is {func_length} lines "
                                f"(max {max_lines}). Consider splitting it.",
                                severity=Severity.INFO,
                                file=filename,
                                line=func_start + 1,
                            )
                        )
                    break
                j += 1
        i += 1


def _is_likely_in_string(line: str, pattern: re.Pattern[str]) -> bool:
    """Rough heuristic: check if the pattern match is inside a string literal.

    This is a best-effort check, not a full parser.
    """
    match = pattern.search(line)
    if not match:
        return False

    pos = match.start()
    # Count unescaped quotes before the match position
    in_single = False
    in_double = False
    i = 0
    while i < pos:
        ch = line[i]
        if ch == "\\" and i + 1 < len(line):
            i += 2  # skip escaped char
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        i += 1

    return in_single or in_double
