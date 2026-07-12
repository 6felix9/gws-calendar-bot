import os
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from collections import defaultdict

from agents import Agent, Runner
from .tools import CALENDARS, list_calendar_events, make_propose_tools, _pending_events


_SYSTEM_PROMPT = """\
You are a calendar assistant. You create and view Google Calendar events from natural language or photos.

Now: {now}
Timezone: {tz}

Calendars:
{calendars}

Rules:
- Do not use markdown in your response.
- Be direct and concise. No filler phrases.
- For viewing, listing, checking, or querying existing events, call `list_calendar_events` immediately. Calendar reads do not need confirmation.
- For broad calendar queries, pass both NUS and Personal. If the user says NUS, school, class, or university, pass only NUS. If the user says personal, pass only Personal.
- For calendar queries, infer date windows in the user's timezone. Use RFC3339 with timezone offset for `time_min` and `time_max`; `time_max` is exclusive.
- For vague upcoming queries, use the next 7 days. For today/tomorrow/named dates, use that local day. For this week/next week, use the local Monday-to-Monday week window.
- After `list_calendar_events` returns, summarize the result clearly with dates/times and event titles.
- Infer missing details using context and reasonable defaults (e.g. 1-hour duration, no location unless stated). Only ask a question if the event title or start time is genuinely ambiguous.
- When you have all the details for one event, call `propose_calendar_event` to stage it, then summarize it to the user (title, date, time, description, calendar). A confirmation button will appear automatically.
- When the user requests multiple distinct events, call `propose_calendar_events` once with the complete list, then summarize every event to the user. Each staged event gets its own Confirm/Cancel buttons. Do not call `propose_calendar_event` repeatedly for a multi-event request.
- Times must be RFC3339 with timezone offset before calling the tool. Example: 2026-06-17T09:00:00+08:00
"""


_CALENDAR_PROMPT = "\n".join(
    f"- {name} (id: {calendar['id']}): {calendar['description']}"
    for name, calendar in CALENDARS.items()
)


def _now_in_timezone(tz: str) -> datetime:
    try:
        return datetime.now(ZoneInfo(tz))
    except ZoneInfoNotFoundError:
        return datetime.now(ZoneInfo("UTC"))


_history: dict[int, list[dict]] = defaultdict(list)
_MAX_HISTORY = 20


async def run_agent(chat_id: int, user_message: str, image_b64: str | None = None) -> str:
    history = _history[chat_id]

    # Clear any stale proposal from a previous turn
    _pending_events.pop(chat_id, None)

    tz = os.getenv("USER_TIMEZONE", "UTC")
    now = _now_in_timezone(tz).strftime("%Y-%m-%d %H:%M %z (%A)")
    agent = Agent(
        name="CalendarAssistant",
        model="gpt-5.1",
        instructions=_SYSTEM_PROMPT.format(now=now, tz=tz, calendars=_CALENDAR_PROMPT),
        tools=[*make_propose_tools(chat_id), list_calendar_events],
    )

    if image_b64:
        content: list[dict] = [
            {"type": "input_image", "image_url": f"data:image/jpeg;base64,{image_b64}"},
        ]
        if user_message:
            content.insert(0, {"type": "input_text", "text": user_message})
        history.append({"role": "user", "content": content})
    else:
        history.append({"role": "user", "content": user_message})

    result = await Runner.run(agent, input=history[-_MAX_HISTORY:])

    reply = result.final_output
    history.append({"role": "assistant", "content": reply})

    if len(history) > _MAX_HISTORY:
        _history[chat_id] = history[-_MAX_HISTORY:]

    return reply
