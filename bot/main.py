import base64
import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from .agent import run_agent

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hi! I'm your calendar assistant.\n\n"
        "Tell me about an event you'd like to schedule and I'll add it to your Google Calendar.\n\n"
        "Example: \"Schedule a team sync tomorrow at 10am for 1 hour\"\n\n"
        "Type /help for more examples."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Calendar Assistant — Examples:\n\n"
        "• Schedule a team sync tomorrow at 10am for 1 hour\n"
        "• Add a dentist appointment on Friday at 3pm\n"
        "• Create a budget review meeting next Monday 2pm–3pm with alice@example.com\n"
        "• Book a standup every day at 9am for 30 minutes with a Meet link\n\n"
        "I'll confirm the details before creating anything."
    )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    text = update.message.text

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        reply = await run_agent(chat_id, text)
    except Exception as e:
        logger.error("Agent error for chat %s: %s", chat_id, e)
        reply = "Sorry, something went wrong. Please try again."

    await update.message.reply_text(reply)


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    photo = update.message.photo[-1]  # largest available size
    caption = update.message.caption or "What's in this image? If it contains event details, help me add it to my calendar."

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        file = await context.bot.get_file(photo.file_id)
        data = await file.download_as_bytearray()
        image_b64 = base64.b64encode(data).decode()
        reply = await run_agent(chat_id, caption, image_b64=image_b64)
    except Exception as e:
        logger.error("Agent error for chat %s: %s", chat_id, e)
        reply = "Sorry, something went wrong processing the image."

    await update.message.reply_text(reply)


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    owner_id = int(os.environ["OWNER_TELEGRAM_ID"])
    owner = filters.User(user_id=owner_id)

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start, filters=owner))
    app.add_handler(CommandHandler("help", help_command, filters=owner))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & owner, message_handler))
    app.add_handler(MessageHandler(filters.PHOTO & owner, photo_handler))

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
