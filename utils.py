import json
from datetime import date, timedelta
from pathlib import Path
from typing import List, Any, Dict

from models import Orders, WorkPlan, InputData, TaskDetails


def aggregate_work_plan(orders: Orders, work_plan: WorkPlan, input_data: InputData) -> Dict[str, TaskDetails]:
    # 1. Создаём словари для быстрого поиска
    task_dict = {}
    for order in orders.root:
        for task in order.tasks:
            task_dict[task.id] = (task, order)

    worker_dict = {worker.id: worker for worker in input_data.workers}

    # 2. Перебираем все назначенные задачи, извлекая по пути работников и заказы
    result = {}
    for assigned_task in work_plan.root:
        if assigned_task.taskId in task_dict:
            task, order = task_dict[assigned_task.taskId]
            worker = worker_dict.get(assigned_task.workerId)
            if worker:
                result[assigned_task.taskId] = TaskDetails(
                    assigned_task=assigned_task,
                    task=task,
                    order=order,
                    worker=worker
                )

    print(f"Всего задач: {len(task_dict)}")
    print(f"Задач в плане работ: {len(result)}")
    return result


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
