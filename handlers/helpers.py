import re
from telegram import User
from telegram.ext import ContextTypes

def is_engineer(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    return user_id in context.bot_data.get('engineers', [])

def get_user_mention(user: User) -> str:
    return f"@{user.username}" if user.username else user.full_name

def escape_markdown(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    escape_chars = r'\_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)