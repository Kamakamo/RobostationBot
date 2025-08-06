import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import constants as c
import reminders
import sheets
from config import ENGINEERS_CHAT_ID

from . import helpers

logger = logging.getLogger(__name__)

# --- ДИАЛОГ ЗАВЕРШЕНИЯ ЗАЯВКИ ---


async def start_completion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    request_id = str(query.data.split(c.CB_COMPLETE_PREFIX)[1])
    context.user_data["completing_request_id"] = request_id

    keyboard = [
        [
            InlineKeyboardButton(
                "🔄 Перезагрузка",
                callback_data=f"{c.CB_COMPLETE_REBOOT}{request_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "📝 Другое",
                callback_data=f"{c.CB_COMPLETE_OTHER}{request_id}"
            )
        ]
    ]

    await query.edit_message_text(
        text=f"Завершение заявки \\#{helpers.escape_markdown(request_id)}\\.\n\n"
        "Выберите тип решения проблемы:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="MarkdownV2",
    )
    return c.AWAITING_COMMENT


async def complete_with_reboot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    request_id = str(query.data.split(c.CB_COMPLETE_REBOOT)[1])
    comment = "Перезагрузка"

    if sheets.update_request_status(request_id, "Завершена", comment=comment):
        await query.edit_message_text(
            f"✅ Заявка #{request_id} успешно завершена с решением: Перезагрузка."
        )

        all_requests = sheets.get_requests_by_status("Завершена")
        req_data = next((r for r in all_requests if r["id"] == request_id), None)

        if req_data:
            final_text = (
                f"✅ *Заявка \\#{helpers.escape_markdown(request_id)} завершена*\n"
                f"👷‍♂️ *Инженер:* {helpers.escape_markdown(req_data.get('engineer_username', ''))}\n"
                f"📝 *Решение:* {helpers.escape_markdown(comment)}"
            )
            await context.bot.send_message(
                chat_id=ENGINEERS_CHAT_ID, text=final_text, parse_mode="MarkdownV2"
            )

        demonstrator_id = context.bot_data.get(f"req_{request_id}_author")
        if demonstrator_id:
            await context.bot.send_message(
                chat_id=demonstrator_id,
                text=f"✅ Ваша заявка \\#{helpers.escape_markdown(request_id)} была успешно завершена\\!",
                parse_mode="MarkdownV2",
            )

        if f"req_{request_id}_author" in context.bot_data:
            del context.bot_data[f"req_{request_id}_author"]
        
        # Очищаем данные отслеживания напоминаний
        reminders.cleanup_request_tracking(context, request_id)
    else:
        await query.edit_message_text("Не удалось обновить статус заявки в таблице.")

    context.user_data.clear()
    return ConversationHandler.END


async def start_other_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    request_id = str(query.data.split(c.CB_COMPLETE_OTHER)[1])
    context.user_data["completing_request_id"] = request_id

    await query.edit_message_text(
        text=f"Завершение заявки \\#{helpers.escape_markdown(request_id)}\\.\n\n"
        "Пожалуйста, напишите комментарий с описанием решения проблемы\\.\n\n"
        "Чтобы отменить, введите /cancel\\.",
        parse_mode="MarkdownV2",
    )
    return c.AWAITING_OTHER_COMMENT


