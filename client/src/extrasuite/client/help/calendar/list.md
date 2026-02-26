List all Google Calendars you have access to.

## Usage

  extrasuite calendar list

## Output

Calendars grouped into "My Calendars" (owner/writer access) and "Other Calendars"
(reader access). Each entry shows the calendar name and its ID.

Use the ID with --calendar in other commands (view, search, freebusy, create, etc.)
to target a specific calendar instead of the default primary calendar.

## Example

  extrasuite calendar list

  ## My Calendars

  - **Primary**  ID: `primary`
  - **Work**     ID: `work@example.com`

  ## Other Calendars

  - **Engineering Team**  ID: `c_abc123@group.calendar.google.com`
  - **Company Holidays**  ID: `en.indian#holiday@group.v.calendar.google.com`
