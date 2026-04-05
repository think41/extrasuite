# Serde Testing Philosophy

## The contract

The serde has two operations:

1. **serialize**: We have a `DocumentWithComments`, and we convert it to a folder
   of files representing this `DocumentWithComments`.
2. **deserialize**: We read the folder again. We had carefully captured the
   pristine state. We figure out what changed since we serialized. To do this,
   we first load the clean serialized state as a `DocumentWithComments` and call
   it "base". Then we figure out what changed, and carefully apply those changes
   to this base. The net result is a "desired" `DocumentWithComments`. We return
   that.

Between serialize and deserialize, someone else (not us) edits the files in the
folder. The serde's job is to detect exactly what changed and produce a desired
document that reflects those changes — and nothing else.

## The test pattern

Every test follows the same black-box workflow:

1. Load a starting point `document.json` — call this **base**. This is a real
   Google Docs API response, not a hand-crafted object.
2. **Serialize** it to a folder.
3. **Edit** the files in the folder (the way an external editor would).
4. **Deserialize** the folder.
5. Assert that:
   - **(a)** Only what we edited shows up as changed in desired.
   - **(b)** Whatever we didn't edit stays the same.

We test at the boundary of the public interface. No testing internals. Each test
starts with a `DocumentWithComments`, calls `serialize`, makes edits it knows
about, calls `deserialize`, and asserts on the resulting `DocumentWithComments`.

## The "nothing else changed" assertion

Part (b) is tricky only if you do it manually in every test. Instead, we have a
test helper — `assert_preserved` — that handles this automatically:

- It compares `base` vs `desired` after stripping indices (which shift whenever
  content changes).
- For tabs that were not edited, it asserts the full tab is identical.
- For edited tabs, it asserts all non-body fields (`documentStyle`,
  `namedStyles`, `headers`, `footers`, `inlineObjects`, etc.) are identical.
- It filters out synthetic list definitions (`kix.md_list_*`) that the markdown
  parser injects — these are an implementation detail, not a user edit.

The test only needs to assert what changed. The helper confirms nothing else did.

## Starting point documents

We use real Google Docs API responses as starting points — golden
`document.json` files pulled from actual documents. The point is: even if they
are huge, we only need to make small targeted edits depending on what we are
testing. The helper confirms nothing else changed, while the test focuses on
what changed.

To create a new golden document:

```bash
uvx extrasuite@latest doc create "Title" /tmp/fixture
# ... populate via push cycles ...
uvx extrasuite@latest doc pull <doc-id> /tmp/fixture
# Copy .raw/document.json to tests/golden/<doc-id>.json
```

Do not use `markdown_to_document()` or hand-craft Pydantic models as starting
points. The starting document should be a real API response with all the quirks
and structure that the real API produces.

## The 3-way merge guarantee

The markdown format is inherently lossy — it cannot represent everything in a
Google Doc. But that is not a bug. The 3-way merge design ensures that things
markdown doesn't understand pass through untouched.

The core idea: the document has an HR, but the markdown serde doesn't understand
HRs. So it either won't show the HR in markdown, or it won't allow you to
delete or modify it. When we deserialize, both the pristine snapshot and the
current folder have the same lossy representation of the HR. The diff between
them produces zero ops for the HR. So the HR survives in desired — it comes
straight from base.

**Desired will never touch things it doesn't understand.** That is the design
and intention. Tests are meant to assert this, not work around it.

## What not to test

- **Code blocks, callouts, blockquotes** — these are special elements backed by
  named ranges. They are not mature and should not be tested here.
- **Internals** — do not test private functions, intermediate representations,
  or how the diff is computed. Test the contract: serialize → edit → deserialize
  → assert.

## Test organization

Tests are grouped by the type of edit an external editor can make:

| Category | What it tests |
|----------|--------------|
| No-op round-trip | Serialize then immediately deserialize — desired equals base |
| Paragraph edits | Edit, add, delete plain paragraphs |
| Heading edits | Edit text, change level, add headings |
| Formatting edits | Add/remove bold, italic; preserve underline, strikethrough |
| Link edits | Add, edit, remove hyperlinks |
| List edits | Edit, add, delete bullet and numbered list items |
| Table edits | Edit cells, add rows |
| Multi-tab | Edit one tab, verify others are untouched |
| Preservation | documentStyle, namedStyles, list definitions, HRs, heading IDs |
| Footnotes | Add footnotes via markdown syntax |
| Comments | Edit comments.xml — resolved, replies |
| Edge cases | Identity edits, whitespace, multiple edits in one tab |
