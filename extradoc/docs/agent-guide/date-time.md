# Date & Time Elements

Insert and modify dates (with optional times) in Google Docs.

To modify a date, just edit its attributes — push handles the delete+reinsert automatically.

## Date-Only

```xml
<p>Deadline: <date timestamp="2025-12-25T00:00:00Z" dateFormat="DATE_FORMAT_MONTH_DAY_YEAR_ABBREVIATED"/></p>
```

## Date with Time

```xml
<p>Meeting: <date timestamp="2025-12-25T10:30:00Z" dateFormat="DATE_FORMAT_MONTH_DAY_YEAR_ABBREVIATED" timeFormat="TIME_FORMAT_HOUR_MINUTE_TIMEZONE" timeZoneId="America/New_York"/></p>
```

## Attributes

| Attribute | Required | Description |
|-----------|----------|-------------|
| `timestamp` | Yes | ISO 8601 datetime in UTC (e.g. `2025-12-25T10:30:00Z`) |
| `dateFormat` | No | How the date is displayed. Default: `DATE_FORMAT_MONTH_DAY_YEAR_ABBREVIATED` |
| `timeFormat` | No | How the time is displayed. Default: `TIME_FORMAT_DISABLED` (no time) |
| `timeZoneId` | No | IANA timezone (e.g. `America/New_York`). Default: `etc/UTC` |
| `locale` | No | Locale for formatting (e.g. `en_US`, `en_GB`). Default: `en_US` |

## `dateFormat` Values

| Value | Example |
|-------|---------|
| `DATE_FORMAT_MONTH_DAY_ABBREVIATED` | Dec 25 |
| `DATE_FORMAT_MONTH_DAY_FULL` | December 25 |
| `DATE_FORMAT_MONTH_DAY_YEAR_ABBREVIATED` | Dec 25, 2025 |
| `DATE_FORMAT_ISO8601` | 2025-12-25 |

## `timeFormat` Values

| Value | Example |
|-------|---------|
| `TIME_FORMAT_DISABLED` | *(no time shown)* |
| `TIME_FORMAT_HOUR_MINUTE` | Dec 25, 2025 10:30 AM |
| `TIME_FORMAT_HOUR_MINUTE_TIMEZONE` | Dec 25, 2025 5:30 AM EST |

When using `TIME_FORMAT_HOUR_MINUTE_TIMEZONE`, set `timeZoneId` to control the displayed timezone. Without it, times display in UTC.
