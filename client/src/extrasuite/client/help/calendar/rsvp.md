Accept, decline, or mark tentative for a calendar event you've been invited to.

## Usage

  extrasuite calendar rsvp EVENT_ID --response RESPONSE [--comment TEXT] [--calendar ID]

## Flags

  --reason TEXT  State the user's intent that led to this command (required). Also -r or -m.

  EVENT_ID            Event ID (from `calendar view` or `calendar search`)
  --response          Your response: accept, decline, or tentative (required)
  --comment TEXT      Optional message to include with your response
  --calendar ID       Calendar ID (default: primary)

## Response Values

  accept              Accept the invitation
  decline             Decline the invitation
  tentative           Mark as tentative (maybe)

## Examples

  # Accept an invite
  extrasuite calendar rsvp abc123xyz --response accept --reason "state the user's intent that led to this command"

  # Decline with a reason
  extrasuite calendar rsvp abc123xyz --response decline --comment "I have a conflict - will send a delegate"

  # Mark tentative
  extrasuite calendar rsvp abc123xyz --response tentative --comment "Will confirm by EOD"

## Notes

- You must be listed as an attendee on the event to RSVP.
- The organizer and other attendees are notified of your response.

## Workflow

1. Run `calendar view` or `calendar search` to find the event and its Event ID
2. Run `calendar rsvp` with the Event ID and your response
