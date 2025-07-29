import logging

from telegram.ext import Application, PicklePersistence

from config import BOT_TOKEN
from handlers.common import my_requests_handler, update_data_from_sheets
from handlers.demonstrator import conv_handler
from handlers.engineer import (
    claim_handler,
    completion_conv_handler,
    in_progress_requests_handler,
    new_requests_handler,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def main() -> None:
    persistence = PicklePersistence(filepath="bot_data.pickle")
    application = (
        Application.builder().token(BOT_TOKEN).persistence(persistence).build()
    )

    job_queue = application.job_queue
    job_queue.run_repeating(update_data_from_sheets, interval=300, first=1)

    # Регистрация хендлеров. ПОРЯДОК ВАЖЕН!

    # 1. Диалог создания заявки (он сложный, его оставляем)
    application.add_handler(conv_handler)

    # 2. Обработчики кнопок
    application.add_handler(claim_handler)
    application.add_handler(completion_conv_handler)

    # 3. Обработчики команд
    application.add_handler(new_requests_handler)
    application.add_handler(in_progress_requests_handler)
    application.add_handler(my_requests_handler)

    # 4. Обработчик для комментариев (ставим его в конец, но перед любыми "общими" текстовыми)

    logger.info("Бот запущен и готов к работе!")
    application.run_polling()


if __name__ == "__main__":
    main()
