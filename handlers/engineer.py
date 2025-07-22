import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, CallbackQueryHandler, CommandHandler, ConversationHandler, MessageHandler, filters
)
import sheets
import constants as c
from . import helpers
from config import ENGINEERS_CHAT_ID

logger = logging.getLogger(__name__)

async def start_completion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    request_id = str(query.data.split(c.CB_COMPLETE_PREFIX)[1])
    context.user_data['completing_request_id'] = request_id
    await query.edit_message_text(
        text=f"Завершение заявки \\#{helpers.escape_markdown(request_id)}\\.\n\n"
             "Пожалуйста, отправьте сообщение с кратким описанием решения проблемы\\.\n\n"
             "Чтобы отменить, введите /cancel\\.",
        parse_mode='MarkdownV2'
    )
    return c.AWAITING_COMMENT

async def save_comment_and_complete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    comment = update.message.text
    request_id = context.user_data.get('completing_request_id')
    if not request_id:
        await update.message.reply_text("Произошла ошибка, не могу найти ID заявки.")
        return ConversationHandler.END

    if sheets.update_request_status(request_id, "Завершена", comment=comment):
        await update.message.reply_text(f"✅ Заявка #{request_id} успешно завершена.")
        await helpers.delete_tracked_messages(context, request_id)
        
        all_requests = sheets.get_requests_by_status("Завершена")
        req_data = next((r for r in all_requests if r['id'] == request_id), None)
        
        if req_data:
            final_text = (f"✅ *Заявка \\#{helpers.escape_markdown(request_id)} завершена*\n"
                          f"👷‍♂️ *Инженер:* {helpers.escape_markdown(req_data.get('engineer_username', ''))}\n"
                          f"📝 *Комментарий:* {helpers.escape_markdown(comment)}")
            await context.bot.send_message(chat_id=ENGINEERS_CHAT_ID, text=final_text, parse_mode='MarkdownV2')

        demonstrator_id = context.bot_data.get(f"req_{request_id}_author")
        if demonstrator_id:
            await context.bot.send_message(
                chat_id=demonstrator_id,
                text=f"✅ Ваша заявка \\#{helpers.escape_markdown(request_id)} была успешно завершена\\!",
                parse_mode='MarkdownV2'
            )
        
        if f"req_{request_id}_author" in context.bot_data: del context.bot_data[f"req_{request_id}_author"]
    else:
        await update.message.reply_text("Не удалось обновить статус заявки в таблице.")

    context.user_data.clear()
    return ConversationHandler.END

async def cancel_completion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Завершение заявки отменено.")
    context.user_data.clear()
    return ConversationHandler.END

async def claim_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    if not helpers.is_engineer(user.id, context):
        await query.answer("Эту кнопку могут нажимать только инженеры.", show_alert=True)
        return
    request_id = str(query.data.split(c.CB_CLAIM_PREFIX)[1])
    if not sheets.is_request_new(request_id):
        await query.answer("Эта заявка уже была взята в работу!", show_alert=True)
        await helpers.delete_tracked_messages(context, request_id)
        return
    engineer_username_raw = helpers.get_user_mention(user)
    engineer_name_raw = sheets.get_engineer_name_by_id(user.id) or engineer_username_raw
    if sheets.update_request_status(request_id, "В работе", engineer_username_raw, engineer_name_raw):
        await query.answer("Вы взяли заявку в работу!")
        await helpers.delete_tracked_messages(context, request_id)
        all_requests = sheets.get_requests_by_status("В работе")
        req_data = next((r for r in all_requests if r['id'] == request_id), None)
        if req_data:
            text = (f"⚙️ *Заявка \\#{helpers.escape_markdown(request_id)} взята в работу*\n"
                    f"👷‍♂️ *Инженер:* {helpers.escape_markdown(engineer_username_raw)} \\({helpers.escape_markdown(engineer_name_raw)}\\)\n"
                    f"🏛 *Экспонат:* {helpers.escape_markdown(req_data['Экспонат'])}")
            await context.bot.send_message(chat_id=ENGINEERS_CHAT_ID, text=text, parse_mode='MarkdownV2')
        demonstrator_id = context.bot_data.get(f"req_{request_id}_author")
        if demonstrator_id and req_data:
            await context.bot.send_message(
                chat_id=demonstrator_id,
                text=f"⚙️ Инженер {helpers.escape_markdown(engineer_name_raw)} взял в работу вашу заявку \\#{helpers.escape_markdown(request_id)} по экспонату «{helpers.escape_markdown(req_data['Экспонат'])}»\\.",
                parse_mode='MarkdownV2'
            )

async def show_requests(update: Update, context: ContextTypes.DEFAULT_TYPE, status: str):
    if not helpers.is_engineer(update.message.from_user.id, context):
        await update.message.reply_text("Эта команда доступна только инженерам.")
        return
    requests = sheets.get_requests_by_status(status)
    if not requests:
        await update.message.reply_text(f"Нет заявок со статусом '{status}'.")
        return
    await update.message.reply_text(f"*Заявки в статусе '{helpers.escape_markdown(status)}':*", parse_mode='MarkdownV2')
    for req in requests:
        req_id = str(req['id'])
        text = (f"🆔 `{helpers.escape_markdown(req_id)}`\n"
                f"🏛 *Экспонат:* {helpers.escape_markdown(req['Экспонат'])}\n"
                f"👤 *Демонстратор:* {helpers.escape_markdown(req.get('demonstrator_username', 'N/A'))}\n")
        keyboard = []
        if status == "Новая":
            keyboard.append([InlineKeyboardButton(text=f"✅ Взять в работу #{req_id}", callback_data=f"{c.CB_CLAIM_PREFIX}{req_id}")])
        elif status == "В работе":
             text += f"👷‍♂️ *Ответственный:* {helpers.escape_markdown(req.get('Ответственный',''))}"
             keyboard.append([InlineKeyboardButton(text=f"🏁 Завершить #{req_id}", callback_data=f"{c.CB_COMPLETE_PREFIX}{req_id}")])
        sent_message = await update.message.reply_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
            parse_mode='MarkdownV2'
        )
        helpers.track_request_message(context, req_id, sent_message.chat_id, sent_message.message_id)

async def show_new_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_requests(update, context, "Новая")

async def show_in_progress_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_requests(update, context, "В работе")

claim_handler = CallbackQueryHandler(claim_request, pattern=f"^{c.CB_CLAIM_PREFIX}")
new_requests_handler = CommandHandler("new", show_new_requests)
in_progress_requests_handler = CommandHandler("inprogress", show_in_progress_requests)
completion_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_completion, pattern=f"^{c.CB_COMPLETE_PREFIX}")],
    states={
        c.AWAITING_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_comment_and_complete)]
    },
    fallbacks=[CommandHandler("cancel", cancel_completion)],
    per_user=True
)