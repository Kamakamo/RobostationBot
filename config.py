import os
from dotenv import load_dotenv

load_dotenv()

# --- Читаем конфигурацию из переменных окружения ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ENGINEERS_CHAT_ID = os.getenv("ENGINEERS_CHAT_ID")
GSHEETS_TABLE_NAME = os.getenv("GSHEETS_TABLE_NAME")
MENTION_ON_NEW_REQUEST = os.getenv("MENTION_ON_NEW_REQUEST")

# --- Статические настройки ---
GSHEETS_CREDENTIALS_FILE = 'credentials.json'
SHEET_NAMES = {
    'requests': 'Заявки',
    'engineers': 'Инженеры',
    'content': 'Экспонаты'
}

if not all([BOT_TOKEN, ENGINEERS_CHAT_ID, GSHEETS_TABLE_NAME]):
    raise ValueError("Необходимо задать все обязательные переменные окружения: BOT_TOKEN, ENGINEERS_CHAT_ID, GSHEETS_TABLE_NAME")