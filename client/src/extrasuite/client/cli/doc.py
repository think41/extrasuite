"""Doc CLI commands: pull, diff, push, create, and raw transport helpers."""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from extrasuite.client.cli._common import (
    _cmd_create,
    _cmd_share,
    _get_credential,
    _get_reason,
    _parse_document_id,
)


def _assert_safe_to_replace(dest_dir: Path) -> None:
    """Abort if ``dest_dir`` is not a safe directory to delete.

    ``pull-md`` replaces the output directory atomically by removing the
    existing one and moving a freshly-pulled temp directory into place.
    That is catastrophic when the user passes ``.`` or any other directory
    that isn't an extrasuite-pull folder — we'd silently wipe their
    project.

    A directory is only considered safe to replace if EITHER:
      1. It is empty, OR
      2. It contains an ``index.md`` or ``index.xml`` marker file at its
         root (indicating it was created by a previous extrasuite pull).

    Additionally, refuse to delete the current working directory or any
    ancestor of it — deleting the cwd out from under the running process
    is never what the user wants.
    """
    dest_abs = dest_dir.resolve()
    cwd_abs = Path.cwd().resolve()
    if dest_abs == cwd_abs or dest_abs in cwd_abs.parents:
        raise SystemExit(
            f"Refusing to overwrite {dest_dir} — it is the current working "
            "directory or an ancestor of it. Pass a dedicated output folder "
            "(e.g. the document id) instead of '.'."
        )

    entries = list(dest_abs.iterdir())
    if not entries:
        return
    if (dest_abs / "index.md").exists() or (dest_abs / "index.xml").exists():
        return
    raise SystemExit(
        f"Refusing to overwrite {dest_dir} — it is not empty and does not "
        "look like a previously-pulled extrasuite folder (no index.md / "
        "index.xml at its root). Remove the directory manually or choose a "
        "different output path."
    )


def cmd_doc_pull(args: Any) -> None:
    """Pull a Google Doc."""
    from extradoc import DocsClient, GoogleDocsTransport

    document_id = _parse_document_id(args.url)
    output_dir_arg = args.output_dir

    reason = _get_reason(args, default="Pulling Google Doc")
    cred = _get_credential(
        args,
        command={"type": "doc.pull", "file_url": args.url, "file_name": ""},
        reason=reason,
    )

    tmp_parent = None
    if output_dir_arg:
        tmp_parent = Path(tempfile.mkdtemp())
        dest_dir = Path(output_dir_arg)
    else:
        dest_dir = Path() / document_id

    async def _run() -> None:
        transport = GoogleDocsTransport(cred.token)
        client = DocsClient(transport)
        pull_parent = tmp_parent if tmp_parent else Path()
        try:
            await client.pull(
                document_id,
                pull_parent,
                save_raw=True,
            )
            if tmp_parent is not None:
                dest_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(tmp_parent / document_id), str(dest_dir))
        finally:
            await transport.close()

    try:
        asyncio.run(_run())
    finally:
        if tmp_parent is not None:
            shutil.rmtree(tmp_parent, ignore_errors=True)

    print(f"Pulled to {dest_dir}/")


def cmd_doc_diff(args: Any) -> None:
    """Preview changes to a Google Doc."""
    from extradoc import DocsClient

    client = DocsClient.__new__(DocsClient)
    result = client.diff(args.folder)
    has_changes = bool(result.batches) or result.comment_ops.has_operations
    if not has_changes:
        print("No changes detected.")
    else:
        if result.batches:
            batches_json = [
                b.model_dump(exclude_none=True, by_alias=True) for b in result.batches
            ]
            print(json.dumps(batches_json, indent=2))
        if result.comment_ops.has_operations:
            parts: list[str] = []
            if result.comment_ops.new_comments:
                parts.append(f"{len(result.comment_ops.new_comments)} new comment(s)")
            if result.comment_ops.new_replies:
                parts.append(f"{len(result.comment_ops.new_replies)} new reply/replies")
            if result.comment_ops.resolves:
                parts.append(
                    f"{len(result.comment_ops.resolves)} comment(s) to resolve"
                )
            print("Comment operations: " + ", ".join(parts))


