#!/usr/bin/env python3
"""Replay captured ``reconcile_v2`` fixtures against live Google Docs.

This is a confidence-sprint harness, not production tooling. It recreates the
fixture base state on a fresh document, lowers ``reconcile_v2`` semantic edits,
applies them live, and checks that the resulting document semantically matches
the captured desired fixture.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

from extrasuite.client import CredentialsManager

from extradoc import GoogleDocsTransport
from extradoc.api_types._generated import Document
from extradoc.reconcile_v2.api import lower_semantic_diff, semantic_diff

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTRASUITE = REPO_ROOT / "extrasuite"
FIXTURES_ROOT = REPO_ROOT / "extradoc" / "tests" / "reconcile_v2" / "fixtures"


class RawDocsClient:
    def __init__(self) -> None:
        manager = CredentialsManager()
        self._cred = manager.get_credential(
            command={"type": "doc.push", "file_url": "", "file_name": ""},
            reason="Replaying reconcile_v2 confidence fixtures",
        )

    async def get_document_raw(self, document_id: str) -> dict:
        transport = GoogleDocsTransport(self._cred.token)
        try:
            return (await transport.get_document(document_id)).raw
        finally:
            await transport.close()

    async def batch_update(self, document_id: str, requests: list[dict]) -> dict:
        transport = GoogleDocsTransport(self._cred.token)
        try:
            return await transport.batch_update(document_id, requests)
        finally:
            await transport.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        action="append",
        dest="only",
        help="Replay only the named fixture. Repeat to select multiple.",
    )
    args = parser.parse_args()

    selected = set(args.only or [])
    fixture_names = [
        "text_replace",
        "paragraph_split",
        "table_cell_text_replace",
        "header_text_replace",
        "named_range_add",
    ]

    import asyncio

    client = RawDocsClient()
    for name in fixture_names:
        if selected and name not in selected:
            continue
        asyncio.run(_replay_fixture(name, client))


async def _replay_fixture(name: str, client: RawDocsClient) -> None:
    fixture_dir = FIXTURES_ROOT / name
    base_fixture = Document.model_validate(json.loads((fixture_dir / "base.json").read_text()))
    desired_fixture = Document.model_validate(
        json.loads((fixture_dir / "desired.json").read_text())
    )

    doc_url = _create_empty_doc(f"Replay {name}")
    doc_id = _extract_document_id(doc_url)
    await _setup_base_state(fixture_dir, doc_url, client, doc_id)

    live_base = Document.model_validate(await client.get_document_raw(doc_id))
    if semantic_diff(live_base, base_fixture):
        raise RuntimeError(f"Live base for {name} did not converge to captured base fixture")

    requests = lower_semantic_diff(live_base, desired_fixture)
    await client.batch_update(doc_id, requests)

    live_after = Document.model_validate(await client.get_document_raw(doc_id))
    residual = semantic_diff(live_after, desired_fixture)
    if residual:
        raise RuntimeError(f"Replay for {name} did not converge: {residual!r}")

    print(f"[replay] {name}: ok ({doc_url})")


async def _setup_base_state(
    fixture_dir: Path,
    doc_url: str,
    client: RawDocsClient,
    doc_id: str,
) -> None:
    base_md = fixture_dir / "base.md"
    if base_md.exists():
        with tempfile.TemporaryDirectory(prefix=f"replay-{fixture_dir.name}-") as tmpdir:
            workdir = Path(tmpdir) / "doc"
            _pull_md(doc_url, workdir)
            (workdir / "Tab_1.md").write_text(base_md.read_text(), encoding="utf-8")
            _push_md(workdir)

    base_header = fixture_dir / "base.header.txt"
    if base_header.exists():
        response = await client.batch_update(doc_id, [{"createHeader": {"type": "DEFAULT"}}])
        header_id = response["replies"][0]["createHeader"]["headerId"]
        await client.batch_update(
            doc_id,
            [
                {
                    "insertText": {
                        "endOfSegmentLocation": {"segmentId": header_id},
                        "text": base_header.read_text().rstrip("\n"),
                    }
                }
            ],
        )


def _create_empty_doc(title: str) -> str:
    result = _run([str(EXTRASUITE), "doc", "create-empty", title])
    match = re.search(r"^URL:\s*(https://docs.google.com/document/d/[^\s]+)$", result.stdout, re.M)
    if match is None:
        raise RuntimeError(f"Could not parse doc URL from output:\n{result.stdout}")
    return match.group(1)


def _pull_md(doc_url: str, output_dir: Path) -> None:
    _run([str(EXTRASUITE), "doc", "pull-md", doc_url, str(output_dir)])


def _push_md(folder: Path) -> None:
    _run([str(EXTRASUITE), "doc", "push-md", str(folder), "--verify"])


def _extract_document_id(doc_url: str) -> str:
    match = re.search(r"/document/d/([a-zA-Z0-9_-]+)", doc_url)
    if match is None:
        raise ValueError(f"Bad document URL: {doc_url}")
    return match.group(1)


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


if __name__ == "__main__":
    main()
