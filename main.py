import logging
from telegram.ext import Application, PicklePersistence
from config import BOT_TOKEN
from handlers.demonstrator import conv_handler
from handlers.engineer import (
    claim_handler, completion_conv_handler, new_requests_handler, in_progress_requests_handler
)
from handlers.common import status_handler, my_requests_handler, update_data_from_sheets

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

def main() -> None:
    persistence = PicklePersistence(filepath="bot_data.pickle")
    application = Application.builder().token(BOT_TOKEN).persistence(persistence).build()
    
    job_queue = application.job_queue
    job_queue.run_repeating(update_data_from_sheets, interval=300, first=1)
    
    application.add_handler(conv_handler)
    application.add_handler(claim_handler)
    application.add_handler(completion_conv_handler)
    application.add_handler(new_requests_handler)
    application.add_handler(in_progress_requests_handler)
    application.add_handler(status_handler)
    application.add_handler(my_requests_handler)
    
    logger.info("Бот запущен и готов к работе!")
    application.run_polling()

if __name__ == "__main__":
    main()