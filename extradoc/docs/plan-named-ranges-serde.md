# Named Ranges as Semantic Annotation Layer — Implementation Plan

**GitHub Issue:** #29
**Branch:** `markdown-format`

---

## Design Principles

### Typed special elements

Special markdown constructs — fenced code blocks, callouts, blockquotes — are first-class typed objects (`CodeBlock`, `Callout`, `Blockquote`). Each typed object knows:

- its canonical Google Docs representation (a styled 1×1 table)
- its canonical markdown serialization
- its named range name

This keeps all element-specific logic in one place, not spread across `_to_markdown.py` and `_from_markdown.py`.

### Canonical styling, always applied

Canonical visual styling (cell background color, monospace font, border) is part of the typed object's definition. It is applied every time `to_table()` is called — on every push, not just the first one. This means the Google Doc always looks consistent regardless of whether the user manually edited the styling.

This is the correct behavior for a markdown-first workflow: the markdown is the source of truth, and push makes the Google Doc match it.

### Named ranges are the only semantic source of truth on pull

A table serializes as a special element **only if** an `extradoc:*` named range covers it. No heuristics. A table without a named range is serialized as a regular GFM or HTML table, exactly as today.

### No side channels: the Document is self-contained

`markdown_to_document()` returns a complete `Document` that includes `namedRanges` in the `DocumentTab`. The named ranges are populated internally (after `reindex_document()` assigns real indices to the body elements). The caller receives a complete Document and passes it directly to `reconcile()`. No extra return values, no side dicts.

### Reconciler handles named range diffing

The reconciler already aligns structural elements between base and desired. It will be extended to also diff `extradoc:*` named ranges, emitting `createNamedRange` and `deleteNamedRange` requests as part of the final batch.

---

## New Module: `serde/_special_elements.py`

This module owns all knowledge about the three special element types.

```python
class SpecialElement(ABC):
    @property
    @abstractmethod
    def named_range_name(self) -> str: ...

    @abstractmethod
    def to_table(self) -> Table:
        """Build a 1×1 Table with canonical content and visual styling."""

    @abstractmethod
    def to_markdown(self) -> str:
        """Render as a markdown string (no trailing newline)."""

    @classmethod
    @abstractmethod
    def from_table(cls, table: Table, named_range_name: str) -> "SpecialElement":
        """Reconstruct from a named-range-annotated table on pull."""
```

### `CodeBlock`

```python
@dataclass
class CodeBlock(SpecialElement):
    language: str      # "" for language-less
    lines: list[str]   # one entry per line of code

    @property
    def named_range_name(self) -> str:
        return f"extradoc:codeblock:{self.language}" if self.language else "extradoc:codeblock"

    def to_markdown(self) -> str:
        fence = f"```{self.language}" if self.language else "```"
        return fence + "\n" + "\n".join(self.lines) + "\n```"

    def to_table(self) -> Table:
        # Cell style: background #f3f3f3
        # Each line → Paragraph with TextRun(content, TextStyle(Courier New 10pt))
        # Trailing empty paragraph required by Docs API
        ...

    @classmethod
    def from_table(cls, table: Table, named_range_name: str) -> "CodeBlock":
        # Extract language from named_range_name (parts[2] if present)
        # Extract lines from cell paragraphs (strip trailing \n from each)
        ...
```

### `Callout`

```python
@dataclass
class Callout(SpecialElement):
    variant: Literal["warning", "info", "danger", "tip"]
    lines: list[str]

    _BG: ClassVar[dict[str, str]] = {
        "warning": "#fff3cd",
        "info":    "#d1ecf1",
        "danger":  "#f8d7da",
        "tip":     "#d4edda",
    }

    @property
    def named_range_name(self) -> str:
        return f"extradoc:callout:{self.variant}"

    def to_markdown(self) -> str:
        header = f"> [!{self.variant.upper()}]"
        body = [f"> {line}" for line in self.lines]
        return "\n".join([header] + body)

    def to_table(self) -> Table:
        # Cell style: background from _BG[self.variant]
        # Content: one Paragraph per line, normal TextStyle
        ...

    @classmethod
    def from_table(cls, table: Table, named_range_name: str) -> "Callout":
        # variant from named_range_name parts[2]
        # lines from cell paragraphs
        ...