def cmd_doc_push(args: Any) -> None:
    """Push changes to a Google Doc."""
    from extradoc import DocsClient, GoogleDocsTransport

    debug = bool(getattr(args, "debug", False))
    if debug:
        from extradoc.debug_push import dump_debug_artifacts

        try:
            debug_dir = dump_debug_artifacts(args.folder)
            print(f"[debug] wrote pipeline artifacts to {debug_dir}/", file=sys.stderr)
        except Exception as exc:
            print(f"[debug] failed to dump artifacts: {exc}", file=sys.stderr)

    reason = _get_reason(args, default="Pushing changes to Google Doc")
    cred = _get_credential(
        args,
        command={"type": "doc.push", "file_url": "", "file_name": ""},
        reason=reason,
    )

    async def _run() -> None:
        transport = GoogleDocsTransport(cred.token)
        client = DocsClient(transport)
        try:
            result = await client.push(args.folder, force=args.force)
            print(result.message)
            if not result.success:
                if debug:
                    from extradoc.debug_push import analyze_push_error

                    print("", file=sys.stderr)
                    print(
                        analyze_push_error(args.folder, result.message),
                        file=sys.stderr,
                    )
                sys.exit(1)
        finally:
            await transport.close()

    asyncio.run(_run())


def cmd_doc_pull_md(args: Any) -> None:
    """Pull a Google Doc in markdown format."""
    from extradoc import DocsClient, GoogleDocsTransport

    document_id = _parse_document_id(args.url)
    output_dir_arg = args.output_dir

    reason = _get_reason(args, default="Pulling Google Doc as markdown")
    cred = _get_credential(
        args,
        command={"type": "doc.pull", "file_url": args.url, "file_name": ""},
        reason=reason,
    )

    tmp_parent = None
    if output_dir_arg:
        tmp_parent = Path(tempfile.mkdtemp())
        dest_dir = Path(output_dir_arg)
    else:
        dest_dir = Path() / document_id

    async def _run() -> None:
        transport = GoogleDocsTransport(cred.token)
        client = DocsClient(transport)
        pull_parent = tmp_parent if tmp_parent else Path()
        try:
            await client.pull(
                document_id,
                pull_parent,
                save_raw=True,
                format="markdown",
            )
            if tmp_parent is not None:
                dest_dir.parent.mkdir(parents=True, exist_ok=True)
                if dest_dir.exists():
                    _assert_safe_to_replace(dest_dir)
                    shutil.rmtree(dest_dir)
                shutil.move(str(tmp_parent / document_id), str(dest_dir))
        finally:
            await transport.close()

    try:
        asyncio.run(_run())
    finally:
        if tmp_parent is not None:
            shutil.rmtree(tmp_parent, ignore_errors=True)

    print(f"Pulled to {dest_dir}/")


def cmd_doc_push_md(args: Any) -> None:
    """Push changes to a Google Doc (markdown format, auto-detected)."""
    # Format is auto-detected from index.xml; push logic is identical to XML.
    cmd_doc_push(args)


