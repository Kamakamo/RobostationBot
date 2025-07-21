import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pandas as pd
import logging
import uuid
from config import GSHEETS_CREDENTIALS_FILE, GSHEETS_TABLE_NAME, SHEET_NAMES

logger = logging.getLogger(__name__)

try:
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(GSHEETS_CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    workbook = client.open(GSHEETS_TABLE_NAME)
except Exception as e:
    logger.error(f"Критическая ошибка подключения к Google Sheets: {e}")
    workbook = None

def get_sheet(sheet_name_key):
    if not workbook: return None
    try:
        return workbook.worksheet(SHEET_NAMES[sheet_name_key])
    except gspread.exceptions.WorksheetNotFound:
        logger.error(f"Лист '{SHEET_NAMES[sheet_name_key]}' не найден!")
        return None

def get_next_request_id():
    """Получает следующий порядковый номер для ID заявки."""
    sheet = get_sheet('requests')
    if not sheet:
        logger.error("Не удалось получить лист 'Заявки' для генерации ID.")
        return None
    # get_all_records() возвращает список словарей, его длина - это количество заявок
    try:
        num_requests = len(sheet.get_all_records())
        return num_requests + 1
    except Exception as e:
        logger.error(f"Ошибка при подсчете записей в таблице: {e}")
        return None

def add_new_request(demonstrator_name, demonstrator_id, exhibit, problem):
    """Добавляет новую заявку в таблицу с последовательным ID и возвращает этот ID."""
    sheet = get_sheet('requests')
    if not sheet: return None

    # Получаем новый ID
    request_id = get_next_request_id()
    if request_id is None:
        # Если не удалось сгенерировать ID, используем старый метод как запасной
        request_id = str(uuid.uuid4())[:8]
        logger.warning(f"Не удалось сгенерировать порядковый ID, используется fallback: {request_id}")

    start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    row = [
        str(request_id), start_time, "", "Новая", exhibit, problem,
        demonstrator_name, str(demonstrator_id), ""
    ]
    sheet.append_row(row)
    
    # Возвращаем сгенерированный ID, чтобы бот мог его использовать
    return request_id

#
# Остальные функции в файле sheets.py остаются без изменений
#
def get_engineers():
    sheet = get_sheet('engineers')
    if not sheet: return []
    records = sheet.get_all_records()
    return [int(record['Telegram ID']) for record in records if record.get('Telegram ID') and str(record['Telegram ID']).isdigit()]

def get_content():
    sheet = get_sheet('content')
    if not sheet: return {}
    records = sheet.get_all_records()
    content = {}
    for row in records:
        exhibit_name = row.get('Экспонат')
        if not exhibit_name: continue
        problems = [value for key, value in row.items() if key.startswith('Проблема') and value]
        content[exhibit_name] = problems
    return content

def update_request_status(request_id, new_status, engineer_name=""):
    sheet = get_sheet('requests')
    if not sheet: return False
    try:
        cell = sheet.find(str(request_id))
        row_number = cell.row
        sheet.update_cell(row_number, 4, new_status) # status
        if new_status == "В работе":
            sheet.update_cell(row_number, 9, engineer_name) # engineer_name
        elif new_status == "Завершена":
            end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            sheet.update_cell(row_number, 3, end_time) # end_time
        return True
    except gspread.exceptions.CellNotFound:
        logger.warning(f"Заявка {request_id} не найдена в таблице для обновления.")
        return False

def get_requests_by_status(status):
    sheet = get_sheet('requests')
    if not sheet: return []
    df = pd.DataFrame(sheet.get_all_records())
    if df.empty or 'status' not in df.columns: return []
    return df[df['status'] == status].to_dict('records')

def get_requests_by_demonstrator(demonstrator_id):
    sheet = get_sheet('requests')
    if not sheet: return []
    df = pd.DataFrame(sheet.get_all_records())
    if df.empty or 'demonstrator_id' not in df.columns: return []
    return df[df['demonstrator_id'] == str(demonstrator_id)].to_dict('records')