```

### `Blockquote`

```python
@dataclass
class Blockquote(SpecialElement):
    lines: list[str]

    @property
    def named_range_name(self) -> str:
        return "extradoc:blockquote"

    def to_markdown(self) -> str:
        return "\n".join(f"> {line}" for line in self.lines)

    def to_table(self) -> Table:
        # Cell style: background #f9f9f9, left border 3pt #888888 SOLID
        # top/right/bottom borders: absent
        # Content: one Paragraph per line, normal TextStyle
        ...

    @classmethod
    def from_table(cls, table: Table, named_range_name: str) -> "Blockquote":
        ...
```

### Factory function

```python
def special_element_from_named_range(
    table: Table, named_range_name: str
) -> SpecialElement:
    """Construct the right typed object given a table and its named range name."""
    parts = named_range_name.split(":")
    type_ = parts[1]
    if type_ == "codeblock":
        return CodeBlock.from_table(table, named_range_name)
    elif type_ == "callout":
        return Callout.from_table(table, named_range_name)
    elif type_ == "blockquote":
        return Blockquote.from_table(table, named_range_name)
    raise ValueError(f"Unknown extradoc type: {named_range_name!r}")
```

---

## Push Path: `_from_markdown.py`

### New mistletoe imports

```python
from mistletoe.block_token import CodeFence, Quote
from mistletoe.span_token import InlineCode
```

Verify exact names: `python -c "import mistletoe.block_token; print(dir(mistletoe.block_token))"`.

### `_parse_body` changes

Track `special_positions: list[tuple[int, str]]` — `(body_index, named_range_name)` for each special element inserted.

```python
elif isinstance(block, CodeFence):
    elem = CodeBlock(
        language=block.language.strip(),
        lines=block.children[0].content.split("\n"),
    )
    special_positions.append((len(body), elem.named_range_name))
    body.append(StructuralElement(table=elem.to_table()))

elif isinstance(block, Quote):
    elem = _quote_to_special_element(block)
    special_positions.append((len(body), elem.named_range_name))
    body.append(StructuralElement(table=elem.to_table()))
```

**`_quote_to_special_element(block) → SpecialElement`:**

1. Check first child paragraph's raw text against `^\[!(WARNING|INFO|DANGER|TIP)\]$`:
   - Match → `Callout(variant=..., lines=lines_from_remaining_children)`
   - No match → `Blockquote(lines=lines_from_all_children)`
2. Extract lines: for each child block (Paragraph, List), convert to plain text lines. For v1, support paragraphs only; nested lists inside quotes are deferred.

### Named ranges embedded in Document

After building the body, `_parse_tab` calls `reindex_document()` on the tab to get real indices, then populates `DocumentTab.namedRanges`:

```python
def _parse_tab(source, tab_title, folder, tab_id=""):
    list_synth = _ListSynth()
    body_content, footnotes, special_positions = _parse_body(source, list_synth)

    # ... build doc_tab_d as before ...

    # Reindex to assign real start/end indices
    tab_props = TabProperties(tab_id=tab_id or f"t.{folder}", title=tab_title)
    doc_tab = DocumentTab.model_validate(doc_tab_d)
    tab = Tab(tab_properties=tab_props, document_tab=doc_tab)
    temp_doc = Document(tabs=[tab])
    reindexed = reindex_document(temp_doc)
    reindexed_body = reindexed.tabs[0].document_tab.body.content or []

    # Build namedRanges from special_positions
    named_ranges_d: dict[str, Any] = {}
    for body_pos, nr_name in special_positions:
        se = reindexed_body[body_pos]
        nr_entry = {
            "namedRangeId": f"kix.md_nr_{body_pos}",
            "name": nr_name,
            "ranges": [{"startIndex": se.start_index, "endIndex": se.end_index}],
        }
        group = named_ranges_d.setdefault(nr_name, {"name": nr_name, "namedRanges": []})
        group["namedRanges"].append(nr_entry)

    if named_ranges_d:
        reindexed.tabs[0].document_tab = reindexed.tabs[0].document_tab.model_copy(
            update={"named_ranges": named_ranges_d}
        )

    return reindexed.tabs[0]
