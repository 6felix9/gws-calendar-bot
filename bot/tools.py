import asyncio
import json
import logging
from typing import Any

from agents import function_tool
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CalendarEventProposal(BaseModel):
    summary: str
    start: str
    end: str
    location: str | None = None
    description: str | None = None
    attendees: list[str] | None = None
    add_meet: bool = False
    calendar: str = "primary"


class CalendarEventDeleteProposal(BaseModel):
    event_id: str
    calendar: str
    summary: str
    start: str | None = None


class CalendarEventEditProposal(BaseModel):
    event_id: str
    calendar: str
    summary: str
    new_summary: str | None = None
    start: str | None = None
    end: str | None = None
    location: str | None = None
    description: str | None = None
    attendees: list[str] | None = None


# Per-chat pending event proposals awaiting confirmation
_pending_events: dict[int, list[dict[str, Any]]] = {}

CALENDARS: dict[str, dict[str, str]] = {
    "NUS": {
        "id": "21d042c54f53c9e4942a6a04a0c757b6c717ea6f09b638322b35baf4b499a69e@group.calendar.google.com",
        "description": "school-related events",
    },
    "Personal": {
        "id": "puahtzefoong@gmail.com",
        "description": "everything else",
    },
}


def _resolve_calendar_ids(calendars: list[str] | None) -> list[str]:
    all_ids = [c["id"] for c in CALENDARS.values()]
    if not calendars:
        return all_ids

    resolved: list[str] = []
    by_name = {name.lower(): calendar["id"] for name, calendar in CALENDARS.items()}
    known_ids = set(all_ids)

    for calendar in calendars:
        calendar = calendar.strip()
        if not calendar:
            continue

        calendar_id = by_name.get(calendar.lower(), calendar)
        if calendar_id in known_ids or calendar_id == "primary" or "@" in calendar_id:
            if calendar_id not in resolved:
                resolved.append(calendar_id)

    return resolved or all_ids


def _resolve_calendar_id(calendar: str) -> str:
    return _resolve_calendar_ids([calendar])[0]


def _calendar_label(calendar_id: str) -> str:
    for name, calendar in CALENDARS.items():
        if calendar["id"] == calendar_id:
            return name
    return calendar_id


def _shorten(text: str, limit: int = 180) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3].rstrip()}..."


def _stage_pending(chat_id: int, items: list[dict[str, Any]]) -> int:
    if items:
        _pending_events[chat_id] = items
    else:
        _pending_events.pop(chat_id, None)
    return len(items)


def _stage_events(chat_id: int, events: list[CalendarEventProposal]) -> int:
    staged = [{**event.model_dump(), "action": "create"} for event in events]
    return _stage_pending(chat_id, staged)


def _stage_deletes(chat_id: int, events: list[CalendarEventDeleteProposal]) -> int:
    staged = [
        {
            "action": "delete",
            "event_id": event.event_id,
            "calendar": event.calendar,
            "summary": event.summary,
            **({"start": event.start} if event.start else {}),
        }
        for event in events
    ]
    return _stage_pending(chat_id, staged)


def _stage_edits(chat_id: int, events: list[CalendarEventEditProposal]) -> int:
    staged = []
    for event in events:
        payload: dict[str, Any] = {
            "action": "edit",
            "event_id": event.event_id,
            "calendar": event.calendar,
            "summary": event.summary,
        }
        if event.new_summary is not None:
            payload["new_summary"] = event.new_summary
        if event.start is not None:
            payload["start"] = event.start
        if event.end is not None:
            payload["end"] = event.end
        if event.location is not None:
            payload["location"] = event.location
        if event.description is not None:
            payload["description"] = event.description
        if event.attendees is not None:
            payload["attendees"] = event.attendees
        staged.append(payload)
    return _stage_pending(chat_id, staged)


