# Skill Customization Guide

Every organization has unique workflows and requirements. This guide explains how to customize ExtraSuite skills for your organization's specific needs.

## Why Customize Skills?

Default skills provide general-purpose functionality, but your organization may need:

- **Domain-specific workflows** - Financial models, HR processes, inventory systems
- **Custom utilities** - Functions specific to your data structures
- **Organization standards** - Naming conventions, formatting rules
- **Integration patterns** - Connections to internal systems

## Skill Architecture

Understanding the skill structure helps you customize effectively:

```
gsheets/
├── SKILL.md           # Instructions for the AI agent
├── checks.py          # Environment verification
├── verify_access.py   # Access verification
├── gsheet_utils.py    # Utility functions
├── requirements.txt   # Python dependencies
└── venv/              # Virtual environment
```

### SKILL.md

This is the "brain" of the skill - it tells the AI agent:

- How to initialize the environment
- What workflow to follow
- Available functions and their usage
- Best practices and constraints

### Utility Functions

`gsheet_utils.py` contains helper functions that extend the standard library. These are where you add custom functionality.

## Customization Options

### Level 1: Prompting Guidelines

The simplest customization - add organization-specific prompting guidelines to `SKILL.md`:

```markdown
## Organization Standards

### Naming Conventions
- All new sheets should be prefixed with department code (FIN_, HR_, ENG_)
- Date columns must use YYYY-MM-DD format
- Currency columns must use format: $#,##0.00

### Required Headers
Every data table must include:
- `created_date` - When the row was created
- `created_by` - Email of creator
- `last_modified` - Last modification timestamp
```

### Level 2: Custom Functions

Add organization-specific utility functions to `gsheet_utils.py`:

```python
# Add to gsheet_utils.py

def create_standard_report_sheet(spreadsheet, name, headers):
    """
    Create a new worksheet with organization-standard formatting.

    Args:
        spreadsheet: gspread Spreadsheet object
        name: Name for the new worksheet
        headers: List of column headers

    Returns:
        gspread Worksheet object
    """
    ws = spreadsheet.add_worksheet(title=name, rows=1000, cols=len(headers))

    # Add headers
    ws.update('A1', [headers])

    # Format headers (bold, centered, colored background)
    ws.format('1:1', {
        'textFormat': {'bold': True},
        'horizontalAlignment': 'CENTER',
        'backgroundColor': {'red': 0.2, 'green': 0.4, 'blue': 0.8}
    })

    # Freeze header row
    ws.freeze(rows=1)

    # Add standard columns if not present
    if 'created_date' not in headers:
        ws.update_acell(f'{chr(65 + len(headers))}1', 'created_date')

    return ws


def apply_finance_formatting(ws, currency_columns, percentage_columns):
    """
    Apply finance-standard formatting to specified columns.

    Args:
        ws: gspread Worksheet object
        currency_columns: List of column letters for currency format
        percentage_columns: List of column letters for percentage format
    """
    for col in currency_columns:
        ws.format(f'{col}:{col}', {
            'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'}
        })

    for col in percentage_columns:
        ws.format(f'{col}:{col}', {
            'numberFormat': {'type': 'PERCENT', 'pattern': '0.00%'}
        })


def validate_data_structure(ws, expected_headers):
    """
    Validate that a worksheet has the expected structure.

    Args:
        ws: gspread Worksheet object
        expected_headers: List of required column headers

    Returns:
        dict with 'valid' (bool) and 'missing' (list of missing headers)
    """
    actual_headers = ws.row_values(1)
    missing = [h for h in expected_headers if h not in actual_headers]

    return {
        'valid': len(missing) == 0,
        'missing': missing,
        'actual': actual_headers
    }
```

Then update `SKILL.md` to document the new functions:

```markdown
## Custom Utilities

### create_standard_report_sheet(spreadsheet, name, headers)

Create a new worksheet with organization-standard formatting:

```python
from gsheet_utils import create_standard_report_sheet

ws = create_standard_report_sheet(
    spreadsheet=sheet,
    name="Q4 Report",
    headers=["Date", "Product", "Revenue", "Units"]
)
```

### apply_finance_formatting(ws, currency_columns, percentage_columns)

Apply finance-standard number formatting:

```python
from gsheet_utils import apply_finance_formatting

apply_finance_formatting(
    ws=ws,
    currency_columns=['C', 'D', 'E'],
    percentage_columns=['F', 'G']
)
```
```

### Level 3: Custom Workflows

Create organization-specific workflow patterns in `SKILL.md`:

```markdown
## Standard Workflows

### Monthly Financial Close

When asked to prepare monthly close data:

1. **Validate structure** - Ensure all required columns exist
2. **Check for errors** - Scan for #REF!, #DIV/0!, etc.
3. **Apply formatting** - Use finance formatting for currency/percentage
4. **Add summary row** - Insert totals at bottom with formulas
5. **Create pivot** - Generate summary pivot in new sheet
6. **Freeze and protect** - Lock header row and formula cells

```python
# Example monthly close workflow
from gsheet_utils import (
    open_sheet, validate_data_structure,
    apply_finance_formatting, create_standard_report_sheet
)

sheet = open_sheet(url)
ws = sheet.worksheet("Transactions")

# Step 1: Validate
validation = validate_data_structure(ws, [
    "Date", "Account", "Debit", "Credit", "Description"
])
if not validation['valid']:
    raise ValueError(f"Missing columns: {validation['missing']}")