def cmd_doc_create(args: Any) -> None:
    """Create a new Google Doc and pull it locally."""
    from extradoc import DocsClient, GoogleDocsTransport

    file_id, url = _cmd_create("doc", args)

    output_dir_arg = getattr(args, "output_dir", None)
    tmp_parent = None
    if output_dir_arg:
        tmp_parent = Path(tempfile.mkdtemp())
        dest_dir = Path(output_dir_arg)
    else:
        dest_dir = Path() / file_id

    reason = _get_reason(args, default="Pulling newly created Google Doc")
    cred = _get_credential(
        args,
        command={"type": "doc.pull", "file_url": url, "file_name": args.title},
        reason=reason,
    )

    async def _run() -> None:
        transport = GoogleDocsTransport(cred.token)
        client = DocsClient(transport)
        pull_parent = tmp_parent if tmp_parent else Path()
        try:
            await client.pull(file_id, pull_parent, save_raw=True)
            if tmp_parent is not None:
                dest_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(tmp_parent / file_id), str(dest_dir))
        finally:
            await transport.close()

    try:
        asyncio.run(_run())
    finally:
        if tmp_parent is not None:
            shutil.rmtree(tmp_parent, ignore_errors=True)

    print(f"Pulled to {dest_dir}/")


def cmd_doc_create_empty(args: Any) -> None:
    """Create a blank Google Doc without pulling it locally."""
    _cmd_create("doc", args)


def cmd_doc_download_raw(args: Any) -> None:
    """Download raw Google Docs transport JSON for a document."""
    from extradoc import GoogleDocsTransport

    document_id = _parse_document_id(args.url)
    reason = _get_reason(args, default="Downloading raw Google Doc JSON")
    cred = _get_credential(
        args,
        command={"type": "doc.pull", "file_url": args.url, "file_name": ""},
        reason=reason,
    )

    async def _run() -> tuple[dict[str, Any], list[dict[str, Any]]]:
        transport = GoogleDocsTransport(cred.token)
        try:
            document = await transport.get_document(document_id)
            comments = (
                await transport.list_comments(document_id) if args.comments else []
            )
            return document.raw, comments
        finally:
            await transport.close()

    raw_document, raw_comments = asyncio.run(_run())
    doc_path, comments_path = _resolve_raw_output_paths(
        document_id=document_id,
        output=getattr(args, "output", None),
        include_comments=args.comments,
    )
    _write_json(doc_path, raw_document)
    print(f"Wrote {doc_path}")
    if comments_path is not None:
        _write_json(comments_path, {"comments": raw_comments})
        print(f"Wrote {comments_path}")


def cmd_doc_share(args: Any) -> None:
    """Share a Google Doc with trusted contacts."""
    _cmd_share("doc", args)


def _resolve_raw_output_paths(
    *,
    document_id: str,
    output: str | None,
    include_comments: bool,
) -> tuple[Path, Path | None]:
    if output is None:
        doc_path = Path(f"{document_id}.json")
    else:
        candidate = Path(output)
        if candidate.suffix.lower() == ".json":
            doc_path = candidate
        else:
            candidate.mkdir(parents=True, exist_ok=True)
            doc_path = candidate / "document.json"

    comments_path: Path | None = None
    if include_comments:
        if doc_path.name == "document.json":
            comments_path = doc_path.with_name("comments.json")
        else:
            comments_path = doc_path.with_name(f"{doc_path.stem}.comments.json")
    return doc_path, comments_path


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# verify-table-indices — debug command
# ---------------------------------------------------------------------------


def cmd_doc_verify_table_indices(args: Any) -> None:
    """Verify deterministic table index prediction against the live API."""
    from extradoc import GoogleDocsTransport

    document_id = _parse_document_id(args.url)
    reason = _get_reason(args, default="Verifying table index prediction")
    cred = _get_credential(
        args,
        command={"type": "doc.push", "file_url": args.url, "file_name": ""},
        reason=reason,
    )

    async def _run() -> None:
        transport = GoogleDocsTransport(cred.token)
        try:
            results = await _verify_table_indices(transport, document_id)
        finally:
            await transport.close()

        passed = sum(1 for r in results if r["passed"])
        total = len(results)
        for r in results:
            status = "PASS" if r["passed"] else "FAIL"
            print(f"[{status}] {r['name']}")
            for err in r.get("errors", []):
                print(f"       {err}")
        print(f"\n{passed}/{total} tests passed")
        if passed < total:
            sys.exit(1)

    asyncio.run(_run())


