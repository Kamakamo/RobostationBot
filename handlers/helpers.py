import logging
import re

from telegram import User
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def is_engineer(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    return user_id in context.bot_data.get("engineers", [])


def get_user_mention(user: User) -> str:
    return f"@{user.username}" if user.username else user.full_name


def escape_markdown(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    escape_chars = r"\_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", text)


def track_request_message(
    context: ContextTypes.DEFAULT_TYPE, request_id: str, chat_id: int, message_id: int
):
    key = f"messages_for_req_{request_id}"
    if key not in context.bot_data:
        context.bot_data[key] = []
    context.bot_data[key].append((chat_id, message_id))


async def delete_tracked_messages(context: ContextTypes.DEFAULT_TYPE, request_id: str):
    key = f"messages_for_req_{request_id}"
    if key in context.bot_data:
        for chat_id, message_id in context.bot_data[key]:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(
                    f"Не удалось удалить сообщение {message_id} в чате {chat_id}: {e}"
                )
        del context.bot_data[key]
