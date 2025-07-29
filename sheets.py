import logging
import uuid
from datetime import datetime

import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials

from config import GSHEETS_CREDENTIALS_FILE, GSHEETS_TABLE_NAME, SHEET_NAMES

logger = logging.getLogger(__name__)

try:
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        GSHEETS_CREDENTIALS_FILE, scope
    )
    client = gspread.authorize(creds)
    workbook = client.open(GSHEETS_TABLE_NAME)
except Exception as e:
    logger.error(f"Критическая ошибка подключения к Google Sheets: {e}")
    workbook = None


def get_sheet(sheet_name_key):
    if not workbook:
        return None
    try:
        return workbook.worksheet(SHEET_NAMES[sheet_name_key])
    except gspread.exceptions.WorksheetNotFound:
        logger.error(f"Лист '{SHEET_NAMES[sheet_name_key]}' не найден!")
        return None


def get_engineer_name_by_id(engineer_id: int):
    sheet = get_sheet("engineers")
    if not sheet:
        return None
    try:
        cell = sheet.find(str(engineer_id))
        return sheet.cell(cell.row, 1).value
    except (gspread.exceptions.CellNotFound, AttributeError):
        return None


def get_next_request_id():
    sheet = get_sheet("requests")
    if not sheet:
        logger.error("Не удалось получить лист 'Заявки' для генерации ID.")
        return None
    try:
        num_requests = len(sheet.get_all_records())
        return num_requests + 1
    except Exception as e:
        logger.error(f"Ошибка при подсчете записей в таблице: {e}")
        return None


def add_new_request(demonstrator_username, exhibit, problem):
    sheet = get_sheet("requests")
    if not sheet:
        return None
    request_id = get_next_request_id()
    if request_id is None:
        request_id = str(uuid.uuid4())[:8]
    start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = [
        str(request_id),
        start_time,
        "",
        "Новая",
        exhibit,
        problem,
        demonstrator_username,
        "",
        "",
        "",
    ]
    sheet.append_row(row)
    return request_id


def update_request_status(
    request_id, new_status, engineer_username="", engineer_name="", comment=""
):
    sheet = get_sheet("requests")
    if not sheet:
        return False
    try:
        cell = sheet.find(str(request_id))
        row_number = cell.row
        sheet.update_cell(row_number, 4, new_status)
        if new_status == "В работе":
            sheet.update_cell(row_number, 8, engineer_username)
            sheet.update_cell(row_number, 9, engineer_name)
        elif new_status == "Завершена":
            end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sheet.update_cell(row_number, 3, end_time)
            sheet.update_cell(row_number, 10, comment)
        return True
    except gspread.exceptions.CellNotFound:
        return False


def is_request_new(request_id: str) -> bool:
    sheet = get_sheet("requests")
    if not sheet:
        return False
    try:
        cell = sheet.find(str(request_id))
        if not cell:
            return False
        status = sheet.cell(cell.row, 4).value
        return status.strip().lower() == "новая"
    except (gspread.exceptions.CellNotFound, AttributeError) as e:
        logger.error(f"Ошибка при проверке статуса заявки {request_id}: {e}")
        return False


def get_engineers():
    sheet = get_sheet("engineers")
    if not sheet:
        return []
    records = sheet.get_all_records()
    return [
        int(record["Telegram ID"])
        for record in records
        if record.get("Telegram ID") and str(record["Telegram ID"]).isdigit()
    ]


def get_content():
    sheet = get_sheet("content")
    if not sheet:
        return {}
    records = sheet.get_all_records()
    content = {}
    for row in records:
        exhibit_name = row.get("Экспонат")
        if not exhibit_name:
            continue
        problems = [
            value for key, value in row.items() if key.startswith("Проблема") and value
        ]
        content[exhibit_name] = problems
    return content


def get_requests_by_status(status):
    sheet = get_sheet("requests")
    if not sheet:
        return []
    df = pd.DataFrame(sheet.get_all_records())
    if df.empty or "Статус" not in df.columns:
        return []
    return df[df["Статус"] == status].to_dict("records")


def get_requests_by_demonstrator(demonstrator_username: str):
    sheet = get_sheet("requests")
    if not sheet:
        return []
    df = pd.DataFrame(sheet.get_all_records())
    if df.empty or "demonstrator_username" not in df.columns:
        return []
    return df[df["demonstrator_username"] == demonstrator_username].to_dict("records")