# ── Index model ─────────────────────────────────────────────────────────────


def _extract_first_table(raw_doc: dict[str, Any]) -> dict[str, Any]:
    """Return the first table structural element from the first tab body."""
    tabs = raw_doc.get("tabs", [])
    if not tabs:
        raise ValueError("Document has no tabs")
    content = tabs[0].get("documentTab", {}).get("body", {}).get("content", [])
    for element in content:
        if "table" in element:
            return element
    raise ValueError("No table found in document body")


def _tab_id(raw_doc: dict[str, Any]) -> str:
    tabs = raw_doc.get("tabs", [])
    if not tabs:
        raise ValueError("Document has no tabs")
    return tabs[0]["tabProperties"]["tabId"]


def _parse_table(element: dict[str, Any]) -> dict[str, Any]:
    """
    Return a compact dict representation of table indices:
      { start, end, rows: [ { start, end, cells: [ { start, end } ] } ] }
    All indices match what the API returns (startIndex / endIndex).
    """
    rows = []
    for row in element["table"].get("tableRows", []):
        cells = []
        for cell in row.get("tableCells", []):
            cells.append({"start": cell["startIndex"], "end": cell["endIndex"]})
        rows.append(
            {"start": row["startIndex"], "end": row["endIndex"], "cells": cells}
        )
    return {"start": element["startIndex"], "end": element["endIndex"], "rows": rows}


def _num_cols(table: dict[str, Any]) -> int:
    return len(table["rows"][0]["cells"]) if table["rows"] else 0


# ── Prediction engine ────────────────────────────────────────────────────────


def _predict_insert_row(
    table: dict[str, Any], row_index: int, insert_below: bool
) -> dict[str, Any]:
    """
    Predict table indices after insertTableRow.

    insert_below=False → new blank row appears ABOVE existing row_index.
    insert_below=True  → new blank row appears BELOW existing row_index
                         (i.e. above existing row_index+1, or appended).
    """
    rows = table["rows"]
    ncols = _num_cols(table)
    new_row_span = 1 + ncols * 2  # 1 row-opener + N blank cells of span 2

    if insert_below:
        # New row starts after the referenced row
        if row_index < len(rows) - 1:
            insert_pos = row_index + 1  # position in rows array
            new_start = rows[row_index + 1]["start"]
        else:
            insert_pos = len(rows)  # append
            new_start = rows[-1]["end"]
    else:
        insert_pos = row_index
        new_start = rows[row_index]["start"]

    # Build the new blank row
    new_cells = []
    cell_start = new_start + 1  # +1 for row opener
    for _ in range(ncols):
        new_cells.append({"start": cell_start, "end": cell_start + 2})
        cell_start += 2
    new_row = {"start": new_start, "end": new_start + new_row_span, "cells": new_cells}

    # Rebuild rows with shift applied to rows at >= insert_pos
    new_rows = []
    for i, row in enumerate(rows):
        if i < insert_pos:
            new_rows.append(row)
        elif i == insert_pos:
            new_rows.append(new_row)
            new_rows.append(_shift_row(row, new_row_span))
        else:
            new_rows.append(_shift_row(row, new_row_span))
    if insert_pos == len(rows):
        new_rows.append(new_row)

    return {
        "start": table["start"],
        "end": table["end"] + new_row_span,
        "rows": new_rows,
    }


def _predict_delete_row(table: dict[str, Any], row_index: int) -> dict[str, Any]:
    rows = table["rows"]
    deleted_span = rows[row_index]["end"] - rows[row_index]["start"]
    new_rows = []
    for i, row in enumerate(rows):
        if i < row_index:
            new_rows.append(row)
        elif i > row_index:
            new_rows.append(_shift_row(row, -deleted_span))
    return {
        "start": table["start"],
        "end": table["end"] - deleted_span,
        "rows": new_rows,
    }