```

`markdown_to_document()` return type stays `Document`. No side channel.

### Inline code

In `_tokens_to_elements`, add:

```python
elif isinstance(token, InlineCode):
    ts = TextStyle(
        weighted_font_family=WeightedFontFamily(font_family="Courier New"),
        font_size=Dimension(magnitude=10, unit=DimensionUnit.PT),
    )
    yield ParagraphElement(text_run=TextRun(content=token.children[0].content, text_style=ts))
```

Also remove backtick from `_escape_md` — it prevents inline code from round-tripping.

---

## Pull Path: `_to_markdown.py`

### Named range index

```python
def _build_named_range_index(doc_tab: DocumentTab) -> dict[int, str]:
    """Map start_index → extradoc:* name, iterating ALL NamedRange entries per group."""
    index: dict[int, str] = {}
    for name, group in (doc_tab.named_ranges or {}).items():
        if not name.startswith("extradoc:"):
            continue
        for nr in group.named_ranges or []:        # multiple entries with same name OK
            for r in nr.ranges or []:
                if r.start_index is not None:
                    index[r.start_index] = name
    return index
```

Multiple ranges with the same name (e.g. two `extradoc:callout:warning` blocks) each have their own `namedRangeId` and `ranges` entry. Both are indexed correctly here.

### Routing in `_serialize_content`

```python
if se.table is not None:
    annotation = named_range_index.get(se.start_index or 0)
    if annotation:
        elem = special_element_from_named_range(se.table, annotation)
        block = elem.to_markdown()
    else:
        block = _serialize_table(se.table)   # unchanged — no heuristics
```

### Inline code in `_serialize_text_run`

```python
_MONOSPACE_FAMILIES = {"Courier New", "Courier", "Source Code Pro", "Roboto Mono"}

if style.weighted_font_family and style.weighted_font_family.font_family in _MONOSPACE_FAMILIES:
    # Emit inline code; other formatting on monospace runs is dropped
    return f"`{text}`"
```

### Relative URL fix

```python
def _normalize_url(url: str) -> str:
    if url.startswith("http://"):
        host = urllib.parse.urlparse(url).netloc
        if "." not in host and host not in {"localhost"}:
            return url[7:]   # strip spurious http:// prefix
    return url
```

Apply in `_serialize_text_run` when emitting `[text](url)`.

---

## Reconciler: Named Range Diffing

**File:** `extradoc/src/extradoc/reconcile/_core.py` (or a new `_named_ranges.py`)

The reconciler's LCS alignment already classifies each structural element as matched, inserted, or deleted. Extend `reconcile()` with a named range diff step that runs after the body diff:

```python
def _diff_named_ranges(
    base_tab: DocumentTab,
    desired_tab: DocumentTab,
    body_alignment: list[AlignedPair],    # from existing LCS step
) -> list[Request]:
    """Generate createNamedRange / deleteNamedRange for extradoc:* ranges."""
    requests = []

    base_index  = _build_extradoc_nr_index(base_tab)    # {start_index → (namedRangeId, name)}
    desired_index = _build_extradoc_nr_index(desired_tab)  # {start_index → (synthetic_id, name)}

    # Inserted tables (in desired, not in base) → createNamedRange
    for pair in body_alignment:
        if pair.is_insert and pair.desired_se.table is not None:
            si = pair.desired_se.start_index
            if si in desired_index:
                _, name = desired_index[si]
                requests.append(Request(create_named_range=CreateNamedRangeRequest(
                    name=name,
                    range=Range(start_index=si, end_index=pair.desired_se.end_index,
                                tab_id=desired_tab.tab_id),
                )))

    # Deleted tables (in base, not in desired) → deleteNamedRange
    for pair in body_alignment:
        if pair.is_delete and pair.base_se.table is not None:
            si = pair.base_se.start_index
            if si in base_index:
                nr_id, _ = base_index[si]
                requests.append(Request(delete_named_range=DeleteNamedRangeRequest(
                    named_range_id=nr_id,
                )))

    # Type change (same position, different name) → delete old + create new
    # Deferred: uncommon edge case, can be a follow-up

    return requests