async def save_comment_and_complete(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    user_comment = update.message.text
    request_id = context.user_data.get("completing_request_id")

    if not request_id:
        await update.message.reply_text("Произошла ошибка, не могу найти ID заявки.")
        return ConversationHandler.END

    # Добавляем префикс "Другое:" к комментарию
    comment = f"Другое: {user_comment}"

    if sheets.update_request_status(request_id, "Завершена", comment=comment):
        await update.message.reply_text(
            f"✅ Заявка #{request_id} успешно завершена с вашим комментарием."
        )

        all_requests = sheets.get_requests_by_status("Завершена")
        req_data = next((r for r in all_requests if r["id"] == request_id), None)

        if req_data:
            final_text = (
                f"✅ *Заявка \\#{helpers.escape_markdown(request_id)} завершена*\n"
                f"👷‍♂️ *Инженер:* {helpers.escape_markdown(req_data.get('engineer_username', ''))}\n"
                f"📝 *Решение:* {helpers.escape_markdown(comment)}"
            )
            await context.bot.send_message(
                chat_id=ENGINEERS_CHAT_ID, text=final_text, parse_mode="MarkdownV2"
            )

        demonstrator_id = context.bot_data.get(f"req_{request_id}_author")
        if demonstrator_id:
            await context.bot.send_message(
                chat_id=demonstrator_id,
                text=f"✅ Ваша заявка \\#{helpers.escape_markdown(request_id)} была успешно завершена\\!",
                parse_mode="MarkdownV2",
            )

        if f"req_{request_id}_author" in context.bot_data:
            del context.bot_data[f"req_{request_id}_author"]
        
        # Очищаем данные отслеживания напоминаний
        reminders.cleanup_request_tracking(context, request_id)
    else:
        await update.message.reply_text("Не удалось обновить статус заявки в таблице.")

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_completion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    request_id = context.user_data.get("completing_request_id")
    await update.message.reply_text(
        f"Завершение заявки #{request_id} отменено. Она остается в статусе 'В работе'."
    )
    context.user_data.clear()
    return ConversationHandler.END


# --- ОСНОВНАЯ ЛОГИКА ---


async def claim_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    if not helpers.is_engineer(user.id, context):
        await query.answer(
            "Эту кнопку могут нажимать только инженеры.", show_alert=True
        )
        return

    request_id = str(query.data.split(c.CB_CLAIM_PREFIX)[1])

    if not sheets.is_request_new(request_id):
        await query.answer("Эта заявка уже была взята в работу!", show_alert=True)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    engineer_username_raw = helpers.get_user_mention(user)
    engineer_name_raw = sheets.get_engineer_name_by_id(user.id) or engineer_username_raw

    if not sheets.update_request_status(
        request_id, "В работе", engineer_username_raw, engineer_name_raw
    ):
        await query.answer(
            "Произошла ошибка при обновлении статуса в таблице.", show_alert=True
        )
        return

    # Начинаем отслеживание времени для напоминаний
    reminders.track_request_claim_time(context, request_id, user.id)

    await query.answer(
        "Вы взяли заявку в работу! Карточка задачи отправлена вам в личные сообщения."
    )

    original_text_v2 = query.message.text_markdown_v2
    try:
        header, body = original_text_v2.split("\n\n", 1)
    except ValueError:
        header = ""
        body = original_text_v2

    new_header_in_group = "⚙️ *Заявка в работе*"
    new_text_in_group = (
        f"{new_header_in_group}\n\n"
        f"{body}\n\n"
        f"👷‍♂️ *Взял в работу:* {helpers.escape_markdown(engineer_username_raw)}"
    )
    await query.edit_message_text(
        text=new_text_in_group, reply_markup=None, parse_mode="MarkdownV2"
    )

    text_for_pm = (
        f"Вы взяли в работу заявку \\#{helpers.escape_markdown(request_id)}\\.\n\n"
        f"{body}"
    )
    keyboard = [
        [
            InlineKeyboardButton(
                text=f"🏁 Завершить #{request_id}",
                callback_data=f"{c.CB_COMPLETE_PREFIX}{request_id}",
            )
        ]
    ]

    try:
        await context.bot.send_message(
            chat_id=user.id,
            text=text_for_pm,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="MarkdownV2",
        )
    except Exception as e:
        logger.error(f"Не удалось отправить ЛС инженеру {user.id}: {e}")
        await query.message.reply_text(
            f"{helpers.escape_markdown(engineer_username_raw)}, не могу отправить вам личное сообщение\\. "
            f"Пожалуйста, начните диалог со мной и используйте команду `/inprogress` для управления заявкой\\.",
            parse_mode="MarkdownV2",
        )

    demonstrator_id = context.bot_data.get(f"req_{request_id}_author")
    if demonstrator_id:
        exhibit_match = re.search(r"🏛 \*Экспонат:\* (.+)", query.message.text)
        exhibit_name = exhibit_match.group(1) if exhibit_match else "..."

        await context.bot.send_message(
            chat_id=demonstrator_id,
            text=f"⚙️ Инженер {helpers.escape_markdown(engineer_username_raw)} взял в работу вашу заявку \\#{helpers.escape_markdown(request_id)} "
            f"по экспонату\\.",
            parse_mode="MarkdownV2",
        )


async def show_requests(
    update: Update, context: ContextTypes.DEFAULT_TYPE, status: str
):
    user = update.message.from_user
    if not helpers.is_engineer(user.id, context):
        await update.message.reply_text("Эта команда доступна только инженерам.")
        return

    requests = sheets.get_requests_by_status(status)
    if not requests:
        await update.message.reply_text(f"✅ Нет заявок со статусом «{status}».")
        return

    await update.message.reply_text(
        f"*{helpers.escape_markdown(f'Заявки в статусе «{status}»')}:*",
        parse_mode="MarkdownV2",
    )

    user_mention = helpers.get_user_mention(user)
    found_own_request = False

    for req in requests:
        req_id = str(req["id"])
        text = (
            f"🆔 `{helpers.escape_markdown(req_id)}`\n"
            f"🏛 *Экспонат:* {helpers.escape_markdown(req['Экспонат'])}\n"
            f"👤 *Демонстратор:* {helpers.escape_markdown(req.get('demonstrator_username', 'N/A'))}\n"
            f"🔧 *Проблема:* {helpers.escape_markdown(req.get('Проблема', '–'))}"
        )

        keyboard = []
        if status == "Новая":
            keyboard.append(
                [
                    InlineKeyboardButton(
                        text=f"✅ Взять в работу #{req_id}",
                        callback_data=f"{c.CB_CLAIM_PREFIX}{req_id}",
                    )
                ]
            )
        elif status == "В работе":
            text += f"\n👷‍♂️ *Ответственный:* {helpers.escape_markdown(req.get('Ответственный', ''))}"
            if req.get("engineer_username") == user_mention:
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            text=f"🏁 Завершить #{req_id}",
                            callback_data=f"{c.CB_COMPLETE_PREFIX}{req_id}",
                        )
                    ]
                )
                found_own_request = True

        await update.message.reply_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
            parse_mode="MarkdownV2",
        )

    if status == "В работе" and not found_own_request:
        await update.message.reply_text("ℹ️ У вас нет назначенных заявок в работе.")


async def show_new_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_requests(update, context, "Новая")


async def show_in_progress_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_requests(update, context, "В работе")


# --- ЭКСПОРТИРУЕМЫЕ ХЕНДЛЕРЫ ---

claim_handler = CallbackQueryHandler(claim_request, pattern=f"^{c.CB_CLAIM_PREFIX}")
new_requests_handler = CommandHandler("new", show_new_requests)
in_progress_requests_handler = CommandHandler("inprogress", show_in_progress_requests)

completion_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(start_completion, pattern=f"^{c.CB_COMPLETE_PREFIX}")
    ],
    states={
        c.AWAITING_COMMENT: [
            CallbackQueryHandler(complete_with_reboot, pattern=f"^{c.CB_COMPLETE_REBOOT}"),
            CallbackQueryHandler(start_other_comment, pattern=f"^{c.CB_COMPLETE_OTHER}"),
        ],
        c.AWAITING_OTHER_COMMENT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, save_comment_and_complete)
        ]
    },
    fallbacks=[CommandHandler("cancel", cancel_completion)],
    per_user=True,
    per_message=False,
    conversation_timeout=1800,
)