def make_propose_tools(chat_id: int):
    @function_tool
    def propose_calendar_event(
        summary: str,
        start: str,
        end: str,
        location: str | None = None,
        description: str | None = None,
        attendees: list[str] | None = None,
        add_meet: bool = False,
        calendar: str = "primary",
    ) -> str:
        """Stage a Google Calendar event for user confirmation before creating it.

        Args:
            summary: Event title.
            start: Start time in RFC3339 format (e.g. 2026-06-17T09:00:00+08:00).
            end: End time in RFC3339 format.
            location: Optional venue or address.
            description: Optional event notes.
            attendees: Optional list of attendee email addresses.
            add_meet: Set to true to add a Google Meet video link.
            calendar: Calendar ID (default 'primary').
        """
        _stage_events(
            chat_id,
            [
                CalendarEventProposal(
                    summary=summary,
                    start=start,
                    end=end,
                    location=location,
                    description=description,
                    attendees=attendees,
                    add_meet=add_meet,
                    calendar=calendar,
                )
            ],
        )
        return "Event staged for confirmation."

    @function_tool
    def propose_calendar_events(events: list[CalendarEventProposal]) -> str:
        """Stage multiple Google Calendar events for one user confirmation.

        Use this when a user asks to create more than one distinct event. Each event
        must include its own title, start time, end time, and calendar selection.

        Args:
            events: The complete list of event proposals to create after confirmation.
        """
        count = _stage_events(chat_id, events)
        if count == 0:
            return "No events staged for confirmation."
        return f"{count} events staged for confirmation."

    @function_tool
    def propose_delete_calendar_event(
        event_id: str,
        calendar: str,
        summary: str,
        start: str | None = None,
    ) -> str:
        """Stage a Google Calendar event deletion for user confirmation.

        Args:
            event_id: Event ID from list_calendar_events.
            calendar: Calendar ID from list_calendar_events.
            summary: Event title for display in confirmation buttons.
            start: Optional start time for display in the summary.
        """
        _stage_deletes(
            chat_id,
            [
                CalendarEventDeleteProposal(
                    event_id=event_id,
                    calendar=calendar,
                    summary=summary,
                    start=start,
                )
            ],
        )
        return "Event staged for deletion."

    @function_tool
    def propose_delete_calendar_events(events: list[CalendarEventDeleteProposal]) -> str:
        """Stage multiple Google Calendar event deletions for user confirmation.

        Use when the user asks to delete more than one distinct event. Each entry
        must include event_id, calendar, and summary from list_calendar_events.

        Args:
            events: The complete list of events to delete after confirmation.
        """
        count = _stage_deletes(chat_id, events)
        if count == 0:
            return "No events staged for deletion."
        return f"{count} events staged for deletion."

    @function_tool
    def propose_edit_calendar_event(
        event_id: str,
        calendar: str,
        summary: str,
        new_summary: str | None = None,
        start: str | None = None,
        end: str | None = None,
        location: str | None = None,
        description: str | None = None,
        attendees: list[str] | None = None,
    ) -> str:
        """Stage a Google Calendar event edit for user confirmation.

        Include only fields that should change. At least one of new_summary, start,
        end, location, description, or attendees must be set.

        Args:
            event_id: Event ID from list_calendar_events.
            calendar: Calendar ID from list_calendar_events.
            summary: Current event title for display in confirmation buttons.
            new_summary: New event title, if changing.
            start: New start time in RFC3339 format.
            end: New end time in RFC3339 format.
            location: New location.
            description: New description.
            attendees: New attendee email list (replaces existing attendees).
        """
        _stage_edits(
            chat_id,
            [
                CalendarEventEditProposal(
                    event_id=event_id,
                    calendar=calendar,
                    summary=summary,
                    new_summary=new_summary,
                    start=start,
                    end=end,
                    location=location,
                    description=description,
                    attendees=attendees,
                )
            ],
        )
        return "Event staged for edit."

    @function_tool
    def propose_edit_calendar_events(events: list[CalendarEventEditProposal]) -> str:
        """Stage multiple Google Calendar event edits for user confirmation.

        Use when the user asks to edit more than one distinct event. Each entry must
        include event_id, calendar, summary, and at least one field to change.

        Args:
            events: The complete list of event edits to apply after confirmation.
        """
        count = _stage_edits(chat_id, events)
        if count == 0:
            return "No events staged for edit."
        return f"{count} events staged for edit."

    return [
        propose_calendar_event,
        propose_calendar_events,
        propose_delete_calendar_event,
        propose_delete_calendar_events,
        propose_edit_calendar_event,
        propose_edit_calendar_events,
    ]


