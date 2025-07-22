import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Chat
from telegram.ext import (
    ConversationHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes, CommandHandler
)
import sheets
import constants as c
from config import ENGINEERS_CHAT_ID
from . import helpers

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_type = update.message.chat.type
    if chat_type in [Chat.GROUP, Chat.SUPERGROUP]:
        bot_username = context.bot.username
        deep_link = f"https://t.me/{bot_username}?start=new_request"
        keyboard = [[InlineKeyboardButton("🚀 Создать заявку в ЛС", url=deep_link)]]
        await update.message.reply_text(
            "Для создания заявки, пожалуйста, перейдите в личный чат со мной.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END
    else:
        keyboard = [[InlineKeyboardButton("Создать заявку", callback_data=c.CB_NEW_REQUEST)]]
        await update.message.reply_text(
            "Здравствуйте! Я бот для помощи с экспонатами.", 
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return c.SELECTING_EXHIBIT

async def select_exhibit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    exhibits = context.bot_data.get('content', {}).keys()
    if not exhibits:
        await query.edit_message_text("Ошибка: не удалось загрузить список экспонатов.")
        return ConversationHandler.END
    keyboard = [[InlineKeyboardButton(exhibit, callback_data=f"{c.CB_EXHIBIT_PREFIX}{exhibit}")] for exhibit in exhibits]
    await query.edit_message_text(text="Шаг 1: Выберите экспонат", reply_markup=InlineKeyboardMarkup(keyboard))
    return c.SELECTING_PROBLEM

async def select_problem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    exhibit_name = query.data.split(c.CB_EXHIBIT_PREFIX)[1]
    context.user_data['exhibit'] = exhibit_name
    problems = context.bot_data['content'].get(exhibit_name, [])
    keyboard = [[InlineKeyboardButton(p, callback_data=f"{c.CB_PROBLEM_PREFIX}{p}")] for p in problems]
    keyboard.append([InlineKeyboardButton("Другое (описать текстом)", callback_data=c.CB_CUSTOM_PROBLEM)])
    keyboard.append([InlineKeyboardButton("⬅️ Назад к экспонатам", callback_data=c.CB_BACK_TO_EXHIBIT)])
    await query.edit_message_text(text=f"Экспонат: {exhibit_name}\n\nШаг 2: Опишите проблему", reply_markup=InlineKeyboardMarkup(keyboard))
    return c.SUBMITTING

async def back_to_exhibit_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await select_exhibit(update, context)

async def custom_problem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Опишите проблему своими словами и отправьте сообщение.")
    return c.TYPING_PROBLEM

async def submit_problem_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['problem'] = update.message.text
    await submit_request(update, context)
    return ConversationHandler.END

async def submit_problem_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['problem'] = query.data.split(c.CB_PROBLEM_PREFIX)[1]
    await submit_request(query, context)
    return ConversationHandler.END

async def submit_request(source, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(source, Update): user = source.message.from_user
    else: user = source.from_user
    
    demonstrator_username_raw = helpers.get_user_mention(user)
    demonstrator_id = user.id
    exhibit_raw = context.user_data['exhibit']
    problem_raw = context.user_data['problem']
    
    request_id = sheets.add_new_request(demonstrator_username_raw, exhibit_raw, problem_raw)
    if request_id is None:
        error_text = "Произошла ошибка при сохранении заявки. Пожалуйста, попробуйте снова."
        if isinstance(source, Update): await source.message.reply_text(error_text)
        else: await source.edit_message_text(error_text)
        return

    context.bot_data[f"req_{request_id}_author"] = demonstrator_id
    
    text_for_engineers = (f"‼️ *Новая заявка \\#{helpers.escape_markdown(str(request_id))}* ‼️\n\n"
                        f"👤 *Демонстратор:* {helpers.escape_markdown(demonstrator_username_raw)}\n"
                        f"🏛 *Экспонат:* {helpers.escape_markdown(exhibit_raw)}\n"
                        f"🔧 *Проблема:* {helpers.escape_markdown(problem_raw)}")
                        
    keyboard = [[InlineKeyboardButton("✅ Взять в работу", callback_data=f"{c.CB_CLAIM_PREFIX}{request_id}")]]
    
    sent_message = await context.bot.send_message(
        chat_id=ENGINEERS_CHAT_ID,
        text=text_for_engineers,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='MarkdownV2'
    )
    
    helpers.track_request_message(context, str(request_id), sent_message.chat_id, sent_message.message_id)
    
    final_text = f"✅ Ваша заявка #{request_id} принята."
    if isinstance(source, Update):
        await source.message.reply_text(final_text)
    else:
        await source.edit_message_text(final_text)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    source = update.callback_query
    if source:
        await source.answer()
        await source.edit_message_text("Действие отменено.")
    elif update.message:
        await update.message.reply_text("Действие отменено.")
    context.user_data.clear()
    return ConversationHandler.END

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start), CallbackQueryHandler(select_exhibit, pattern=f"^{c.CB_NEW_REQUEST}$")],
    states={
        c.SELECTING_EXHIBIT: [CallbackQueryHandler(select_exhibit, pattern=f"^{c.CB_NEW_REQUEST}$")],
        c.SELECTING_PROBLEM: [CallbackQueryHandler(select_problem, pattern=f"^{c.CB_EXHIBIT_PREFIX}")],
        c.SUBMITTING: [
            CallbackQueryHandler(submit_problem_button, pattern=f"^{c.CB_PROBLEM_PREFIX}"),
            CallbackQueryHandler(custom_problem, pattern=f"^{c.CB_CUSTOM_PROBLEM}$"),
            CallbackQueryHandler(back_to_exhibit_selection, pattern=f"^{c.CB_BACK_TO_EXHIBIT}$"),
        ],
        c.TYPING_PROBLEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, submit_problem_text)],
    },
    fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(cancel, pattern=f"^{c.CB_CANCEL}$")],
    per_user=True,
    per_message=False,
)