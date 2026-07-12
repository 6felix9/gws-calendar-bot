import base64
import logging
import os

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from .agent import run_agent
from .tools import (
    _pending_events,
    _run_create_calendar_event,
    _run_delete_calendar_event,
    _run_edit_calendar_event,
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def _short_button_label(summary: str, max_len: int = 30) -> str:
    title = summary.strip()
    if len(title) <= max_len:
        return title
    return f"{title[: max_len - 3].rstrip()}..."


def _confirm_label(event: dict, index: int) -> str:
    label = _short_button_label(event.get("summary") or f"Event {index + 1}")
    action = event.get("action", "create")
    if action == "delete":
        return f"✅ Confirm delete: {label}"
    if action == "edit":
        return f"✅ Confirm edit: {label}"
    return f"✅ Confirm: {label}"


def _confirm_keyboard(events: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for index, event in enumerate(events):
        rows.append([
            InlineKeyboardButton(_confirm_label(event, index), callback_data=f"confirm:{index}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"cancel:{index}"),
        ])
    return InlineKeyboardMarkup(rows)


async def _execute_pending_item(item: dict) -> str:
    action = item.get("action", "create")
    payload = {key: value for key, value in item.items() if key != "action"}
    if action == "delete":
        return await _run_delete_calendar_event(**payload)
    if action == "edit":
        return await _run_edit_calendar_event(**payload)
    return await _run_create_calendar_event(**payload)


async def _refresh_proposal_keyboard(query, chat_id: int) -> None:
    pending = _pending_events.get(chat_id)
    markup = _confirm_keyboard(pending) if pending else None
    await query.edit_message_reply_markup(reply_markup=markup)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hi! I'm your calendar assistant.\n\n"
        "Ask me what's on your calendar, or tell me about an event you'd like to schedule.\n\n"
        "Examples:\n"
        "\"What do I have today?\"\n"
        "\"Schedule a team sync tomorrow at 10am for 1 hour\"\n\n"
        "Type /help for more examples."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Calendar Assistant — Examples:\n\n"
        "View events:\n"
        "• What do I have today?\n"
        "• Show my NUS events tomorrow\n"
        "• What's on my personal calendar next week?\n\n"
        "Create events:\n"
        "• Schedule a team sync tomorrow at 10am for 1 hour\n"
        "• Add a dentist appointment on Friday at 3pm\n"
        "• Create a budget review meeting next Monday 2pm–3pm with alice@example.com\n"
        "• Book a standup every day at 9am for 30 minutes with a Meet link\n\n"
        "Delete events:\n"
        "• Delete my lunch tomorrow\n"
        "• Remove the team sync on Friday\n\n"
        "Edit events:\n"
        "• Move my lunch tomorrow to 1pm\n"
        "• Rename Friday's team sync to Project sync\n\n"
        "I'll answer calendar queries immediately. Creating, editing, or deleting events requires confirmation via inline buttons."
    )


async def _reply_with_agent_output(update: Update, chat_id: int, reply: str) -> None:
    pending = _pending_events.get(chat_id)
    if pending:
        await update.message.reply_text(reply, reply_markup=_confirm_keyboard(pending))
    else:
        await update.message.reply_text(reply)


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    text = update.message.text

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        reply = await run_agent(chat_id, text)
    except Exception as e:
        logger.error("Agent error for chat %s: %s", chat_id, e)
        reply = "Sorry, something went wrong. Please try again."

    await _reply_with_agent_output(update, chat_id, reply)


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    photo = update.message.photo[-1]  # largest available size
    caption = update.message.caption or "If this image contains event details, help me add it to my calendar."

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        file = await context.bot.get_file(photo.file_id)
        data = await file.download_as_bytearray()
        image_b64 = base64.b64encode(data).decode()
        reply = await run_agent(chat_id, caption, image_b64=image_b64)
    except Exception as e:
        logger.error("Agent error for chat %s: %s", chat_id, e)
        reply = "Sorry, something went wrong processing the image."

    await _reply_with_agent_output(update, chat_id, reply)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat_id = query.message.chat_id
    await query.answer()

    data = query.data or ""
    if ":" not in data:
        await query.message.reply_text("This proposal has already expired.")
        return

    action, _, index_str = data.partition(":")
    try:
        index = int(index_str)
    except ValueError:
        await query.message.reply_text("This proposal has already expired.")
        return

    pending_events = _pending_events.get(chat_id)
    if not pending_events or index < 0 or index >= len(pending_events):
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("This proposal has already expired.")
        return

    if action == "confirm":
        item = pending_events.pop(index)
        if pending_events:
            _pending_events[chat_id] = pending_events
        else:
            _pending_events.pop(chat_id, None)
        await _refresh_proposal_keyboard(query, chat_id)
        result = await _execute_pending_item(item)
        await query.message.reply_text(result)
    elif action == "cancel":
        summary = pending_events[index].get("summary") or "Event"
        pending_action = pending_events[index].get("action", "create")
        pending_events.pop(index)
        if pending_events:
            _pending_events[chat_id] = pending_events
        else:
            _pending_events.pop(chat_id, None)
        await _refresh_proposal_keyboard(query, chat_id)
        if pending_action == "delete":
            await query.message.reply_text(f"Cancelled delete: {summary}")
        elif pending_action == "edit":
            await query.message.reply_text(f"Cancelled edit: {summary}")
        else:
            await query.message.reply_text(f"Cancelled: {summary}")
    else:
        await query.message.reply_text("This proposal has already expired.")


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    owner_id = int(os.environ["OWNER_TELEGRAM_ID"])
    owner = filters.User(user_id=owner_id)

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start, filters=owner))
    app.add_handler(CommandHandler("help", help_command, filters=owner))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & owner, message_handler))
    app.add_handler(MessageHandler(filters.PHOTO & owner, photo_handler))
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