async def _fetch_calendar_events(
    calendar_id: str, time_min: str, time_max: str, max_results: int
) -> tuple[list[dict], str | None]:
    params = {
        "calendarId": calendar_id,
        "timeMin": time_min,
        "timeMax": time_max,
        "singleEvents": True,
        "orderBy": "startTime",
        "maxResults": max_results,
    }
    cmd = [
        "gws", "calendar", "events", "list",
        "--format", "json",
        "--params", json.dumps(params),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        logger.error("gws calendar events list timed out (calendar=%s)", calendar_id)
        return [], f"{_calendar_label(calendar_id)}: timed out"

    if proc.returncode != 0:
        stderr_text = stderr.decode().strip()
        message = stderr_text or stdout.decode().strip() or "unknown error"
        logger.error(
            "gws calendar events list failed (calendar=%s, exit=%s): %s",
            calendar_id, proc.returncode, message,
        )
        return [], f"{_calendar_label(calendar_id)}: {message}"

    try:
        data = json.loads(stdout.decode())
    except json.JSONDecodeError:
        logger.error(
            "gws calendar events list returned invalid JSON (calendar=%s): %s",
            calendar_id, stdout.decode().strip(),
        )
        return [], f"{_calendar_label(calendar_id)}: returned invalid JSON"

    events = []
    for event in data.get("items", []):
        event["calendarLabel"] = _calendar_label(calendar_id)
        event["calendarId"] = calendar_id
        events.append(event)
    return events, None


@function_tool
async def list_calendar_events(
    time_min: str,
    time_max: str,
    calendars: list[str] | None = None,
    max_results: int = 20,
) -> str:
    """List Google Calendar events in a time window.

    Args:
        time_min: Inclusive window start in RFC3339 format with timezone offset.
        time_max: Exclusive window end in RFC3339 format with timezone offset.
        calendars: Calendar names or IDs. Defaults to all configured calendars.
        max_results: Maximum events to fetch per calendar, clamped to 1-50.
    """
    calendar_ids = _resolve_calendar_ids(calendars)
    max_results = min(max(max_results, 1), 50)

    results = await asyncio.gather(
        *[_fetch_calendar_events(cid, time_min, time_max, max_results) for cid in calendar_ids]
    )
    events: list[dict] = []
    errors: list[str] = []
    for cal_events, error in results:
        events.extend(cal_events)
        if error:
            errors.append(error)

    events.sort(key=lambda event: (
        event.get("start", {}).get("dateTime")
        or event.get("start", {}).get("date")
        or ""
    ))

    if not events:
        message = f"No events found from {time_min} to {time_max}."
        if errors:
            message += "\nErrors:\n" + "\n".join(f"- {error}" for error in errors)
        return message

    lines = [f"Events from {time_min} to {time_max}:"]
    for event in events:
        summary = event.get("summary") or "(no title)"
        start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date") or "unknown start"
        end = event.get("end", {}).get("dateTime") or event.get("end", {}).get("date") or "unknown end"
        details = [
            f"- [{event.get('calendarLabel')}] {summary}",
            f"  Event ID: {event.get('id') or 'unknown'}",
            f"  Calendar ID: {event.get('calendarId') or 'unknown'}",
            f"  Start: {start}",
            f"  End: {end}",
        ]
        if event.get("location"):
            details.append(f"  Location: {_shorten(event['location'], 120)}")
        if event.get("description"):
            details.append(f"  Description: {_shorten(event['description'])}")
        lines.extend(details)

    if errors:
        lines.append("Errors:")
        lines.extend(f"- {error}" for error in errors)

    return "\n".join(lines)


async def _run_create_calendar_event(
    summary: str,
    start: str,
    end: str,
    location: str | None = None,
    description: str | None = None,
    attendees: list[str] | None = None,
    add_meet: bool = False,
    calendar: str = "primary",
) -> str:
    cmd = [
        "gws", "calendar", "+insert",
        "--summary", summary,
        "--start", start,
        "--end", end,
    ]
    if location:
        cmd += ["--location", location]
    if description:
        cmd += ["--description", description]
    for email in (attendees or []):
        cmd += ["--attendee", email]
    if add_meet:
        cmd.append("--meet")
    if calendar != "primary":
        cmd += ["--calendar", calendar]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        logger.error("gws calendar +insert timed out (summary=%r)", summary)
        return "Failed to create event: timed out."

    if proc.returncode == 0:
        return f"'{summary}' added to your calendar."

    stderr_text = stderr.decode().strip()
    logger.error(
        "gws calendar +insert failed (summary=%r, exit=%s): %s",
        summary, proc.returncode, stderr_text,
    )
    return f"Failed to create event: {stderr_text}"


async def _run_delete_calendar_event(
    event_id: str,
    calendar: str,
    summary: str,
    start: str | None = None,
) -> str:
    calendar_id = _resolve_calendar_id(calendar)
    params = {"calendarId": calendar_id, "eventId": event_id}
    cmd = [
        "gws", "calendar", "events", "delete",
        "--params", json.dumps(params),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        logger.error("gws calendar events delete timed out (summary=%r)", summary)
        return "Failed to delete event: timed out."

    if proc.returncode == 0:
        return f"'{summary}' deleted from your calendar."

    stderr_text = stderr.decode().strip()
    logger.error(
        "gws calendar events delete failed (summary=%r, exit=%s): %s",
        summary, proc.returncode, stderr_text,
    )
    return f"Failed to delete event: {stderr_text}"


def _build_edit_patch_body(
    new_summary: str | None = None,
    start: str | None = None,
    end: str | None = None,
    location: str | None = None,
    description: str | None = None,
    attendees: list[str] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if new_summary is not None:
        body["summary"] = new_summary
    if start is not None:
        body["start"] = {"dateTime": start}
    if end is not None:
        body["end"] = {"dateTime": end}
    if location is not None:
        body["location"] = location
    if description is not None:
        body["description"] = description
    if attendees is not None:
        body["attendees"] = [{"email": email} for email in attendees]
    return body


async def _run_edit_calendar_event(
    event_id: str,
    calendar: str,
    summary: str,
    new_summary: str | None = None,
    start: str | None = None,
    end: str | None = None,
    location: str | None = None,
    description: str | None = None,
    attendees: list[str] | None = None,
) -> str:
    patch_body = _build_edit_patch_body(
        new_summary=new_summary,
        start=start,
        end=end,
        location=location,
        description=description,
        attendees=attendees,
    )
    if not patch_body:
        return "Failed to edit event: no fields to update."

    calendar_id = _resolve_calendar_id(calendar)
    params = {"calendarId": calendar_id, "eventId": event_id}
    cmd = [
        "gws", "calendar", "events", "patch",
        "--params", json.dumps(params),
        "--json", json.dumps(patch_body),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        logger.error("gws calendar events patch timed out (summary=%r)", summary)
        return "Failed to edit event: timed out."

    display_name = new_summary or summary
    if proc.returncode == 0:
        return f"'{display_name}' updated on your calendar."

    stderr_text = stderr.decode().strip()
    logger.error(
        "gws calendar events patch failed (summary=%r, exit=%s): %s",
        summary, proc.returncode, stderr_text,
    )
    return f"Failed to edit event: {stderr_text}"
