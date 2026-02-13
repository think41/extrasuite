# ExtraDoc Scripts

This directory contains utility scripts for extradoc development and testing.

## Recording Mode

### Overview

The recording mode infrastructure allows you to test the mock Google Docs API (`mock_api.py`) against the real API by running actual pull-edit-push workflows.

**Key Components:**

- **`record_scenario.py`** - Main script that executes pull-edit-push with recording
- **`CompositeTransport`** - Transport that calls both real and mock APIs
- **`MismatchLogger`** - Logs detailed information when APIs diverge
- **`scenarios/`** - Example test scenarios

### Quick Start

1. **Setup:**
   ```bash
   cd /home/user/extrasuite/extradoc
   uv sync
   extrasuite doc login
   ```

2. **Create a test document** in Google Docs and share it with your service account

3. **Run a scenario:**
   ```bash
   uv run python scripts/record_scenario.py \
     "https://docs.google.com/document/d/YOUR_DOC_ID/edit" \
     "Add a paragraph with text 'Testing mock API'"
   ```

4. **Check results:**
   - ✅ If no mismatches: Mock API matches real API perfectly
   - ⚠️ If mismatches: Review logs in `mismatch_logs/` directory

### How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                     record_scenario.py                       │
└────────────────────────┬────────────────────────────────────┘
                         │
           ┌─────────────┼─────────────┐
           │             │             │
        PULL          EDIT           PUSH
           │             │             │
           ▼             ▼             ▼
    ┌────────────┐  ┌─────────┐  ┌──────────────┐
    │ Real API   │  │ Claude  │  │ Composite    │
    │ get_doc    │  │ Code    │  │ Transport    │
    └────────────┘  │ (edit   │  └──────┬───────┘
                    │  XML)   │         │
                    └─────────┘         │
                                        │
                        ┌───────────────┴──────────────┐
                        │                              │
                        ▼                              ▼
                  ┌──────────┐                  ┌──────────┐
                  │ Real API │                  │ Mock API │
                  │ batch_   │                  │ batch_   │
                  │ update() │                  │ update() │
                  └─────┬────┘                  └────┬─────┘
                        │                            │
                        └──────────┬─────────────────┘
                                   │
                                   ▼
                            ┌──────────────┐
                            │  Compare     │
                            │  Results     │
                            └──────┬───────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
                    ▼                             ▼
              ✅ Match                    ⚠️ Mismatch
                                               │
                                               ▼
                                    ┌──────────────────┐
                                    │ Log to:          │
                                    │ - input_doc      │
                                    │ - requests       │
                                    │ - real_response  │
                                    │ - mock_response  │
                                    │ - real_doc_after │
                                    │ - mock_doc_after │
                                    └──────────────────┘
```

### Usage

#### Basic Usage

```bash
python scripts/record_scenario.py <doc_url> <instructions>
```

**Arguments:**
- `doc_url`: Google Docs URL (e.g., `https://docs.google.com/document/d/abc123/edit`)
- `instructions`: What edits to make (e.g., `"Add a heading 'Chapter 1'"`)

**Options:**
- `--output-dir DIR`: Where to save pulled documents (default: `scenario_output`)
- `--mismatch-dir DIR`: Where to save mismatch logs (default: `mismatch_logs`)

#### Examples

**Simple text insertion:**
```bash
python scripts/record_scenario.py \
  "https://docs.google.com/document/d/abc123/edit" \
  "Insert the text 'Hello World' at the beginning"
```

**Formatting:**
```bash
python scripts/record_scenario.py \
  "https://docs.google.com/document/d/abc123/edit" \
  "Make the first paragraph bold and convert the second to a Heading 1"
```

**Tables:**
```bash
python scripts/record_scenario.py \
  "https://docs.google.com/document/d/abc123/edit" \
  "Insert a 2x3 table with headers Name, Age, City"
```

### Analyzing Mismatches

When a mismatch is detected, detailed logs are saved:

```
mismatch_logs/
  batch_update_mismatch_20260213_143052_1/
    metadata.json              # Operation details
    input_document.json        # Doc before update
    requests.json              # batchUpdate requests
    real_response.json         # Real API response
    mock_response.json         # Mock API response
    real_document_after.json   # Real API result
    mock_document_after.json   # Mock API result
```

**Common Issues:**

1. **Index Calculation Errors**
   - UTF-16 encoding (emoji, special chars)
   - Solution: Check `extradoc/indexer.py`

2. **Missing Validation**
   - Real API rejects, mock allows
   - Solution: Add validation to `mock_api.py`

3. **ID Generation Differences**
   - Real: `kix.abc123`
   - Mock: `mock_id_1`
   - Solution: Normalize in comparison or update mock

### Pre-Built Scenarios

Run pre-built test scenarios:

```bash
# Simple text operations
./scripts/scenarios/01_simple_text.sh <doc_url>

# Heading formatting
./scripts/scenarios/02_headings.sh <doc_url>

# Bulleted lists
./scripts/scenarios/03_lists.sh <doc_url>

# Table operations
./scripts/scenarios/04_tables.sh <doc_url>
```

See `scenarios/README.md` for more details.

### Manual Testing (without Claude Code)

If you want to edit XML files manually:

1. **Pull the document:**
   ```bash
   extrasuite doc pull https://docs.google.com/document/d/abc123/edit
   ```

2. **Edit `abc123/document.xml` manually**

3. **Create a test script:**
   ```python
   import asyncio
   from pathlib import Path
   from extradoc.client import DocsClient
   from extradoc.composite_transport import CompositeTransport, MismatchLogger
   from extradoc.transport import GoogleDocsTransport

   async def test_push():
       token = "YOUR_ACCESS_TOKEN"
       real = GoogleDocsTransport(token)
       logger = MismatchLogger(Path("mismatches"))
       composite = CompositeTransport(real, logger)
       client = DocsClient(composite)

       result = await client.push(Path("abc123"))
       print(logger.get_summary())
       await composite.close()

   asyncio.run(test_push())
   ```

### Development Workflow

**When adding new features to mock_api.py:**

1. Create a test document with the feature you want to test
2. Run a recording scenario that exercises the feature
3. If mismatch detected:
   - Review the mismatch logs
   - Fix `mock_api.py`
   - Re-run the scenario
4. Once passing, add a unit test to `tests/test_mock_api.py`

**Benefits:**
- Validates mock against real API behavior
- Catches edge cases and validation issues
- Documents expected behavior with real examples
- Provides regression testing

### Troubleshooting

**"claude-code command not found"**
- Install Claude Code CLI, or
- Edit XML files manually and use Python script to push

**"Failed to get access token"**
- Run `extrasuite doc login`
- Or manually set token in script

**"Document not found (404)"**
- Ensure doc is shared with your service account
- Check that document ID in URL is correct

**"Mock API raised error but real API succeeded"**
- This is a bug in mock_api.py
- Review error details in mismatch logs
- Add missing validation or fix implementation

### Contributing

To add a new scenario:

1. Create a test document
2. Write a scenario script in `scenarios/`
3. Document expected behavior
4. Add to `scenarios/README.md`

See `scenarios/README.md` for guidelines.

## Other Scripts

(Add other script documentation here as needed)

## See Also

- [Mock API Documentation](../docs/mock-api.md)
- [Test Scenarios](./scenarios/README.md)
- [ExtraDoc Client API](../docs/client-api.md)
