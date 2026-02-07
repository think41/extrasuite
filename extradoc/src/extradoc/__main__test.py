from __future__ import annotations

import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

REVISION_RE = re.compile(r'\srevision="[^"]*"')


def _run(cmd: list[str], **kwargs: Any) -> None:
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def _parse_doc_id(document_xml: Path) -> str:
    root = ET.parse(document_xml).getroot()
    doc_id = root.get("id")
    if not doc_id:
        raise SystemExit("document.xml missing id attribute")
    return doc_id


def _normalize(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    text = REVISION_RE.sub("", text)
    return [ln.rstrip() for ln in text.splitlines()]


def run_test_workflow(folder: Path) -> int:
    folder = folder.expanduser().resolve()
    document_xml = folder / "document.xml"
    if not document_xml.exists():
        print(f"missing document.xml at {document_xml}", file=sys.stderr)
        return 1

    doc_id = _parse_doc_id(document_xml)
    diff_path = folder / "diff.json"
    after_dir = folder.parent / f"{folder.name}-after"

    print(f"[1/4] diff -> {diff_path}")
    with diff_path.open("w", encoding="utf-8") as f:
        _run(["uv", "run", "python", "-m", "extradoc", "diff", str(folder)], stdout=f)

    print("[2/4] push")
    _run(["uv", "run", "python", "-m", "extradoc", "push", str(folder)])

    print(f"[3/4] pull -> {after_dir}")
    _run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "extradoc",
            "pull",
            f"https://docs.google.com/document/d/{doc_id}/edit",
            str(after_dir),
        ]
    )

    print("[4/4] compare")
    expected = document_xml
    repulled_root = after_dir / doc_id
    actual = (
        repulled_root / "document.xml"
        if repulled_root.exists()
        else after_dir / "document.xml"
    )

    if not actual.exists():
        print(f"repulled document missing: {actual}", file=sys.stderr)
        return 1

    exp_lines = _normalize(expected)
    act_lines = _normalize(actual)

    if exp_lines == act_lines:
        print("SUCCESS: repull matches edited document (ignoring revision).")
        print(f"diff.json: {diff_path}")
        print(f"expected:  {expected}")
        print(f"actual:    {actual}")
        return 0

    import difflib

    diff = "\n".join(
        difflib.unified_diff(
            exp_lines,
            act_lines,
            fromfile=str(expected),
            tofile=str(actual),
            lineterm="",
        )
    )
    print("MISMATCH: repull differs from edited version.")
    print(f"diff.json: {diff_path}")
    print(f"expected:  {expected}")
    print(f"actual:    {actual}")
    print("Diff (revision stripped):")
    print(diff)
    return 1
