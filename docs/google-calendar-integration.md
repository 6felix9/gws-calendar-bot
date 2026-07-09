# Google Calendar Integration Guide

This document explains how Google Calendar event creation works in this project, intended for future coding agents working on Felix.

## How it works end-to-end

```
User message
  → bot/agent.py   (OpenAI agent with propose_calendar_event tool)
  → bot/tools.py   (stages event in _pending_events dict)
  → bot/main.py    (shows Confirm/Cancel buttons to user)
  → bot/tools.py   (_run_create_calendar_event shells out to `gws`)
  → Google Calendar (event created via gws CLI)
```

The key design choice: the agent **proposes** an event first (no side effects), then the user confirms via Telegram inline buttons before it is actually created. Never skip this two-step flow — it is a deliberate safety gate.

---

## The `gws` CLI

All calendar writes go through the `@googleworkspace/cli` npm package (`gws`). This project does not use the Google Calendar REST API directly.

### Creating an event

```bash
gws calendar +insert \
  --summary "Team standup" \
  --start "2026-06-17T09:00:00+08:00" \
  --end   "2026-06-17T09:30:00+08:00"
```

### All available flags

| Flag | Required | Default | Description |
|---|---|---|---|
| `--summary` | yes | — | Event title |
| `--start` | yes | — | Start time (RFC3339 with offset) |
| `--end` | yes | — | End time (RFC3339 with offset) |
| `--calendar` | no | `primary` | Calendar ID |
| `--location` | no | — | Venue or address |
| `--description` | no | — | Event notes |
| `--attendee` | no | — | Attendee email; repeat the flag for multiple |
| `--meet` | no | — | Adds a Google Meet link |

### Time format requirement

Times **must** be RFC3339 with a timezone offset — not UTC `Z` suffix. Use the user's local offset (configured in `USER_TIMEZONE` env var):

```
Correct:   2026-06-17T09:00:00+08:00
Incorrect: 2026-06-17T09:00:00Z
```

### Authentication

`gws` reads credentials from the path in `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE`. On Railway/Docker this is `/gws-config/credentials.json`, written at startup from the `GWS_CREDENTIALS` env var. Do not hardcode the path — always read from the env var.

### Skill files

The Claude Code skills for `gws` live in `.claude/skills/`:
- `gws-calendar-insert/SKILL.md` — `gws calendar +insert` flags and examples
- `gws-calendar/SKILL.md` — all calendar subcommands
- `gws-shared/SKILL.md` — auth, global flags, security rules (run `gws generate-skills` if missing)

---

## Code walkthrough

### `bot/tools.py` — two-phase tool design

**Phase 1: propose** (`propose_calendar_event`)

The agent calls this tool. It only writes to an in-memory dict — no subprocess, no side effects.

```python
_pending_events[chat_id] = { "summary": ..., "start": ..., ... }
return "Event staged for confirmation."
```

`make_propose_tool(chat_id)` is a factory because the tool needs the chat ID in its closure. A new tool instance is created per agent run.

**Phase 2: create** (`_run_create_calendar_event`)

Called by `main.py` only after the user taps Confirm. Builds the `gws` command and runs it as an async subprocess with a 30-second timeout.

```python
proc = await asyncio.create_subprocess_exec(*cmd, ...)
_, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
```

On success (returncode 0) returns a confirmation string. On failure returns the stderr message.

### `bot/agent.py` — system prompt with calendar context

The system prompt includes:
- Current date/time (`{now}`) — rebuilt fresh on every request so the agent always knows the real date
- User's timezone (`{tz}`) — read from `USER_TIMEZONE` env var
- Named calendars with their IDs — the agent picks the right one based on context

The two project-specific calendar IDs (NUS and Personal) are hardcoded in the system prompt. If a new calendar needs to be added, update `_SYSTEM_PROMPT` in `bot/agent.py`.

### `bot/main.py` — confirmation flow

After `run_agent` returns, the handler checks if a pending event was staged:

```python
pending = _pending_events.get(chat_id)
if pending:
    await update.message.reply_text(reply, reply_markup=_CONFIRM_KEYBOARD)
```

The `button_handler` handles Confirm/Cancel:
- **Confirm**: pops the pending event and calls `_run_create_calendar_event(**pending)`
- **Cancel**: pops and discards

`_pending_events.pop(chat_id, None)` is also called at the start of each new agent run (`run_agent`) to clear any stale proposal from a previous turn.

---

## Adding a new calendar

1. Get the calendar ID from Google Calendar settings.
2. Add it to the `Calendars:` section in `_SYSTEM_PROMPT` inside `bot/agent.py`.
3. The agent will automatically route events to the right calendar based on context.

## Adding a new field to events

1. Add the parameter to `propose_calendar_event` in `bot/tools.py` (with type hint and docstring entry).
2. Add the same parameter to `_run_create_calendar_event`.
3. Add the corresponding `gws` flag to the `cmd` list inside `_run_create_calendar_event`.
4. The `button_handler` calls `_run_create_calendar_event(**pending)` — since `pending` is built from `propose_calendar_event`'s args, the new field flows through automatically.

## Viewing events (future work)

The `gws-calendar` skill documents a `+view` or list command. If implementing a view-calendar feature, use the same subprocess pattern as `_run_create_calendar_event` but without the user-confirmation gate (reads are safe to execute immediately).
