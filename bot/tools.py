import asyncio
from agents import function_tool

# Per-chat pending event proposals awaiting confirmation
_pending_events: dict[int, dict] = {}


def make_propose_tool(chat_id: int):
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
        _pending_events[chat_id] = {
            "summary": summary,
            "start": start,
            "end": end,
            "location": location,
            "description": description,
            "attendees": attendees,
            "add_meet": add_meet,
            "calendar": calendar,
        }
        return "Event staged for confirmation."

    return propose_calendar_event


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
        return "Failed to create event: timed out."

    if proc.returncode == 0:
        return f"'{summary}' added to your calendar."
    return f"Failed to create event: {stderr.decode().strip()}"