def _predict_insert_column(
    table: dict[str, Any], column_index: int, insert_right: bool
) -> dict[str, Any]:
    """
    Predict table indices after insertTableColumn.

    insert_right=False → new column appears to the LEFT of column_index.
    insert_right=True  → new column appears to the RIGHT of column_index.

    Since rows are sequential in the index space, inserting a cell in row r
    (span=2) shifts all subsequent rows by 2. Cumulative shift going into row r
    is r * 2.
    """
    eff_col = column_index + 1 if insert_right else column_index
    new_rows = []
    cumulative = 0  # total shift accumulated from previous rows
    for _r_idx, row in enumerate(table["rows"]):
        row_start = row["start"] + cumulative
        new_cells = []
        for c_idx, cell in enumerate(row["cells"]):
            s = cell["start"] + cumulative
            e = cell["end"] + cumulative
            if c_idx == eff_col:
                # Insert blank cell here, then the existing cell (shifted by 2)
                new_cells.append({"start": s, "end": s + 2})
                new_cells.append({"start": s + 2, "end": e + 2})
            elif c_idx > eff_col:
                new_cells.append({"start": s + 2, "end": e + 2})
            else:
                new_cells.append({"start": s, "end": e})
        if eff_col >= len(row["cells"]):
            # Append at end of row
            last_end = row["cells"][-1]["end"] + cumulative
            new_cells.append({"start": last_end, "end": last_end + 2})
        row_end = row["end"] + cumulative + 2
        new_rows.append({"start": row_start, "end": row_end, "cells": new_cells})
        cumulative += 2

    total_new = len(table["rows"]) * 2
    return {"start": table["start"], "end": table["end"] + total_new, "rows": new_rows}


def _predict_delete_column(table: dict[str, Any], column_index: int) -> dict[str, Any]:
    new_rows = []
    cumulative = 0  # negative shift from previous rows' deleted cells
    for row in table["rows"]:
        deleted_span = (
            row["cells"][column_index]["end"] - row["cells"][column_index]["start"]
        )
        row_start = row["start"] + cumulative
        new_cells = []
        for c_idx, cell in enumerate(row["cells"]):
            if c_idx == column_index:
                continue
            shift = cumulative if c_idx < column_index else cumulative - deleted_span
            new_cells.append(
                {"start": cell["start"] + shift, "end": cell["end"] + shift}
            )
        row_end = row["end"] + cumulative - deleted_span
        new_rows.append({"start": row_start, "end": row_end, "cells": new_cells})
        cumulative -= deleted_span
    return {"start": table["start"], "end": table["end"] + cumulative, "rows": new_rows}


def _shift_row(row: dict[str, Any], delta: int) -> dict[str, Any]:
    return {
        "start": row["start"] + delta,
        "end": row["end"] + delta,
        "cells": [
            {"start": c["start"] + delta, "end": c["end"] + delta} for c in row["cells"]
        ],
    }


# ── Comparison ───────────────────────────────────────────────────────────────


