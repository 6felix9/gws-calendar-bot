import subprocess
from agents import function_tool


@function_tool
def create_calendar_event(
    summary: str,
    start: str,
    end: str,
    location: str | None = None,
    description: str | None = None,
    attendees: list[str] | None = None,
    add_meet: bool = False,
    calendar: str = "primary",
) -> str:
    """Create a Google Calendar event via the gws CLI.

    Args:
        summary: Event title.
        start: Start time in RFC3339 format (e.g. 2026-06-17T09:00:00+08:00).
        end: End time in RFC3339 format.
        location: Optional venue or address.
        description: Optional event notes.
        attendees: Optional list of attendee email addresses.
        add_meet: Set to true to add a Google Meet video link.
        calendar: Calendar ID to add the event to (default 'primary').
    """
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

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return f"Event '{summary}' created successfully.\n{result.stdout.strip()}"
    return f"Failed to create event: {result.stderr.strip()}"