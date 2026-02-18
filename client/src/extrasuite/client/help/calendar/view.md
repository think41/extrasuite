View Google Calendar events for a time range.

## Usage

  extrasuite calendar view [--when <range>] [--calendar <id>]

## Flags

  --when <range>      Time range to view (default: today)
  --calendar <id>     Calendar ID (default: primary)

## Time Range Values

  today               Events for today
  tomorrow            Events for tomorrow
  yesterday           Events for yesterday
  this-week           Events for the current week (Mon-Sun)
  next-week           Events for next week (Mon-Sun)
  YYYY-MM-DD          Events for a specific date (e.g. 2025-03-15)

## Output

Events formatted as markdown, grouped by date. Each event shows:
title, time, location (if any), and description (if any).

## Examples

  extrasuite calendar view
  extrasuite calendar view --when tomorrow
  extrasuite calendar view --when this-week
  extrasuite calendar view --when 2025-03-15
  extrasuite calendar view --when next-week --calendar work@example.com
