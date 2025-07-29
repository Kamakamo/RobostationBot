import logging

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import sheets

from .helpers import escape_markdown, get_user_mention

logger = logging.getLogger(__name__)


async def update_data_from_sheets(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Обновление данных из Google Sheets...")
    context.bot_data["engineers"] = sheets.get_engineers()
    context.bot_data["content"] = sheets.get_content()
    logger.info(
        f"Данные обновлены. Инженеров: {len(context.bot_data.get('engineers', []))}, Экспонатов: {len(context.bot_data.get('content', {}))}"
    )


async def show_my_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_mention = get_user_mention(user)
    my_requests = sheets.get_requests_by_demonstrator(user_mention)
    if not my_requests:
        await update.message.reply_text("У вас нет созданных заявок.")
        return

    text = "🔍 *Ваши заявки:*\n\n"
    for req in my_requests:
        status_icon = {"Новая": "‼️", "В работе": "⚙️", "Завершена": "✅"}.get(
            req["Статус"], "❓"
        )
        text += (
            f"{status_icon} *\\#{escape_markdown(req['id'])}* \\({escape_markdown(req['Статус'])}\\)\n"
            f"   *Экспонат:* {escape_markdown(req['Экспонат'])}\n"
            f"   *Проблема:* {escape_markdown(req['Проблема'])}\n\n"
        )

    await update.message.reply_text(text, parse_mode="MarkdownV2")


my_requests_handler = CommandHandler("myrequests", show_my_requests)
