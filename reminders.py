import logging
from datetime import datetime, timedelta
from typing import Dict, List

from telegram.ext import ContextTypes

import sheets
from handlers.helpers import get_user_mention, escape_markdown

logger = logging.getLogger(__name__)


def track_request_claim_time(context: ContextTypes.DEFAULT_TYPE, request_id: str, engineer_id: int):
    """Сохранить время взятия заявки в работу"""
    claim_time = datetime.now()
    context.bot_data[f"claim_time_{request_id}"] = {
        "engineer_id": engineer_id,
        "claim_time": claim_time,
        "last_reminder_time": None  # Время последнего отправленного напоминания
    }
    logger.info(f"Отслеживание времени для заявки {request_id}, инженер {engineer_id}")


def cleanup_request_tracking(context: ContextTypes.DEFAULT_TYPE, request_id: str):
    """Очистить данные отслеживания заявки при ее завершении"""
    key = f"claim_time_{request_id}"
    if key in context.bot_data:
        del context.bot_data[key]
        logger.info(f"Очищены данные отслеживания для заявки {request_id}")


async def check_and_send_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Проверить заявки в работе и отправить напоминания при необходимости"""
    current_time = datetime.now()
    reminder_threshold = timedelta(minutes=30)  # Изменено с 1 часа на 30 минут
    
    # Получаем все заявки в работе
    in_progress_requests = sheets.get_requests_by_status("В работе")
    
    if not in_progress_requests:
        logger.debug("Нет заявок в работе для проверки напоминаний")
        return
    
    reminders_sent = 0
    
    for request in in_progress_requests:
        request_id = str(request.get("id", ""))
        if not request_id:
            continue
            
        tracking_key = f"claim_time_{request_id}"
        tracking_data = context.bot_data.get(tracking_key)
        
        if not tracking_data:
            # Если нет данных отслеживания, возможно заявка была взята до внедрения системы
            logger.debug(f"Нет данных отслеживания для заявки {request_id}")
            continue
            
        engineer_id = tracking_data.get("engineer_id")
        claim_time = tracking_data.get("claim_time")
        last_reminder_time = tracking_data.get("last_reminder_time")
        
        if not engineer_id or not claim_time:
            continue
            
        # Проверяем, нужно ли отправить напоминание
        should_send_reminder = False
        
        if last_reminder_time is None:
            # Первое напоминание - проверяем, прошло ли 30 минут с момента взятия заявки
            time_since_claim = current_time - claim_time
            if time_since_claim >= reminder_threshold:
                should_send_reminder = True
        else:
            # Повторное напоминание - проверяем, прошло ли 30 минут с последнего напоминания
            time_since_last_reminder = current_time - last_reminder_time
            if time_since_last_reminder >= reminder_threshold:
                should_send_reminder = True
        
        if should_send_reminder:
            # Отправляем напоминание
            try:
                exhibit_name = request.get("Экспонат", "Неизвестно")
                problem = request.get("Проблема", "")
                
                # Определяем текст напоминания в зависимости от того, первое это напоминание или повторное
                if last_reminder_time is None:
                    time_text = "более 30 минут назад"
                else:
                    time_since_claim = current_time - claim_time
                    hours = int(time_since_claim.total_seconds() // 3600)
                    minutes = int((time_since_claim.total_seconds() % 3600) // 60)
                    if hours > 0:
                        time_text = f"более {hours} ч {minutes} мин назад"
                    else:
                        time_text = f"более {minutes} мин назад"
                
                reminder_text = (
                    f"⏰ *Напоминание о заявке*\n\n"
                    f"Вы взяли в работу заявку \\#{escape_markdown(request_id)} "
                    f"{escape_markdown(time_text)}\\.\n\n"
                    f"🏛 *Экспонат:* {escape_markdown(exhibit_name)}\n"
                    f"🔧 *Проблема:* {escape_markdown(problem)}\n\n"
                    f"Пожалуйста, не забудьте завершить заявку после решения проблемы\\!"
                )
                
                await context.bot.send_message(
                    chat_id=engineer_id,
                    text=reminder_text,
                    parse_mode="MarkdownV2"
                )
                
                # Обновляем время последнего напоминания
                context.bot_data[tracking_key]["last_reminder_time"] = current_time
                reminders_sent += 1
                
                logger.info(f"Отправлено напоминание инженеру {engineer_id} о заявке {request_id}")
                
            except Exception as e:
                logger.error(f"Ошибка отправки напоминания инженеру {engineer_id} о заявке {request_id}: {e}")
    
    if reminders_sent > 0:
        logger.info(f"Отправлено {reminders_sent} напоминаний инженерам")