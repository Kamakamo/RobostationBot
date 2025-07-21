import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
import sheets
from config import ADMIN_IDS

logger = logging.getLogger(__name__)

async def update_data_from_sheets(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Обновление данных из Google Sheets...")
    context.bot_data['engineers'] = sheets.get_engineers()
    context.bot_data['content'] = sheets.get_content()
    logger.info(f"Данные обновлены. Инженеров: {len(context.bot_data.get('engineers',[]))}, Экспонатов: {len(context.bot_data.get('content',{}))}")

async def show_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Эта команда доступна только администраторам.")
        return
    engineers_count = len(context.bot_data.get('engineers', []))
    content_count = len(context.bot_data.get('content', {}))
    text = (f"**Статус бота:**\n\n✅ **Бот онлайн**\n"
            f"🔗 **Подключение к Google Sheets:** {'Успешно' if sheets.workbook else 'Ошибка'}\n"
            f"👷‍♂️ **Инженеров в кэше:** {engineers_count}\n"
            f"🏛️ **Экспонатов в кэше:** {content_count}")
    await update.message.reply_text(text, parse_mode='Markdown')

async def show_my_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    my_requests = sheets.get_requests_by_demonstrator(user_id)
    if not my_requests:
        await update.message.reply_text("У вас нет созданных заявок.")
        return
    text = "🔍 **Ваши заявки:**\n\n"
    for req in my_requests:
        status_icon = {"Новая": "‼️", "В работе": "⚙️", "Завершена": "✅"}.get(req['status'], "❓")
        text += (f"{status_icon} *#{req['id']}* ({req['status']})\n"
                 f"   Экспонат: {req['exhibit']}\n"
                 f"   Проблема: {req['problem']}\n\n")
    await update.message.reply_text(text, parse_mode='Markdown')

status_handler = CommandHandler("status", show_status)
my_requests_handler = CommandHandler("myrequests", show_my_requests)