def _compare_tables(predicted: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if predicted["start"] != actual["start"]:
        errors.append(
            f"table.start: predicted={predicted['start']} actual={actual['start']}"
        )
    if predicted["end"] != actual["end"]:
        errors.append(f"table.end: predicted={predicted['end']} actual={actual['end']}")
    prows, arows = predicted["rows"], actual["rows"]
    if len(prows) != len(arows):
        errors.append(f"num_rows: predicted={len(prows)} actual={len(arows)}")
        return errors
    for r, (pr, ar) in enumerate(zip(prows, arows, strict=False)):
        if pr["start"] != ar["start"]:
            errors.append(
                f"row[{r}].start: predicted={pr['start']} actual={ar['start']}"
            )
        if pr["end"] != ar["end"]:
            errors.append(f"row[{r}].end: predicted={pr['end']} actual={ar['end']}")
        pcells, acells = pr["cells"], ar["cells"]
        if len(pcells) != len(acells):
            errors.append(
                f"row[{r}] num_cells: predicted={len(pcells)} actual={len(acells)}"
            )
            continue
        for c, (pc, ac) in enumerate(zip(pcells, acells, strict=False)):
            if pc["start"] != ac["start"]:
                errors.append(
                    f"cell[{r},{c}].start: predicted={pc['start']} actual={ac['start']}"
                )
            if pc["end"] != ac["end"]:
                errors.append(
                    f"cell[{r},{c}].end: predicted={pc['end']} actual={ac['end']}"
                )
    return errors


# ── Test harness ─────────────────────────────────────────────────────────────


async def _setup_table(
    transport: Any,
    doc_id: str,
    tab_id: str,
    rows: int,
    cols: int,
) -> dict[str, Any]:
    """
    Insert a blank MxN table at index 1, fill cells with variable-length text,
    and return the actual table index structure after filling.

    Cell (r, c) gets text of length r*cols + c + 1 chars (e.g. "a", "bb", "ccc"…).
    Text is inserted without trailing \\n (the blank cell already has one).
    Insertions go bottom-to-top, right-to-left to avoid index shifts.
    """
    # Insert blank table
    await transport.batch_update(
        doc_id,
        [
            {
                "insertTable": {
                    "rows": rows,
                    "columns": cols,
                    "location": {"index": 1, "tabId": tab_id},
                }
            }
        ],
    )

    # Fetch to get blank-cell indices
    raw = (await transport.get_document(doc_id)).raw
    table = _parse_table(_extract_first_table(raw))

    # Fill cells bottom-to-top, right-to-left
    fill_reqs = []
    for r in range(rows - 1, -1, -1):
        for c in range(cols - 1, -1, -1):
            length = r * cols + c + 1
            text = chr(ord("a") + (r * cols + c) % 26) * length
            cell = table["rows"][r]["cells"][c]
            fill_reqs.append(
                {
                    "insertText": {
                        "location": {"index": cell["start"] + 1, "tabId": tab_id},
                        "text": text,
                    }
                }
            )
    await transport.batch_update(doc_id, fill_reqs)

    # Fetch final state
    raw = (await transport.get_document(doc_id)).raw
    return _parse_table(_extract_first_table(raw))


async def _teardown_table(
    transport: Any,
    doc_id: str,
    tab_id: str,
    table: dict[str, Any],
) -> None:
    """Delete the table by removing its content range."""
    await transport.batch_update(
        doc_id,
        [
            {
                "deleteContentRange": {
                    "range": {
                        "startIndex": table["start"],
                        "endIndex": table["end"],
                        "tabId": tab_id,
                    }
                }
            }
        ],
    )


async def _run_one(
    transport: Any,
    doc_id: str,
    tab_id: str,
    name: str,
    predict_fn: Any,
    request_fn: Any,
) -> dict[str, Any]:
    """
    Run a single prediction scenario:
      1. setup: insert + fill 3x3 table
      2. predict: call predict_fn(table) → predicted_table
      3. apply: call request_fn(table) → API request, execute it
      4. fetch + compare
      5. teardown
    """
    try:
        table = await _setup_table(transport, doc_id, tab_id, 3, 3)
        predicted = predict_fn(table)
        request = request_fn(table, tab_id)
        await transport.batch_update(doc_id, [request])
        raw = (await transport.get_document(doc_id)).raw
        actual = _parse_table(_extract_first_table(raw))
        errors = _compare_tables(predicted, actual)
        await _teardown_table(transport, doc_id, tab_id, actual)
        return {"name": name, "passed": not errors, "errors": errors}
    except Exception as exc:
        # Best-effort cleanup: re-fetch to find table and delete it
        try:
            raw = (await transport.get_document(doc_id)).raw
            actual = _parse_table(_extract_first_table(raw))
            await _teardown_table(transport, doc_id, tab_id, actual)
        except Exception:
            pass
        return {"name": name, "passed": False, "errors": [f"Exception: {exc}"]}


async def _run_chained(
    transport: Any,
    doc_id: str,
    tab_id: str,
    name: str,
    predict_fns: list[Any],
    request_fns: list[Any],
) -> dict[str, Any]:
    """
    Run two operations in sequence, verifying the chained prediction.
    predict_fns[1] receives the output of predict_fns[0] as input.
    """
    try:
        table = await _setup_table(transport, doc_id, tab_id, 3, 3)
        # Apply ops and predictions in sequence
        current = table
        for predict_fn, request_fn in zip(predict_fns, request_fns, strict=False):
            predicted = predict_fn(current)
            request = request_fn(current, tab_id)
            await transport.batch_update(doc_id, [request])
            raw = (await transport.get_document(doc_id)).raw
            actual = _parse_table(_extract_first_table(raw))
            errors = _compare_tables(predicted, actual)
            if errors:
                await _teardown_table(transport, doc_id, tab_id, actual)
                return {"name": name, "passed": False, "errors": errors}
            current = actual
        await _teardown_table(transport, doc_id, tab_id, current)
        return {"name": name, "passed": True, "errors": []}
    except Exception as exc:
        try:
            raw = (await transport.get_document(doc_id)).raw
            actual = _parse_table(_extract_first_table(raw))
            await _teardown_table(transport, doc_id, tab_id, actual)
        except Exception:
            pass
        return {"name": name, "passed": False, "errors": [f"Exception: {exc}"]}


async def _verify_table_indices(transport: Any, doc_id: str) -> list[dict[str, Any]]:
    raw = (await transport.get_document(doc_id)).raw
    tid = _tab_id(raw)

    def req_insert_row(row_index: int, insert_below: bool):  # type: ignore[return]
        def _make(table: dict[str, Any], tab_id: str) -> dict[str, Any]:
            return {
                "insertTableRow": {
                    "tableCellLocation": {
                        "tableStartLocation": {
                            "index": table["start"],
                            "tabId": tab_id,
                        },
                        "rowIndex": row_index,
                        "columnIndex": 0,
                    },
                    "insertBelow": insert_below,
                }
            }

        return _make

    def req_delete_row(row_index: int):  # type: ignore[return]
        def _make(table: dict[str, Any], tab_id: str) -> dict[str, Any]:
            return {
                "deleteTableRow": {
                    "tableCellLocation": {
                        "tableStartLocation": {
                            "index": table["start"],
                            "tabId": tab_id,
                        },
                        "rowIndex": row_index,
                        "columnIndex": 0,
                    }
                }
            }

        return _make

    def req_insert_col(col_index: int, insert_right: bool):  # type: ignore[return]
        def _make(table: dict[str, Any], tab_id: str) -> dict[str, Any]:
            return {
                "insertTableColumn": {
                    "tableCellLocation": {
                        "tableStartLocation": {
                            "index": table["start"],
                            "tabId": tab_id,
                        },
                        "rowIndex": 0,
                        "columnIndex": col_index,
                    },
                    "insertRight": insert_right,
                }
            }

        return _make

    def req_delete_col(col_index: int):  # type: ignore[return]
        def _make(table: dict[str, Any], tab_id: str) -> dict[str, Any]:
            return {
                "deleteTableColumn": {
                    "tableCellLocation": {
                        "tableStartLocation": {
                            "index": table["start"],
                            "tabId": tab_id,
                        },
                        "rowIndex": 0,
                        "columnIndex": col_index,
                    }
                }
            }

        return _make

    results = []

    # ── Row scenarios ──────────────────────────────────────────────────────
    results.append(
        await _run_one(
            transport,
            doc_id,
            tid,
            "insert row above first (row_index=0, insertBelow=False)",
            lambda t: _predict_insert_row(t, 0, False),
            req_insert_row(0, False),
        )
    )
    results.append(
        await _run_one(
            transport,
            doc_id,
            tid,
            "insert row in middle (row_index=1, insertBelow=False)",
            lambda t: _predict_insert_row(t, 1, False),
            req_insert_row(1, False),
        )
    )
    results.append(
        await _run_one(
            transport,
            doc_id,
            tid,
            "insert row at end (row_index=2, insertBelow=True)",
            lambda t: _predict_insert_row(t, 2, True),
            req_insert_row(2, True),
        )
    )
    results.append(
        await _run_one(
            transport,
            doc_id,
            tid,
            "delete row at index 0",
            lambda t: _predict_delete_row(t, 0),
            req_delete_row(0),
        )
    )
    results.append(
        await _run_one(
            transport,
            doc_id,
            tid,
            "delete row at index 1 (middle)",
            lambda t: _predict_delete_row(t, 1),
            req_delete_row(1),
        )
    )
    results.append(
        await _run_one(
            transport,
            doc_id,
            tid,
            "delete row at index 2 (last)",
            lambda t: _predict_delete_row(t, 2),
            req_delete_row(2),
        )
    )

    # ── Column scenarios ───────────────────────────────────────────────────
    results.append(
        await _run_one(
            transport,
            doc_id,
            tid,
            "insert column at index 0, insertRight=False (prepend)",
            lambda t: _predict_insert_column(t, 0, False),
            req_insert_col(0, False),
        )
    )
    results.append(
        await _run_one(
            transport,
            doc_id,
            tid,
            "insert column at index 1, insertRight=False (middle-left)",
            lambda t: _predict_insert_column(t, 1, False),
            req_insert_col(1, False),
        )
    )
    results.append(
        await _run_one(
            transport,
            doc_id,
            tid,
            "insert column at index 2, insertRight=False (middle-right)",
            lambda t: _predict_insert_column(t, 2, False),
            req_insert_col(2, False),
        )
    )
    results.append(
        await _run_one(
            transport,
            doc_id,
            tid,
            "insert column at index 2, insertRight=True (append)",
            lambda t: _predict_insert_column(t, 2, True),
            req_insert_col(2, True),
        )
    )
    results.append(
        await _run_one(
            transport,
            doc_id,
            tid,
            "delete column at index 0",
            lambda t: _predict_delete_column(t, 0),
            req_delete_col(0),
        )
    )
    results.append(
        await _run_one(
            transport,
            doc_id,
            tid,
            "delete column at index 1 (middle)",
            lambda t: _predict_delete_column(t, 1),
            req_delete_col(1),
        )
    )
    results.append(
        await _run_one(
            transport,
            doc_id,
            tid,
            "delete column at index 2 (last)",
            lambda t: _predict_delete_column(t, 2),
            req_delete_col(2),
        )
    )

    # ── Multi-op chained scenarios ─────────────────────────────────────────
    results.append(
        await _run_chained(
            transport,
            doc_id,
            tid,
            "chain: insert row(0) then insert col(0)",
            [
                lambda t: _predict_insert_row(t, 0, False),
                lambda t: _predict_insert_column(t, 0, False),
            ],
            [req_insert_row(0, False), req_insert_col(0, False)],
        )
    )
    results.append(
        await _run_chained(
            transport,
            doc_id,
            tid,
            "chain: insert col(1) then delete col(1)",
            [
                lambda t: _predict_insert_column(t, 1, False),
                lambda t: _predict_delete_column(t, 1),
            ],
            [req_insert_col(1, False), req_delete_col(1)],
        )
    )
    results.append(
        await _run_chained(
            transport,
            doc_id,
            tid,
            "chain: insert row(2,below) then delete row(0)",
            [
                lambda t: _predict_insert_row(t, 2, True),
                lambda t: _predict_delete_row(t, 0),
            ],
            [req_insert_row(2, True), req_delete_row(0)],
        )
    )

    return results
