import os
from datetime import datetime
from collections import defaultdict

from agents import Agent, Runner
from .tools import make_propose_tool, _pending_events

_SYSTEM_PROMPT = """\
You are a calendar assistant. You create Google Calendar events from natural language or photos.

Now: {now}
Timezone: {tz}

Rules:
- Do not use markdown in your response.
- Be direct and concise. No filler phrases.
- Infer missing details using context and reasonable defaults (e.g. 1-hour duration, no location unless stated). Only ask a question if the event title or start time is genuinely ambiguous.
- When you have all the details, call `propose_calendar_event` to stage the event, then summarize it to the user (title, date, time, duration). Confirmation buttons will appear automatically.
- Times must be RFC3339 with timezone offset before calling the tool. Example: 2026-06-17T09:00:00+08:00
"""

# Per-chat conversation history: chat_id -> list of message dicts
_history: dict[int, list[dict]] = defaultdict(list)
_MAX_HISTORY = 20  # keep last 20 messages per chat


async def run_agent(chat_id: int, user_message: str, image_b64: str | None = None) -> str:
    history = _history[chat_id]

    # Clear any stale proposal from a previous turn
    _pending_events.pop(chat_id, None)

    tz = os.getenv("USER_TIMEZONE", "UTC")
    now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
    agent = Agent(
        name="CalendarAssistant",
        model="gpt-5.1",
        instructions=_SYSTEM_PROMPT.format(now=now, tz=tz),
        tools=[make_propose_tool(chat_id)],
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
