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
from .tools import _pending_events, _run_create_calendar_event

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

_CONFIRM_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("✅ Confirm", callback_data="confirm"),
        InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
    ]
])


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
        "I'll answer calendar queries immediately. For new events, I'll show the event details and ask you to confirm before creating it."
    )


async def _reply_with_agent_output(update: Update, chat_id: int, reply: str) -> None:
    pending = _pending_events.get(chat_id)
    if pending:
        await update.message.reply_text(reply, reply_markup=_CONFIRM_KEYBOARD)
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

    if query.data == "confirm":
        pending = _pending_events.pop(chat_id, None)
        await query.edit_message_reply_markup(reply_markup=None)
        if not pending:
            await query.message.reply_text("This proposal has already expired.")
            return
        result = await _run_create_calendar_event(**pending)
        await query.message.reply_text(result)

    elif query.data == "cancel":
        _pending_events.pop(chat_id, None)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Event creation cancelled.")


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