```

Named range requests are appended to the **last** batch (after all content operations) so that start/end indices are stable.

---

## Named Range Uniqueness — Clarification

Two `> [!WARNING]` callouts in the same document both get the named range name `extradoc:callout:warning`. The Google Docs API stores them under the same key but as separate `NamedRange` objects:

```json
"extradoc:callout:warning": {
  "name": "extradoc:callout:warning",
  "namedRanges": [
    { "namedRangeId": "id-alpha", "ranges": [{"startIndex": 42, "endIndex": 108}] },
    { "namedRangeId": "id-beta",  "ranges": [{"startIndex": 210, "endIndex": 290}] }
  ]
}
```

`_build_named_range_index` iterates the inner `namedRanges` list and indexes both entries by their `startIndex`. Both callouts pull correctly. No UUID suffix or counter in the name is needed.

---

## Inline Code: No Named Range Needed

Inline code spans (`` `code` ``) map to `TextRun.textStyle.weightedFontFamily = "Courier New"`. This is a text-level style, not a structural element, so it round-trips as a text style property — no named range annotation required.

---

## File Change Summary

| File | What changes |
|---|---|
| `serde/_special_elements.py` | **New.** `SpecialElement` ABC + `CodeBlock`, `Callout`, `Blockquote` + `special_element_from_named_range()` factory |
| `serde/_from_markdown.py` | Handle `CodeFence`, `Quote`, `InlineCode` tokens; call typed `.to_table()`; embed named ranges in Document before returning |
| `serde/_to_markdown.py` | `_build_named_range_index()`; route annotated tables to `special_element_from_named_range(...).to_markdown()`; inline code detection; relative URL fix |
| `reconcile/_core.py` | `_diff_named_ranges()` appended to final batch |
| `tests/test_serde_markdown.py` | `TestMarkdownSpecialBlocks` — see below |

---

## Tests

`TestMarkdownSpecialBlocks` in `tests/test_serde_markdown.py`:

| Test | What it checks |
|---|---|
| `test_code_fence_push` | CodeFence token → CodeBlock.to_table() has Courier New + #f3f3f3 + named range in DocumentTab |
| `test_callout_push` | `> [!WARNING]\n> text` → Callout table with #fff3cd bg + named range |
| `test_blockquote_push` | `> text` → Blockquote table with #f9f9f9 bg + left border + named range |
| `test_code_fence_pull` | Document with 1×1 table + `extradoc:codeblock:python` named range → ` ```python\n...\n``` ` |
| `test_callout_pull` | Same pattern for callout |
| `test_no_named_range_stays_table` | 1×1 table with no named range → regular GFM table, not a code block |
| `test_multiple_same_type` | Two `extradoc:callout:warning` named ranges at different positions → both pull as `> [!WARNING]` |
| `test_inline_code_round_trip` | `` `print()` `` → Courier New TextRun → back to `` `print()` `` |
| `test_relative_url` | `[LICENSE](LICENSE)` stored by API as `http://LICENSE` → pulled as `[LICENSE](LICENSE)` |
| `test_named_range_diff_insert` | reconcile with new CallOut in desired → createNamedRange in output requests |
| `test_named_range_diff_delete` | reconcile with CallOut removed from desired → deleteNamedRange in output requests |

---

## Deferred

- Type change in place (code block → callout at same position): delete old named range + create new. Edge case; deferred.
- Rich content inside callouts/blockquotes (nested lists, tables). v1 supports paragraphs only.
- Nested blockquotes (`> > text`): flattened to single level in v1.