# Step 2-6: Continue with workflow...
```

### HR Data Export

When exporting HR data:

1. **Check permissions** - Verify requester is in HR department
2. **Anonymize PII** - Remove SSN, replace names with IDs
3. **Apply filters** - Only include active employees
4. **Add audit trail** - Log who exported what and when
```

### Level 4: Custom Skills

For major customizations, create a new skill entirely:

```
skills/
├── gsheets/           # Standard skill
└── finance-sheets/    # Custom finance skill
    ├── SKILL.md
    ├── checks.py
    ├── verify_access.py
    ├── finance_utils.py
    └── requirements.txt
```

## Deployment Options

### Option 1: Local Override

Override skills locally for individual users:

```bash
# Copy default skill
cp -r ~/.claude/skills/gsheets ~/.claude/skills/gsheets-backup

# Edit SKILL.md and gsheet_utils.py
nano ~/.claude/skills/gsheets/SKILL.md
nano ~/.claude/skills/gsheets/gsheet_utils.py
```

### Option 2: Organization Repository

Host customized skills in an organization repository:

```bash
# Organization install script (install-org-skills.sh)
#!/bin/bash

# Download organization-customized skills
SKILL_URL="https://internal-repo.company.com/extrasuite-skills"

curl -fsSL "$SKILL_URL/gsheets.tar.gz" | tar -xz -C ~/.claude/skills/
```

### Option 3: Fork and Customize

Fork the ExtraSuite repository and customize:

1. Fork `github.com/think41/extrasuite`
2. Modify `skills/gsheets/SKILL.md` and utilities
3. Update install endpoints in your ExtraSuite deployment
4. Deploy your customized version

### Option 4: Skill Server

Build a skill distribution server:

```python
# Example skill server endpoint
@app.get("/api/skills/install/{token}")
async def install_skill(token: str, org: str = None):
    # Validate token
    user = validate_token(token)

    # Get organization-specific skill files
    if org and org in CUSTOM_SKILLS:
        skill_files = load_custom_skill(org)
    else:
        skill_files = load_default_skill()

    # Return install script with customized skills
    return generate_install_script(skill_files)
```

## Best Practices

### 1. Document Everything

Every custom function needs clear documentation:

```python
def my_custom_function(ws, param1, param2):
    """
    Brief description of what this function does.

    Args:
        ws: gspread Worksheet object
        param1: Description of param1
        param2: Description of param2

    Returns:
        Description of return value

    Raises:
        ValueError: When validation fails

    Example:
        result = my_custom_function(ws, "value1", 123)
    """
```

### 2. Maintain Compatibility

Custom skills should extend, not break, standard functionality:

```python
# Good: Extends standard behavior
def create_report(ws, **kwargs):
    # Custom pre-processing
    apply_org_standards(ws)

    # Standard operation
    standard_create_report(ws, **kwargs)

    # Custom post-processing
    add_audit_trail(ws)
```

### 3. Version Control

Track customizations with version numbers:

```markdown
# SKILL.md

---
name: gsheet
version: 1.2.0-acme
org: acme-corp
last_updated: 2024-01-15
---
```

### 4. Test Thoroughly

Create test spreadsheets to validate custom functions:

```python
# test_custom_functions.py
def test_create_standard_report_sheet():
    sheet = open_sheet(TEST_SPREADSHEET_URL)
    ws = create_standard_report_sheet(
        sheet, "Test", ["A", "B", "C"]
    )
    assert ws.acell('A1').value == "A"
    assert ws.frozen_row_count == 1
```

### 5. Provide Fallbacks

Custom functions should handle edge cases gracefully:

```python
def safe_apply_formatting(ws, column, format_type):
    try:
        apply_custom_formatting(ws, column, format_type)
    except Exception as e:
        # Fall back to standard formatting
        apply_standard_formatting(ws, column)
        log_warning(f"Custom formatting failed: {e}")
```

## Examples

### Finance Department Customization

```markdown
# SKILL.md additions for Finance

## Finance-Specific Functions

### create_budget_template(spreadsheet, fiscal_year)
Creates a standard budget template with:
- Monthly columns (Jan-Dec)
- Standard expense categories
- Variance formulas
- Conditional formatting for over/under budget

### reconcile_accounts(ws, gl_sheet)
Reconcile transactions against general ledger:
- Match by transaction ID
- Flag discrepancies
- Generate reconciliation report
```

### HR Department Customization

```markdown
# SKILL.md additions for HR

## HR Data Handling

### IMPORTANT: PII Protection
- NEVER export full SSN (use last 4 digits only)
- Replace names with employee IDs in exports
- Log all data access for compliance

### create_org_chart(ws, employees_data)
Generate organization chart from employee data:
- Hierarchy based on manager relationships
- Department groupings
- Headcount summaries
```

### Sales Department Customization

```markdown
# SKILL.md additions for Sales

## CRM Integration Patterns

### sync_from_salesforce(ws, report_id)
Pull Salesforce report data into worksheet:
- Map Salesforce fields to column headers
- Convert dates to organization standard
- Add sync timestamp

### calculate_commissions(ws, rates_sheet)
Calculate sales commissions:
- Look up rate by product category
- Apply tiered commission structure
- Generate payment summary
```

## Getting Help

For assistance with skill customization:

1. Review this guide and the [Skills Overview](../skills/index.md)
2. Examine the default `gsheet_utils.py` for patterns
3. Test changes in a development environment first
4. Contact your internal platform team for organization-specific guidance
