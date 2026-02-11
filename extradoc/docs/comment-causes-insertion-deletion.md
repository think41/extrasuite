# Bug: Adding comment-ref causes spurious document changes

## Summary

When an agent adds a `<comment-ref>` tag around text in `document.xml`, the diff engine generates unnecessary `deleteContentRange` + `insertText` + `updateTextStyle` requests for that paragraph, even though the actual text content is unchanged. This causes the paragraph to be deleted and recreated on push, which can orphan comments that were anchored to that text.

## Steps to reproduce

1. Pull a document:
   ```
   extrasuite doc pull <doc_id> output/
   ```

2. Wrap existing text with a comment-ref tag. For example, change:
   ```xml
   <p><span class="_HTl6"><i>InnovateTech AI Labs, Bangalore</i></span></p>
   ```
   to:
   ```xml
   <p><span class="_HTl6"><i><comment-ref id="new_comment">InnovateTech AI Labs, Bangalore</comment-ref></i></span></p>
   ```

3. Add corresponding entry in `comments.xml`.

4. Run diff:
   ```
   extrasuite doc diff output/<doc_id>/
   ```

5. **Expected**: 0 document changes, 1 comment creation via Drive API
6. **Actual**: 6 document changes (delete paragraph, re-insert text, restyle) + 1 comment creation

## Example diff output

```
6 document requests (should be 0)
  [0] deleteContentRange: 1372-1404
  [1] insertText: idx=1372 text='InnovateTech AI Labs, Bangalore\n'
  [2] updateTextStyle: 1372-1404
  [3] updateParagraphStyle
  [4] deleteParagraphBullets
  [5] updateTextStyle: 1372-1403
```

## Root cause

The diff pipeline compares paragraph XML between pristine and current:

- **Pristine**: `<p><span class="_HTl6"><i>InnovateTech AI Labs, Bangalore</i></span></p>`
- **Current**: `<p><span class="_HTl6"><i><comment-ref id="new_comment">InnovateTech AI Labs, Bangalore</comment-ref></i></span></p>`

The XML is structurally different (extra `<comment-ref>` element), so the diff engine treats it as a modified paragraph and generates delete + insert requests. But `<comment-ref>` is purely an annotation — it doesn't change the rendered text, styles, or formatting. It should be invisible to the diff engine.

## Impact

1. **Performance**: Unnecessary API calls to delete and recreate unchanged text
2. **Comment orphaning**: When the paragraph text is deleted and recreated, existing comments anchored to that text range can become orphaned/deleted in the Google Docs UI
3. **Revision noise**: Each push creates unnecessary revision history entries

## Proposed fix

Strip `<comment-ref>` tags from both pristine and current XML before running the diff engine. Since `<comment-ref>` is zero-width (doesn't affect indexing — the `block_indexer` already treats it as transparent), removing it before diffing will make the diff engine see identical paragraphs and produce 0 changes.

The best place to do this is in `desugar.py`, in the `_extract_runs_recursive()` function. When encountering a `comment-ref` element, simply recurse into its children without emitting any tag — same as how unknown/transparent elements are handled. The `comment-ref` tag is already treated this way by `block_indexer.py` and `desugar.py`'s run extraction, but the **paragraph XML comparison** (which happens before run extraction) sees the structural difference.

Alternatively, strip `<comment-ref>` tags from the raw XML string before passing to the diff engine in `client.py:diff()`. This is simpler but less principled:

```python
import re
def _strip_comment_refs(xml: str) -> str:
    """Remove <comment-ref> tags but keep their content."""
    xml = re.sub(r'<comment-ref[^>]*>', '', xml)
    xml = re.sub(r'</comment-ref>', '', xml)
    return xml
```

The regex approach is safe because `<comment-ref>` never has child `<comment-ref>` tags in practice, and its attributes are simple strings without `>` characters.
