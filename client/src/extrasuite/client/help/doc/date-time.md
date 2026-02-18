# Date & Time Elements

Insert and modify dynamic date/time fields in Google Docs.

## Syntax

```xml
<!-- Date only -->
<p>Deadline: <date timestamp="2025-12-25T00:00:00Z"
              dateFormat="DATE_FORMAT_MONTH_DAY_YEAR_ABBREVIATED"/></p>

<!-- Date with time -->
<p>Meeting: <date timestamp="2025-12-25T10:30:00Z"
              dateFormat="DATE_FORMAT_MONTH_DAY_YEAR_ABBREVIATED"
              timeFormat="TIME_FORMAT_HOUR_MINUTE_TIMEZONE"
              timeZoneId="America/New_York"/></p>
```

## Attributes

  timestamp     Required. ISO 8601 UTC datetime: "2025-12-25T10:30:00Z"
  dateFormat    How the date displays (see below). Default: MONTH_DAY_YEAR_ABBREVIATED
  timeFormat    How the time displays (see below). Default: TIME_FORMAT_DISABLED (no time)
  timeZoneId    IANA timezone: "America/New_York". Default: UTC
  locale        Formatting locale: "en_US", "en_GB". Default: en_US

## dateFormat Values

  DATE_FORMAT_MONTH_DAY_ABBREVIATED        Dec 25
  DATE_FORMAT_MONTH_DAY_FULL               December 25
  DATE_FORMAT_MONTH_DAY_YEAR_ABBREVIATED   Dec 25, 2025
  DATE_FORMAT_ISO8601                      2025-12-25

## timeFormat Values

  TIME_FORMAT_DISABLED              (no time shown)
  TIME_FORMAT_HOUR_MINUTE           Dec 25, 2025 10:30 AM
  TIME_FORMAT_HOUR_MINUTE_TIMEZONE  Dec 25, 2025 5:30 AM EST

When using TIME_FORMAT_HOUR_MINUTE_TIMEZONE, set timeZoneId to control
the displayed timezone. Without it, times display in UTC.

## Editing

To modify a date, edit its attributes directly. Push handles the
delete-and-reinsert automatically.
