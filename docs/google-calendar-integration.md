# Google Calendar Integration Guide

This document explains how Google Calendar read and write operations work in this project, intended for future coding agents working on Felix.

## How it works end-to-end

```
User message or photo
  → bot/main.py    (Telegram handlers)
  → bot/agent.py   (OpenAI agent with calendar tools)
  → bot/tools.py   (stage proposals or run gws reads/writes)
  → bot/main.py    (per-event Confirm/Cancel inline buttons for writes)
  → bot/tools.py   (_run_create_calendar_event shells out to `gws`)
  → Google Calendar (event created via gws CLI)
```

The key design choice for **writes**: the agent **proposes** events first (no side effects), then the user confirms via Telegram inline buttons before anything is created. Never skip this two-step flow — it is a deliberate safety gate.

**Reads** (`list_calendar_events`) run immediately with no confirmation.

---

## The `gws` CLI

All calendar operations go through the `@googleworkspace/cli` npm package (`gws`). This project does not use the Google Calendar REST API directly.

### Creating an event

```bash
gws calendar +insert \
  --summary "Team standup" \
  --start "2026-06-17T09:00:00+08:00" \
  --end   "2026-06-17T09:30:00+08:00"
```

### Listing events

```bash
gws calendar events list \
  --format json \
  --params '{"calendarId":"...", "timeMin":"...", "timeMax":"...", "singleEvents":true, "orderBy":"startTime", "maxResults":20}'
```

### All available flags for `+insert`

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
- `gws-calendar-agenda/SKILL.md` — listing/upcoming events
- `gws-shared/SKILL.md` — auth, global flags, security rules (run `gws generate-skills` if missing)

---

## Code walkthrough

### `bot/tools.py` — two-phase write design

**Phase 1: propose** (`propose_calendar_event`, `propose_calendar_events`)

The agent calls one of these tools. They only write to an in-memory dict — no subprocess, no side effects.

```python
# Per-chat pending event proposals awaiting confirmation
_pending_events: dict[int, list[dict[str, Any]]] = {}
```

- **Single event:** `propose_calendar_event` stages one `CalendarEventProposal`.
- **Multiple events:** `propose_calendar_events` stages the full list in one call. The agent should use this for multi-event requests instead of calling `propose_calendar_event` repeatedly.

Staging always **replaces** the pending list for that chat:

```python
def _stage_events(chat_id: int, events: list[CalendarEventProposal]) -> int:
    staged = [event.model_dump() for event in events]
    if staged:
        _pending_events[chat_id] = staged
    else:
        _pending_events.pop(chat_id, None)
    return len(staged)
```

Each staged dict has keys: `summary`, `start`, `end`, `location`, `description`, `attendees`, `add_meet`, `calendar`.

`make_propose_tools(chat_id)` is a factory because the tools need the chat ID in their closure. New tool instances are created per agent run.

**Phase 2: create** (`_run_create_calendar_event`)

Called by `main.py` only after the user taps Confirm on a specific event. Builds the `gws calendar +insert` command and runs it as an async subprocess with a 30-second timeout.

```python
proc = await asyncio.create_subprocess_exec(*cmd, ...)
_, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
```

On success (returncode 0) returns a confirmation string. On failure returns the stderr message.

**Reads** (`list_calendar_events`)

Runs immediately when the agent needs to view events. Resolves calendar names/IDs via the `CALENDARS` dict, shells out to `gws calendar events list`, and returns a formatted text summary. No confirmation gate.

### `bot/agent.py` — system prompt with calendar context

The system prompt includes:
- Current date/time (`{now}`) — rebuilt fresh on every request so the agent always knows the real date
- User's timezone (`{tz}`) — read from `USER_TIMEZONE` env var
- Named calendars with their IDs — the agent picks the right one based on context

Calendar IDs are defined in `CALENDARS` inside `bot/tools.py` and injected into the prompt via `_CALENDAR_PROMPT`. If a new calendar needs to be added, update `CALENDARS` in `bot/tools.py`.

At the start of each agent run, any stale pending proposal is cleared:

```python
_pending_events.pop(chat_id, None)
```

If the user sends a new message without confirming, buttons on the old message become orphaned (Confirm will reply "This proposal has already expired.").

### `bot/main.py` — per-event confirmation flow

After `run_agent` returns, the handler checks if pending events were staged:

```python
pending = _pending_events.get(chat_id)
if pending:
    await update.message.reply_text(reply, reply_markup=_confirm_keyboard(pending))
```

`_confirm_keyboard(events)` builds one inline keyboard row per staged event:

```
✅ Confirm: Team sync    ❌ Cancel
✅ Confirm: Dentist      ❌ Cancel
✅ Confirm: Budget rev…  ❌ Cancel
```

- Button labels truncate long titles (~30 chars).
- `callback_data` is `confirm:{index}` or `cancel:{index}` (0-based index into the current pending list).

The `button_handler` handles per-event Confirm/Cancel:

- **Confirm (`confirm:{i}`):** pops that event from `_pending_events[chat_id]`, calls `_run_create_calendar_event(**event)`, replies with the result, and refreshes the keyboard on the original message (or removes it if no events remain).
- **Cancel (`cancel:{i}`):** removes that event from the list, replies `Cancelled: {summary}`, and refreshes/clears the keyboard the same way.
- **Expired:** if the list is gone, the index is invalid, or callback data is malformed, replies "This proposal has already expired." and clears the keyboard.

Users can confirm some events and cancel others independently within the same batch.

---

## Adding a new calendar

1. Get the calendar ID from Google Calendar settings.
2. Add an entry to `CALENDARS` in `bot/tools.py` (name, id, description).
3. The agent will automatically route events and reads to the right calendar based on context.

## Adding a new field to events

1. Add the field to `CalendarEventProposal` in `bot/tools.py`.
2. Add the parameter to `propose_calendar_event` (and ensure it flows through `propose_calendar_events` via the model).
3. Add the same parameter to `_run_create_calendar_event`.
4. Add the corresponding `gws` flag to the `cmd` list inside `_run_create_calendar_event`.
5. The `button_handler` calls `_run_create_calendar_event(**event)` — since each staged dict comes from `model_dump()`, the new field flows through automatically.
