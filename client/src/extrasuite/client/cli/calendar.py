"""Calendar CLI commands: view, list, search, freebusy, create, update, delete, rsvp."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from extrasuite.client.cli._common import _get_oauth_token


def cmd_calendar_view(args: Any) -> None:
    """View calendar events for a time range."""
    from extrasuite.client.google_api import (
        format_events_markdown,
        list_calendar_events,
        parse_time_value,
    )

    time_min, time_max = parse_time_value(args.when)
    access_token = _get_oauth_token(
        args,
        scopes=["calendar"],
        reason="View calendar events",
    )

    events = list_calendar_events(
        access_token,
        calendar_id=args.calendar,
        time_min=time_min,
        time_max=time_max,
    )

    print(format_events_markdown(events))


def cmd_calendar_list(args: Any) -> None:
    """List all calendars the user has access to."""
    from extrasuite.client.google_api import format_calendars_markdown, list_calendars

    access_token = _get_oauth_token(
        args,
        scopes=["calendar"],
        reason="List calendars",
    )
    calendars = list_calendars(access_token)
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

    access_token = _get_oauth_token(
        args,
        scopes=["calendar"],
        reason="Search calendar events",
    )

    events = search_calendar_events(
        access_token,
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
    access_token = _get_oauth_token(
        args,
        scopes=["calendar"],
        reason="Check free/busy",
    )

    result = get_freebusy(access_token, attendees, time_min, time_max)
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

    access_token = _get_oauth_token(
        args,
        scopes=["calendar"],
        reason="Create calendar event",
    )

    event = create_calendar_event(
        access_token,
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

    access_token = _get_oauth_token(
        args,
        scopes=["calendar"],
        reason="Update calendar event",
    )

    event = update_calendar_event(
        access_token,
        args.event_id,
        patch_json,
        calendar_id=calendar_id,
        send_notifications=send_notifications,
    )
    print(format_updated_event_markdown(event))


def cmd_calendar_delete(args: Any) -> None:
    """Delete (cancel) a calendar event."""
    from extrasuite.client.google_api import delete_calendar_event

    access_token = _get_oauth_token(
        args,
        scopes=["calendar"],
        reason="Delete calendar event",
    )

    delete_calendar_event(
        access_token,
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

    access_token = _get_oauth_token(
        args,
        scopes=["calendar"],
        reason="RSVP to calendar event",
    )

    # Normalize short forms to API values
    response_map = {
        "accept": "accepted",
        "decline": "declined",
        "tentative": "tentative",
    }
    api_response = response_map.get(args.response, args.response)

    event = rsvp_calendar_event(
        access_token,
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
