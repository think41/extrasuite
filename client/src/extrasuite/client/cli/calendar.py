"""Calendar CLI commands: view, list, search, freebusy, create, update, delete, rsvp."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from extrasuite.client.cli._common import _get_credential, _get_reason


def cmd_calendar_view(args: Any) -> None:
    """View calendar events for a time range."""
    from extrasuite.client.google_api import (
        format_events_markdown,
        list_calendar_events,
        parse_time_value,
    )

    time_min, time_max = parse_time_value(args.when)
    reason = _get_reason(args, default="View calendar events")
    cred = _get_credential(
        args,
        command={
            "type": "calendar.view",
            "when": args.when,
            "calendar_id": getattr(args, "calendar", "") or "",
        },
        reason=reason,
    )

    events = list_calendar_events(
        cred.token,
        calendar_id=args.calendar,
        time_min=time_min,
        time_max=time_max,
    )

    print(format_events_markdown(events))


def cmd_calendar_list(args: Any) -> None:
    """List all calendars the user has access to."""
    from extrasuite.client.google_api import format_calendars_markdown, list_calendars

    reason = _get_reason(args, default="List calendars")
    cred = _get_credential(
        args,
        command={"type": "calendar.list"},
        reason=reason,
    )
    calendars = list_calendars(cred.token)
    print(format_calendars_markdown(calendars))


def cmd_calendar_search(args: Any) -> None:
    """Search calendar events by title or attendee."""
    from extrasuite.client.google_api import (
        format_events_markdown,
        parse_time_value,
        search_calendar_events,
    )

    if not args.query and not args.attendee:
        print("Error: provide --query or --attendee (or both).", file=sys.stderr)
        sys.exit(1)

    from_val = args.fr or "today"
    to_val = args.to

    time_min, _ = parse_time_value(from_val)
    if to_val:
        _, time_max = parse_time_value(to_val)
    else:
        from datetime import timedelta

        time_max = time_min + timedelta(days=30)

    reason = _get_reason(args, default="Search calendar events")
    cred = _get_credential(
        args,
        command={
            "type": "calendar.search",
            "query": args.query or "",
            "attendee": args.attendee or "",
            "from_date": from_val,
            "to_date": to_val or "",
        },
        reason=reason,
    )

    events = search_calendar_events(
        cred.token,
        query=args.query,
        attendee=args.attendee,
        calendar_id=args.calendar,
        time_min=time_min,
        time_max=time_max,
    )

    print(format_events_markdown(events))


def cmd_calendar_freebusy(args: Any) -> None:
    """Check free/busy for a set of attendees."""
    from extrasuite.client.google_api import (
        format_freebusy_markdown,
        get_freebusy,
        parse_time_value,
    )

    attendees: list[str] = args.attendees
    if not attendees:
        print("Error: provide at least one --attendees email.", file=sys.stderr)
        sys.exit(1)

    time_min, time_max = parse_time_value(args.when)
    reason = _get_reason(args, default="Check free/busy")
    cred = _get_credential(
        args,
        command={
            "type": "calendar.freebusy",
            "attendees": attendees,
            "when": args.when,
        },
        reason=reason,
    )

    result = get_freebusy(cred.token, attendees, time_min, time_max)
    print(format_freebusy_markdown(result, attendees, time_min, time_max))


def cmd_calendar_create(args: Any) -> None:
    """Create a calendar event from a JSON file."""
    import json as _json

    from extrasuite.client.google_api import (
        create_calendar_event,
        format_created_event_markdown,
    )

    json_path = args.json
    if json_path == "-":
        event_json = _json.load(sys.stdin)
    else:
        event_json = _json.loads(Path(json_path).read_text())

    calendar_id = event_json.pop("calendar", None) or args.calendar
    send_notifications = event_json.pop("send_notifications", True)

    # Extract audit-relevant fields before making the API call
    event_title = event_json.get("summary", "")
    attendees = [
        a.get("email", "") for a in event_json.get("attendees", []) if a.get("email")
    ]
    start_time = (event_json.get("start") or {}).get("dateTime", "") or (
        event_json.get("start") or {}
    ).get("date", "")
    end_time = (event_json.get("end") or {}).get("dateTime", "") or (
        event_json.get("end") or {}
    ).get("date", "")

    reason = _get_reason(args, default="Create calendar event")
    cred = _get_credential(
        args,
        command={
            "type": "calendar.create",
            "event_title": event_title,
            "attendees": attendees,
            "start_time": start_time,
            "end_time": end_time,
        },
        reason=reason,
    )

    event = create_calendar_event(
        cred.token,
        event_json,
        calendar_id=calendar_id,
        send_notifications=send_notifications,
    )
    print(format_created_event_markdown(event))


def cmd_calendar_update(args: Any) -> None:
    """Update an existing calendar event from a JSON patch file."""
    import json as _json

    from extrasuite.client.google_api import (
        format_updated_event_markdown,
        update_calendar_event,
    )

    json_path = args.json
    if json_path == "-":
        patch_json = _json.load(sys.stdin)
    else:
        patch_json = _json.loads(Path(json_path).read_text())

    calendar_id = patch_json.pop("calendar", None) or args.calendar
    send_notifications = not args.no_notify

    event_title = patch_json.get("summary", "")
    attendees = [
        a.get("email", "") for a in patch_json.get("attendees", []) if a.get("email")
    ]

    reason = _get_reason(args, default="Update calendar event")
    cred = _get_credential(
        args,
        command={
            "type": "calendar.update",
            "event_id": args.event_id,
            "event_title": event_title,
            "attendees": attendees,
        },
        reason=reason,
    )

    event = update_calendar_event(
        cred.token,
        args.event_id,
        patch_json,
        calendar_id=calendar_id,
        send_notifications=send_notifications,
    )
    print(format_updated_event_markdown(event))


def cmd_calendar_delete(args: Any) -> None:
    """Delete (cancel) a calendar event."""
    from extrasuite.client.google_api import delete_calendar_event

    reason = _get_reason(args, default="Delete calendar event")
    cred = _get_credential(
        args,
        command={
            "type": "calendar.delete",
            "event_id": args.event_id,
            "event_title": "",
        },
        reason=reason,
    )

    delete_calendar_event(
        cred.token,
        args.event_id,
        calendar_id=args.calendar,
        send_notifications=not args.no_notify,
        this_and_following=args.this_and_following,
    )
    print(f"Event {args.event_id} cancelled.")
    if not args.no_notify:
        print("Cancellation notifications sent to attendees.")


def cmd_calendar_rsvp(args: Any) -> None:
    """Accept, decline, or mark tentative for an event."""
    from extrasuite.client.google_api import rsvp_calendar_event

    # Normalize short forms to API values
    response_map = {
        "accept": "accepted",
        "decline": "declined",
        "tentative": "tentative",
    }
    api_response = response_map.get(args.response, args.response)

    reason = _get_reason(args, default="RSVP to calendar event")
    cred = _get_credential(
        args,
        command={
            "type": "calendar.rsvp",
            "event_id": args.event_id,
            "event_title": "",
            "response": api_response,
        },
        reason=reason,
    )

    event = rsvp_calendar_event(
        cred.token,
        args.event_id,
        response=api_response,
        comment=args.comment,
        calendar_id=args.calendar,
    )
    summary = event.get("summary", args.event_id)
    label = {"accepted": "Accepted", "declined": "Declined", "tentative": "Tentative"}
    print(f"RSVP updated: {summary}")
    print(f"Response: {label.get(api_response, api_response)}")
    if args.comment:
        print(f'Comment: "{args.comment}"')
