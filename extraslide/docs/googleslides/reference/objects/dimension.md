# Dimension

A magnitude in a single direction in the specified units.

## Schema

```json
{
  "magnitude": number,
  "unit": string
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `magnitude` | number | The magnitude. |
| `unit` | string | The units for magnitude. |

### unit Values

| Value | Description |
|-------|-------------|
| `UNIT_UNSPECIFIED` | The units are unknown. |
| `EMU` | An English Metric Unit (EMU) is defined as 1/360,000 of a centimeter and thus there are 914,400 E... |
| `PT` | A point, 1/72 of an inch. |

