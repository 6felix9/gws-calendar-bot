import os
from datetime import datetime
from collections import defaultdict

from agents import Agent, Runner
from .tools import create_calendar_event

_SYSTEM_PROMPT = """\
You are a helpful calendar assistant. You help the user manage their Google Calendar.

Today's date and time: {now}
User's timezone: {tz}

When the user asks to schedule, create, or add an event:
1. Extract the event details (title, date/time, duration, location, attendees, etc.)
2. If any required information is missing (start time, end time/duration), ask for it before proceeding.
3. Always convert times to RFC3339 format with the user's timezone offset before calling the tool.
4. Confirm with the user what you are about to create, then call create_calendar_event.
5. Report back the result clearly.

RFC3339 format example: 2026-06-17T09:00:00+08:00
"""

# Per-chat conversation history: chat_id -> list of message dicts
_history: dict[int, list[dict]] = defaultdict(list)
_MAX_HISTORY = 20  # keep last 20 messages per chat


def _build_agent() -> Agent:
    tz = os.getenv("USER_TIMEZONE", "UTC")
    now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
    return Agent(
        name="CalendarAssistant",
        model="gpt-5.1",
        instructions=_SYSTEM_PROMPT.format(now=now, tz=tz),
        tools=[create_calendar_event],
    )


async def run_agent(chat_id: int, user_message: str, image_b64: str | None = None) -> str:
    history = _history[chat_id]

    if image_b64:
        content: list[dict] = [
            {"type": "input_image", "image_url": f"data:image/jpeg;base64,{image_b64}"},
        ]
        if user_message:
            content.insert(0, {"type": "input_text", "text": user_message})
        history.append({"role": "user", "content": content})
    else:
        history.append({"role": "user", "content": user_message})

    agent = _build_agent()
    result = await Runner.run(agent, input=history[-_MAX_HISTORY:])

    reply = result.final_output
    history.append({"role": "assistant", "content": reply})

    # trim history to avoid unbounded growth
    if len(history) > _MAX_HISTORY:
        _history[chat_id] = history[-_MAX_HISTORY:]

    return reply
