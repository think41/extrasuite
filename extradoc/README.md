# extradoc

File-based Google Docs representation library for LLM agents.

Part of the [ExtraSuite](https://github.com/think41/extrasuite) project.

## Overview

`extradoc` is the library layer behind the Google Docs support in ExtraSuite.
It:

- pulls Google Docs into an XML folder representation
- deserializes edited XML back into typed `Document` objects
- reconciles base vs desired documents into Docs API `batchUpdate` requests
- pushes those requests through a transport

The canonical on-disk format is documented in [docs/on-disk-format.md](/Users/sripathikrishnan/.codex/worktrees/8d0e/extrasuite/extradoc/docs/on-disk-format.md).

## Status

This package currently exposes a programmatic API. The end-user CLI lives in
the `extrasuite` client package and is invoked as `extrasuite doc ...`.

There is no supported standalone `python -m extradoc` pull/diff/push CLI in
this repo.

## Programmatic Usage

```python
from pathlib import Path

from extradoc import DocsClient, GoogleDocsTransport


async def main() -> None:
    transport = GoogleDocsTransport("ACCESS_TOKEN")
    client = DocsClient(transport)
    try:
        await client.pull("DOCUMENT_ID", Path("output"))
        result = await client.push(Path("output") / "DOCUMENT_ID")
        print(result.message)
    finally:
        await transport.close()
```

`DocsClient.diff(folder)` is available for local debugging, but normal user
workflow is pull, edit, push, then re-pull.

## Main Modules

- `src/extradoc/client.py` — `DocsClient` orchestration
- `src/extradoc/serde/` — `Document ↔ XML folder`
- `src/extradoc/reconcile/` — base/desired diff to batchUpdate requests
- `src/extradoc/mock/` — in-process mock Docs API for tests
- `src/extradoc/transport.py` — transport interfaces and implementations

## Development

```bash
cd extradoc
uv sync --all-extras
uv run pytest tests/ -v
uv run ruff check . && uv run ruff format .
uv run mypy src/extradoc
```

## License

MIT License - see `LICENSE`.
