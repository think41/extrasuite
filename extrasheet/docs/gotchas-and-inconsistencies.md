# ExtraSheet Gotchas and Inconsistencies

This document catalogs surprising behaviors, inconsistencies, and common pitfalls discovered while using ExtraSheet. These were encountered while building a comprehensive demo spreadsheet.

---

## 1. Color Format Inconsistencies (Major Gotcha)

**The same property name requires different formats depending on context:**

| Location | Property | Expected Format | Example |
|----------|----------|-----------------|---------|
| `formatRules[].format.backgroundColor` | backgroundColor | Hex string | `"#E6E6E6"` |
| `conditionalFormats[].gradientRule.*.color` | color | RGB dict | `{"red": 0.96, "green": 0.8, "blue": 0.8}` |
| `conditionalFormats[].booleanRule.format.backgroundColor` | backgroundColor | RGB dict | `{"red": 0.8, "green": 0.96, "blue": 0.8}` |
| `formatRules[].format.textFormat.foregroundColor` | foregroundColor | RGB dict | `{"red": 1.0, "green": 1.0, "blue": 1.0}` |

**Why this is confusing:** The documentation (`on-disk-format.md`) shows RGB dicts for `backgroundColor` in examples, but the code at `request_generator.py:673` calls `_hex_to_rgb()` which expects hex strings for `formatRules`.

**Error encountered:** `'dict' object has no attribute 'lstrip'` - completely unhelpful for diagnosing the issue.

---

## 2. Format.json Structure Mismatch

**Wrong structure:**
```json
{
  "cells": {
    "A1": {"textFormat": {"bold": true}},
    "B1": {"backgroundColor": {"red": 0.9, ...}}
  }
}
```

**Correct structure:**
```json
{
  "formatRules": [
    {
      "range": "A1",
      "format": {"textFormat": {"bold": true}}
    }
  ]
}
```

**Error:** `'dict' object has no attribute 'lstrip'` - same unhelpful error, different cause.

---

## 3. Formula.json Structure Mismatch

**Wrong structure:**
```json
{
  "formulas": {
    "C5": "=A5+B5",
    "B14": "=SUM(B10:G10)"
  }
}
```

**Correct structure:** Flat dict without wrapper:
```json
{
  "C5": "=A5+B5",
  "B14": "=SUM(B10:G10)"
}
```

**Error:** Same `'dict' object has no attribute 'lstrip'`

---

## 4. Unsupported Data Validation Types

The following validation types are NOT supported by the Google Sheets API despite appearing in some documentation:
- `TEXT_IS_VALID_EMAIL`
- `TEXT_IS_VALID_URL`

**Error:** `API error (400): Invalid value at 'requests[X].setDataValidation.rule.condition.type'`

**Workaround:** Use custom formulas or remove these validation rules.

---

## 5. Pristine State Management

**Surprising behavior:** After successfully pushing changes, the `.pristine/spreadsheet.zip` is NOT automatically updated.

**Consequence:** If you try to push additional changes, the diff compares against the OLD pristine state and may try to create sheets that already exist.

**Error:** `Sheet with id XXXX already exists`

**Workaround:** Re-pull the entire spreadsheet to update the pristine state before making additional changes.

---

## 6. Sheet IDs Change After Push

**Surprising behavior:**
- Original `spreadsheet.json` might specify `sheetId: 0, 100, 200, 300...`
- After push and re-pull, Google may assign different IDs: `1101, 1102, 1103...`

**Impact:** Charts, filters, and other features reference sheets by `sheetId`. You must update all references after re-pull.

**Gotcha:** You cannot rely on the sheetIds you specify - Google may reassign them.

---

## 7. Index Numbering Inconsistencies

| Context | Indexing | Example |
|---------|----------|---------|
| data.tsv display | 1-based (line numbers) | Line 5 is row 5 |
| A1 notation | 1-based | A1, B2, etc. |
| GridRange in JSON | 0-based | `startRowIndex: 0` = row 1 |
| Range end indices | Exclusive | `endRowIndex: 10` means rows 0-9 |

