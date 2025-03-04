import json
from datetime import date, timedelta
from pathlib import Path
from typing import List, Any


def is_weekend(d: date) -> bool:
    """Проверяет, является ли дата выходным (суббота или воскресенье)."""
    return d.weekday() >= 5  # 5 = суббота, 6 = воскресенье


def calculate_working_days(start: date, end: date, holidays: List[date]) -> int:
    """Вычисляет количество рабочих дней между двумя датами (включительно)."""
    delta = end - start
    working_days = 0
    for i in range(delta.days + 1):
        current_date = start + timedelta(days=i)
        if not is_weekend(current_date) and current_date not in holidays:
            working_days += 1
    return working_days


def load_json(file_name: str) -> Any:
    """
       Загружает данные из JSON-файлов в папке data и возвращает их
    """
    data_path = Path("data") / file_name
    if data_path.exists():
        with open(data_path, "r", encoding="utf-8") as file:
            return json.load(file)
