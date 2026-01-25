# ExtraSheet Design Decisions

This document explains the key design decisions made in the ExtraSheet file format and the rationale behind each choice.

---

## Table of Contents

1. [Why Multiple Files per Sheet?](#why-multiple-files-per-sheet)
2. [Why TSV for Data?](#why-tsv-for-data)
3. [Why Sparse JSON for Formulas?](#why-sparse-json-for-formulas)
4. [Why Range-Based Formatting?](#why-range-based-formatting)
5. [Why Not SQLite?](#why-not-sqlite)
6. [Why Not XML/SML Like Extraslide?](#why-not-xmlsml-like-extraslide)
7. [Comparison with Alternatives](#comparison-with-alternatives)
8. [Trade-offs Acknowledged](#trade-offs-acknowledged)

---

## Why Multiple Files per Sheet?

### Decision

Each Google Sheet is represented as a directory with multiple files:
- `data.tsv` - Cell values
- `formulas.json` - Cell formulas (sparse)
- `format.json` - Cell formatting
- `features.json` - Charts, pivots, etc.

### Rationale

1. **Separation of Concerns**: Different aspects of a spreadsheet change for different reasons:
   - Data changes frequently (user input)
   - Formulas change occasionally (logic updates)
   - Formatting changes rarely (design updates)
   - Features change rarely (report structure)

2. **Minimal Diffs**: When you change a cell value, only `data.tsv` changes. The diff is clean and obvious.

3. **Parallel Editing**: Multiple agents or users can work on different layers without conflicts:
   - One agent updates data
   - Another adjusts formatting
   - No conflicts unless both touch the same layer

4. **Selective Sync**: You can pull just data without formatting, or push just formatting updates.

5. **Human Readability**: Each file has a single purpose and is easy to understand in isolation.

### Alternatives Considered

- **Single JSON file**: Rejected because changes to any aspect would show as changes to the whole file, making diffs noisy.
- **Single XML file**: Same problem as JSON, plus XML is more verbose.
- **Database (SQLite)**: See [Why Not SQLite?](#why-not-sqlite)

---

## Why TSV for Data?

### Decision

Cell values are stored as tab-separated values (TSV) in `data.tsv`.

### Rationale

1. **Universal Familiarity**: TSV is understood by everyone. Open it in any text editor, and you see your data.

2. **Trivial Parsing**: Every programming language can parse TSV. No special libraries needed.

3. **Git-Friendly**: TSV files produce clean, line-by-line diffs:
   ```diff
   -Alice	28	Engineer
   +Alice	29	Engineer
   ```

4. **AI-Agent Friendly**: LLMs can read and write TSV without special instructions. It's just text with tabs.

5. **Spreadsheet Import/Export**: Every spreadsheet tool can import/export TSV.

6. **Compact**: No structural overhead (no braces, quotes, commas for every cell).

### Why Not CSV?

CSV has ambiguity issues:
- Some tools use `;` as delimiter
- Quoting rules vary
- Excel uses locale-specific settings

TSV is unambiguous: tabs separate columns, newlines separate rows.

### Limitations Accepted

- Binary data: Not supported (use Base64 if needed)
- Multi-line text: Requires escaping (`\n`)
- Very long cells: Work fine, but less readable

---

## Why Sparse JSON for Formulas?

### Decision

Formulas are stored as a sparse JSON object mapping cell addresses to formulas:

```json
{
  "D2": "=B2*C2",
  "D5": "=SUM(D2:D4)"
}
```

### Rationale

1. **Most Cells Don't Have Formulas**: In a typical spreadsheet, <10% of cells contain formulas. Storing every cell would be wasteful.

2. **Clear Formula Identification**: You can instantly see which cells have formulas and what they are.

3. **Easy Updates**: Adding a formula is adding a key. Removing one is deleting a key.

4. **No Coupling with Values**: Formula changes don't affect `data.tsv` (except for the expected result).

5. **Preserves Original Formulas**: The exact formula as entered is preserved, including:
   - Absolute/relative references (`$A$1` vs `A1`)
   - Named ranges
   - Cross-sheet references

### Why Not Embed in data.tsv?

If formulas were in `data.tsv`, you couldn't distinguish:
- Cell with value `=SUM(A:A)` (text)
- Cell with formula `=SUM(A:A)` (formula)

And changing a formula would change the data file, mixing concerns.

### Why JSON, Not YAML?

- JSON is more widely supported
- No indentation ambiguity
- Easier to generate and parse programmatically

---

## Why Range-Based Formatting?

### Decision

Formatting is specified as an ordered list of range-based rules:

```json
{
  "rules": [
    {"range": "A1:Z1", "format": {"bold": true}},
    {"range": "B2:B100", "format": {"numberFormat": {"type": "CURRENCY"}}}
  ]
}
```

### Rationale

1. **How Humans Think**: People format ranges, not individual cells. "Make the header row bold" → format `A1:Z1`.

2. **Compact Representation**: One rule can style thousands of cells. Per-cell formatting would be massive.

3. **Matches Google Sheets Model**: The Sheets API uses ranges for formatting. Direct mapping = efficient.

4. **Cascading Behavior**: Later rules override earlier ones, like CSS. This is intuitive:
   ```json
   {"range": "A:A", "format": {"bold": true}},
   {"range": "A1", "format": {"bold": false}}  // Override for header
   ```

5. **Easy to Diff**: Adding a new rule adds one object. Changing a rule modifies one object.

### Alternatives Considered

- **Per-cell formatting**: Rejected because it's verbose and doesn't match how users think.
- **CSS-like selectors**: Interesting but would require a new syntax to learn.

### Trade-off: Overlapping Ranges

When ranges overlap, you need to understand the cascade. But this matches spreadsheet behavior anyway.

---

## Why Not SQLite?

### Decision

Cell data is stored as TSV, not in a SQLite database.

### Rationale

SQLite was seriously considered because:
- AI agents can query data with SQL
- Handles large datasets efficiently
- Supports complex queries

**However**, we chose TSV because:

1. **Transparency**: TSV is visible and editable without tools. SQLite is binary.

2. **Diff-ability**: TSV produces readable diffs. SQLite changes are opaque.

3. **Simplicity**: No database connection, no schema, no migrations.

4. **Spreadsheets Aren't Databases**: Spreadsheets have:
   - Mixed types in columns
   - Formulas (not SQL expressions)
   - Formatting tied to cells
   - No primary keys

5. **Edit Experience**: Opening a `.sqlite` file requires a database tool. Opening `data.tsv` works anywhere.

6. **Conflict Resolution**: TSV line-by-line conflicts are easier to resolve than SQLite conflicts.

### When SQLite Might Be Better

If the use case is:
- Read-only analytics on large datasets
- Frequent complex queries
- No need for human editing

Then SQLite could be a better choice. But that's not the primary ExtraSheet use case.

### Hybrid Approach (Future)

We could support both:
- Default: TSV for human-editable sheets
- Optional: SQLite for large data-only sheets

This would be opt-in per sheet.

---

## Why Not XML/SML Like Extraslide?

### Decision

ExtraSheet uses JSON+TSV, not an XML-based markup like Extraslide's SML.

### Rationale

Extraslide uses XML because slides are:
- Hierarchical (slides → elements → text)
- Visual (position, rotation, styling)
- Relatively small (dozens of elements per slide)

Sheets are different:
- Tabular (rows × columns)
- Data-focused (values, formulas)
- Large (thousands of cells)

1. **Volume**: A 1000×26 sheet = 26,000 cells. XML for each cell would be:
   ```xml
   <Cell r="1" c="1" v="Hello"/>
   <Cell r="1" c="2" v="World"/>
   <!-- 25,998 more... -->
   ```
   Versus TSV:
   ```
   Hello	World	...
   ```

2. **Readability**: Tabular data is naturally... tabular. TSV preserves the table structure visually.

3. **Editing**: Adding a row in TSV = add a line. In XML = add 26 Cell elements with correct attributes.

4. **Different Mental Model**: Slides are "objects on a canvas." Sheets are "data in a grid."

### Could We Use XML for Features?

Yes, for charts and pivot tables, XML might be natural. But JSON is equally expressive and more widely used in modern tooling.

---

## Comparison with Alternatives

### Alternative 1: Google Sheets API JSON (Raw)

Store the full Sheets API response as JSON.

| Aspect | Raw JSON | ExtraSheet |
|--------|----------|------------|
| Human readable | No (complex nesting) | Yes (purpose-specific files) |
| Editable | Impractical | Easy |
| Diff quality | Noisy | Clean |
| Size | Large | Smaller |
| API mapping | Direct | Requires conversion |

### Alternative 2: Excel .xlsx (ZIP of XML)

Store sheets as .xlsx files.

| Aspect | .xlsx | ExtraSheet |
|--------|-------|------------|
| Standard | Industry standard | Custom |
| Human readable | No (binary ZIP) | Yes |
| Diff quality | Binary diff | Text diff |
| Google Sheets compat | Requires conversion | Native |
| AI editing | Needs special tools | Direct text editing |

### Alternative 3: CSV Only

Store just CSV files for each sheet.

| Aspect | CSV Only | ExtraSheet |
|--------|----------|------------|
| Simplicity | Simpler | More complex |
| Formulas | Lost | Preserved |
| Formatting | Lost | Preserved |
| Charts | Lost | Preserved |
| Round-trip | Lossy | Lossless |

### Alternative 4: Single JSON per Sheet

One JSON file containing data, formulas, and formatting.

| Aspect | Single JSON | ExtraSheet Multi-File |
|--------|-------------|----------------------|
| Atomicity | All or nothing | Per-aspect |
| Conflicts | Whole-file | Per-file |
| Diff noise | Any change shows | Only affected file |
| Simplicity | Simpler structure | More files |

---

## Trade-offs Acknowledged

### Complexity

**Trade-off**: Multiple files per sheet adds complexity.

**Mitigation**: Clear naming, consistent structure, tooling abstracts away file management.

### Sync Consistency

**Trade-off**: Files can get out of sync (e.g., formula references cell that doesn't exist in data).

**Mitigation**: Validation on push, warnings on inconsistencies.

### Not a Standard

**Trade-off**: ExtraSheet is a custom format, not an industry standard.

**Mitigation**:
- TSV is standard
- JSON is standard
- Conversion to/from Sheets is lossless
- Documentation is comprehensive

### Large Files

**Trade-off**: Very large sheets (100k+ rows) may have large TSV files.

**Mitigation**:
- Git handles text files well
- Could add compression option
- Could add SQLite option for data-only sheets

### Formula Execution

**Trade-off**: Formulas aren't evaluated locally (values in data.tsv are cached).

**Mitigation**:
- Push to Google Sheets for accurate calculation
- Document that data.tsv values may be stale after formula changes
- Future: Add local formula evaluation engine

---

## Conclusion

The ExtraSheet format is designed for a specific use case: enabling AI agents to read, understand, and edit Google Sheets through human-readable local files. Every design decision optimizes for:

1. **Clarity** - Easy to understand without documentation
2. **Editability** - Changes are simple text edits
3. **Diff-ability** - Git diffs are meaningful
4. **Separability** - Independent aspects can be modified independently
5. **Fidelity** - No information loss in the round-trip

These priorities shaped the multi-file, TSV+JSON format we arrived at.