**Gotcha:** When data.tsv shows content on line 5, the JSON `startRowIndex` should be 4 (0-based).

---

## 8. Error Messages Are Unhelpful

The error `'dict' object has no attribute 'lstrip'` is encountered for multiple different root causes:
1. Wrong format.json structure (cells dict vs formatRules array)
2. Wrong formula.json structure (nested vs flat)
3. Wrong color format (RGB dict vs hex string)

**No indication of:**
- Which file caused the error
- Which field has the wrong type
- What the expected format should be

---

## 9. Module Invocation Path Sensitivity

**Works:**
```bash
cd extrasheet
uv run python -m extrasheet pull ...
```

**May not work from parent directory:**
```bash
cd extrasuite
uv run python -m extrasheet pull ...
# Error: No module named extrasheet.__main__
```

**Workaround:** Run from the extrasheet directory, or use relative paths from there.

---

## 10. Documentation vs Implementation Gaps

**on-disk-format.md shows:**
```json
{
  "range": "A2:A23",
  "format": {
    "backgroundColor": { "red": 1, "green": 0.85, "blue": 0.85 }
  }
}
```

**But request_generator.py expects hex strings for formatRules backgroundColor.**

This is a direct contradiction between documentation and implementation.

---

## 11. Conditional Format Rule Index Requirement

Each conditional format requires a `ruleIndex` field:
```json
{
  "conditionalFormats": [
    {
      "ruleIndex": 0,
      "ranges": ["A1:A10"],
      "gradientRule": {...}
    }
  ]
}
```

This determines the order rules are applied and isn't obvious from the documentation.

---

## 12. Charts JSON Structure Varies by Type

The chart spec structure differs by chart type:

**Basic charts (bar, line, scatter, area):**
```json
{
  "spec": {
    "basicChart": {
      "chartType": "BAR",
      "domains": [...],
      "series": [...]
    }
  }
}
```

**Pie charts:**
```json
{
  "spec": {
    "pieChart": {
      "domain": {...},
      "series": {...}
    }
  }
}
```

Note: `domains` (plural array) vs `domain` (singular object), and `series` as array vs object.

---

## 13. Tab Colors May Not Be Applied

Tab colors specified in `spreadsheet.json` via `tabColorStyle` may not be applied during push. The mechanism for setting tab colors may require a different approach.

---

## 14. Formula Errors in Data

Formulas that reference header rows will produce errors if the headers contain text. Ensure formula ranges start from data rows, not header rows.

**Example error in preview:**
```
"Function ADD parameter 1 expects number values. But 'Value A' is a text..."
```

---

## 15. No Pre-flight Validation

There's no validation before push to catch:
- Invalid color formats
- Invalid data validation types
- Malformed JSON structures
- Sheet ID conflicts

Issues are only discovered when the API returns a 400 error, sometimes after partial changes have been applied.

---

## Summary Table

| Category | Issue | Severity |
|----------|-------|----------|
| Color formats | Same property, different formats by context | High |
| Error messages | Unhelpful, same error for different causes | High |
| Documentation | Contradicts implementation | High |
| Pristine state | Not updated after push | Medium |
| Sheet IDs | Reassigned by Google | Medium |
| Structure | formatRules vs cells dict | Medium |
| Structure | Nested vs flat formula.json | Medium |
| Validation types | EMAIL/URL not supported | Medium |
| Index numbering | Mixed 0-based and 1-based | Low |
| Chart specs | Inconsistent by chart type | Low |

---

## Recommendations

1. **Improve error messages** - Include file path, field name, and expected format in error messages
2. **Update documentation** - Ensure on-disk-format.md matches implementation (hex strings for formatRules backgroundColor)
3. **Add validation** - Pre-flight validation before push to catch common errors
4. **Update pristine after push** - Consider automatically updating .pristine after successful push
5. **Document sheet ID behavior** - Clarify that Google may reassign sheet IDs
6. **Unify color formats** - Consider accepting both hex strings and RGB dicts everywhere
