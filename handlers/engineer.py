import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler
import sheets
import constants as c
from .helpers import is_engineer, get_user_mention, escape_markdown

logger = logging.getLogger(__name__)

async def claim_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    
    if not is_engineer(user.id, context):
        await query.answer("Эту кнопку могут нажимать только инженеры.", show_alert=True)
        return

    request_id = query.data.split(c.CB_CLAIM_PREFIX)[1]
    engineer_name_raw = get_user_mention(user)
    engineer_name_escaped = escape_markdown(engineer_name_raw)

    if sheets.update_request_status(request_id, "В работе", engineer_name_raw):
        # Редактируем сообщение в чате инженеров
        original_text = query.message.text_markdown_v2_urled
        new_text = original_text.replace("‼️ *Новая заявка", "⚙️ *Заявка в работе")
        new_text += f"\n\n👷‍♂️ *Взял в работу:* {engineer_name_escaped}"
        keyboard = [[InlineKeyboardButton("🏁 Завершить", callback_data=f"{c.CB_COMPLETE_PREFIX}{request_id}")]]
        
        try:
            await query.edit_message_text(text=new_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='MarkdownV2')
            await query.answer("Вы взяли заявку в работу!")
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения (claim_request): {e}")
            await query.answer("Ошибка обновления сообщения.", show_alert=True)

        demonstrator_id = context.bot_data.get(f"req_{request_id}_author")
        if demonstrator_id:
            exhibit = "неизвестному экспонату"
            if query.message.text:
                lines = query.message.text.split('\n')
                for line in lines:
                    if "Экспонат:" in line:
                        try:
                            exhibit = line.split(':', 1)[1].strip()
                            break
                        except IndexError:
                            continue
            
            exhibit_escaped = escape_markdown(exhibit)
            request_id_escaped = escape_markdown(request_id)

            await context.bot.send_message(
                chat_id=demonstrator_id,
                text=f"⚙️ Инженер {engineer_name_escaped} взял в работу вашу заявку \\#{request_id_escaped} по экспонату «{exhibit_escaped}»\\.",
                parse_mode='MarkdownV2'
            )

async def complete_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    if not is_engineer(user.id, context):
        await query.answer("Эту кнопку могут нажимать только инженеры.", show_alert=True)
        return
    request_id = query.data.split(c.CB_COMPLETE_PREFIX)[1]
    if sheets.update_request_status(request_id, "Завершена"):
        original_text = query.message.text_markdown_v2_urled
        clean_text = "\n".join(original_text.split('\n')[:-2])
        new_text = clean_text.replace("⚙️ *Заявка в работе", "✅ *Заявка завершена")
        try:
            await query.edit_message_text(text=new_text, reply_markup=None, parse_mode='MarkdownV2')
            await query.answer("Заявка завершена!", show_alert=True)
        except Exception as e:
            logger.error(f"Ошибка при ред-нии сообщения (complete_request): {e}")
            await query.answer("Ошибка обновления сообщения.", show_alert=True)
        demonstrator_id = context.bot_data.get(f"req_{request_id}_author")
        if demonstrator_id:
            text = f"✅ Ваша заявка \\#{escape_markdown(request_id)} была успешно завершена\\!"
            await context.bot.send_message(chat_id=demonstrator_id, text=text, parse_mode='MarkdownV2')
            if f"req_{request_id}_author" in context.bot_data:
                del context.bot_data[f"req_{request_id}_author"]

async def show_requests(update: Update, context: ContextTypes.DEFAULT_TYPE, status: str):
    if not is_engineer(update.message.from_user.id, context):
        await update.message.reply_text("Эта команда доступна только инженерам.")
        return
    try:
        requests = sheets.get_requests_by_status(status)
    except Exception as e:
        logger.error(f"Ошибка при получении данных из sheets: {e}")
        await update.message.reply_text("Произошла ошибка при доступе к таблице.")
        return
    if not requests:
        await update.message.reply_text(f"Нет заявок со статусом '{status}'.")
        return
    response_text = f"*Заявки в статусе '{escape_markdown(status)}':*\n\n"
    keyboard = []
    for req in requests:
        response_text += (f"🆔 `{escape_markdown(req['id'])}`\n"
                          f"🏛 *Экспонат:* {escape_markdown(req['exhibit'])}\n"
                          f"👤 *Демонстратор:* {escape_markdown(req.get('demonstrator_name', 'N/A'))}\n")
        if req.get('engineer_name'):
            response_text += f"👷‍♂️ *В работе:* {escape_markdown(req['engineer_name'])}\n\n"
        else:
            response_text += "\n"
        if status == "Новая":
            keyboard.append([InlineKeyboardButton(text=f"✅ Взять в работу #{req['id']}", callback_data=f"{c.CB_CLAIM_PREFIX}{req['id']}")])
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    try:
        await update.message.reply_text(response_text, reply_markup=reply_markup, parse_mode='MarkdownV2')
    except Exception as e:
        logger.error(f"Ошибка при отправке списка заявок: {e}")
        await update.message.reply_text("Не удалось отформатировать список заявок.")

async def show_new_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_requests(update, context, "Новая")
async def show_in_progress_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_requests(update, context, "В работе")

claim_handler = CallbackQueryHandler(claim_request, pattern=f"^{c.CB_CLAIM_PREFIX}")
complete_handler = CallbackQueryHandler(complete_request, pattern=f"^{c.CB_COMPLETE_PREFIX}")
new_requests_handler = CommandHandler("new", show_new_requests)
in_progress_requests_handler = CommandHandler("inprogress", show_in_progress_requests)