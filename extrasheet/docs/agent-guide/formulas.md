# Formulas Guide

## formula.json Structure

**Must be a flat dictionary** - NOT nested:

```json
{
  "A1": "=NOW()",
  "C2": "=A2+B2",
  "D2:D100": "=B2*C2",
  "E5": "=SUM(A1:A4)"
}
```

**Wrong:**
```json
{
  "formulas": {
    "A1": "=NOW()"
  }
}
```

## Range Compression

When contiguous cells share the same formula pattern, they're stored as a range:

```json
{
  "C2:C100": "=A2+B2"
}
```

This means:
- C2: `=A2+B2`
- C3: `=A3+B3`
- C4: `=A4+B4`
- ...and so on

**Relative references increment, absolute references (`$A$1`) stay fixed.**

## Adding/Modifying Formulas

### Single Cell
```json
{
  "B10": "=SUM(B2:B9)"
}
```

### Range with Auto-fill
```json
{
  "C2:C100": "=A2+B2"
}
```
Push will set C2, then auto-fill down.

### With Absolute References
```json
{
  "D2:D100": "=C2*$B$1"
}
```
$B$1 stays fixed; C2 becomes C3, C4, etc.

## Deleting Formulas

Remove the key from formula.json. The cell will retain its last computed value in data.tsv.

## Cross-Sheet References

```json
{
  "A1": "='Other Sheet'!B5",
  "B1:B10": "=SUM('Data Source'!A:A)"
}
```

## Named Ranges

Check `named_ranges.json` for available named ranges:
```json
{
  "A1": "=SUM(SalesData)",
  "B1": "=AVERAGE(Expenses)"
}
```

## Common Formula Patterns

```json
{
  "B10": "=SUM(B2:B9)",
  "C10": "=AVERAGE(C2:C9)",
  "D2:D100": "=IFERROR(B2/C2, 0)",
  "E2:E100": "=IF(D2>0.5, \"High\", \"Low\")",
  "F1": "=TODAY()",
  "G2:G100": "=VLOOKUP(A2, 'Lookup'!A:B, 2, FALSE)"
}
```

## Array Formulas

Rare, but if present they appear in an `arrayFormulas` section:
```json
{
  "A1": "=UNIQUE(Sheet2!A:A)",
  "arrayFormulas": {
    "A1": {
      "formula": "=UNIQUE(Sheet2!A:A)",
      "outputRange": "A1:A50"
    }
  }
}
```
