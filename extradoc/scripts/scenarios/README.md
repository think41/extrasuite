# Recording Mode Scenarios

This directory contains example scenarios for testing the mock API against the real Google Docs API using recording mode.

## What is Recording Mode?

Recording mode is a testing infrastructure that:
1. Pulls a Google Doc
2. Edits it using Claude Code (per your instructions)
3. Pushes the changes using both the real API and mock API
4. Compares the results and logs any mismatches

This helps validate that the mock API (`mock_api.py`) accurately simulates the real Google Docs API behavior.

## How to Run a Scenario

### Prerequisites

1. Install extrasuite/extradoc:
   ```bash
   cd /home/user/extrasuite/extradoc
   uv sync
   ```

2. Install Claude Code CLI (if testing with automatic edits)

3. Authenticate with Google:
   ```bash
   extrasuite doc login
   ```

4. Create a test Google Doc and share it with your service account

### Run a Scenario

```bash
cd /home/user/extrasuite/extradoc

# Basic text insertion
uv run python scripts/record_scenario.py \
  "https://docs.google.com/document/d/YOUR_DOC_ID/edit" \
  "Add a new paragraph at the end with the text 'Testing mock API'"

# With custom output directories
uv run python scripts/record_scenario.py \
  "https://docs.google.com/document/d/YOUR_DOC_ID/edit" \
  "Add a heading with text 'Chapter 1'" \
  --output-dir ./test_output \
  --mismatch-dir ./test_mismatches
```

### Manual Editing (without Claude Code)

If you prefer to edit manually instead of using Claude Code:

```bash
# 1. Pull the document
extrasuite doc pull https://docs.google.com/document/d/YOUR_DOC_ID/edit

# 2. Manually edit document.xml in YOUR_DOC_ID/document.xml

# 3. Use a Python script with CompositeTransport to push:
```

```python
import asyncio
from pathlib import Path
from extradoc.client import DocsClient
from extradoc.composite_transport import CompositeTransport, MismatchLogger
from extradoc.transport import GoogleDocsTransport

async def main():
    access_token = "YOUR_TOKEN"
    doc_folder = Path("YOUR_DOC_ID")

    real_transport = GoogleDocsTransport(access_token)
    mismatch_logger = MismatchLogger(Path("mismatches"))
    composite = CompositeTransport(real_transport, mismatch_logger)
    client = DocsClient(composite)

    result = await client.push(doc_folder)
    print(mismatch_logger.get_summary())
    await composite.close()

asyncio.run(main())
```

## Example Scenarios

### 1. Simple Text Operations

**Scenario:** Insert, delete, and style text

**Setup:**
- Create a doc with: "Hello World"

**Instructions:**
```
1. Change "Hello" to "Goodbye"
2. Make "World" bold
3. Add a new line with "Testing 123"
```

**Expected:** Mock API should handle:
- deleteContentRange
- insertText
- updateTextStyle

### 2. Paragraph Formatting

**Scenario:** Create headings and styled paragraphs

**Setup:**
- Create a doc with plain text

**Instructions:**
```
Convert the first line to a Heading 1
Add a new paragraph with text "This is body text"
```

**Expected:** Mock API should handle:
- updateParagraphStyle (headingId)

### 3. Lists

**Scenario:** Create and modify bulleted/numbered lists

**Setup:**
- Create a doc with several paragraphs

**Instructions:**
```
Convert the first 3 paragraphs into a bulleted list
```

**Expected:** Mock API should handle:
- createParagraphBullets

### 4. Tables

**Scenario:** Insert and modify tables

**Setup:**
- Create a doc with text

**Instructions:**
```
Insert a 2x3 table after the first paragraph
Fill the first row with: "Name", "Age", "City"
```

**Expected:** Mock API should handle:
- insertTable
- insertText in table cells

### 5. Headers and Footers

**Scenario:** Create headers and footers

**Setup:**
- Create a blank doc

**Instructions:**
```
Add a header with the text "Company Name"
Add a footer with "Page X"
```

**Expected:** Mock API should handle:
- createHeader
- createFooter
- Proper segment ID generation and mapping

### 6. Complex Document

**Scenario:** Multiple operations in sequence

**Setup:**
- Create a doc with mixed content

**Instructions:**
```
1. Add a heading "Introduction"
2. Add a paragraph below it
3. Insert a 3x3 table
4. Add a bulleted list
5. Create a header with current date
```

**Expected:** All mock operations work correctly together

## Analyzing Mismatches

When a mismatch is detected, the script logs detailed information:

```
mismatch_logs/
  batch_update_mismatch_20260213_143052_1/
    metadata.json              # Timestamp, operation type, doc ID
    input_document.json        # Document state before update
    requests.json              # The batchUpdate requests sent
    real_response.json         # Response from real API
    mock_response.json         # Response from mock API
    real_document_after.json   # Document state after real API
    mock_document_after.json   # Document state after mock API
```

### Common Mismatch Patterns

1. **ID Generation Differences**
   - Real API: `kix.abc123xyz`
   - Mock API: `mock_id_1`
   - **Solution:** Normalize IDs in comparison

2. **Missing Fields**
   - Real API includes metadata fields
   - Mock API might omit them
   - **Solution:** Update mock to include these fields

3. **Index Calculation Errors**
   - UTF-16 encoding differences (emoji, special chars)
   - **Solution:** Fix indexer in mock_api.py

4. **Structural Validation**
   - Real API rejects invalid operations
   - Mock API might allow them
   - **Solution:** Add validation to mock_api.py

## Best Practices

1. **Start Simple:** Test basic operations before complex scenarios
2. **Isolate Features:** Test one API feature per scenario
3. **Use Clean Docs:** Start with simple, predictable document states
4. **Document Findings:** Note any mismatches and their root causes
5. **Iterate:** Fix mock_api.py and re-run scenarios

## Contributing Scenarios

To add a new scenario:

1. Create a Google Doc with the necessary setup
2. Document the starting state
3. Write clear instructions
4. Run the scenario and verify results
5. Add to this README with expected behavior

## Troubleshooting

**"claude-code command not found"**
- Install Claude Code CLI or edit XMLs manually

**"Failed to get access token"**
- Run `extrasuite doc login` first

**"Document not found"**
- Ensure doc is shared with your service account
- Check URL format

**"Mock API error but real API succeeded"**
- This is a bug in mock_api.py - log it as a mismatch
- Review the error details in mismatch logs
