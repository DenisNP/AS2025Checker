import json
from datetime import date, timedelta
from pathlib import Path
from typing import List, Any, Dict, Optional
from math import ceil

from models import Orders, WorkPlan, InputData, TaskDetails
from models.orders import Order
from models.work_plan import AssignedTask


def aggregate_work_plan(orders: Orders, work_plan: WorkPlan, input_data: InputData) -> (Dict[str, TaskDetails], int):
    # 1. Создаём словари для быстрого поиска
    task_dict = {}
    for order in orders.root:
        for task in order.tasks:
            task_dict[task.id] = (task, order)

    worker_dict = {worker.id: worker for worker in input_data.workers}

    # 2. Перебираем все назначенные задачи, извлекая по пути работников и заказы
    result = {}
    min_date = date.max
    max_date = date.min
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
                if assigned_task.start < min_date:
                    min_date = assigned_task.start
                if assigned_task.end > max_date:
                    max_date = assigned_task.end

    total_days = (max_date - min_date).days + 1

    return result, total_days


def is_weekend(d: date) -> bool:
    """Проверяет, является ли дата выходным (суббота или воскресенье)."""
    return d.weekday() >= 5  # 5 = суббота, 6 = воскресенье


def calculate_order_duration(order: Order) -> int:
    """
    Вычисляет длительность заказа с учетом зависимостей между задачами.
    """
    # Создаем словарь для хранения максимальной длительности пути до каждой задачи
    max_durations = {}
    
    def get_max_path_duration(task_id: str) -> int:
        # Если длительность уже посчитана - возвращаем её
        if task_id in max_durations:
            return max_durations[task_id]
            
        # Находим задачу по id
        task = next(t for t in order.tasks if t.id == task_id)
        
        # Если нет зависимостей, возвращаем базовую длительность
        if not task.dependsOn:
            max_durations[task_id] = task.baseDuration
            return task.baseDuration
            
        # Иначе находим максимальный путь через зависимости
        max_dep_duration = max(get_max_path_duration(dep_id) for dep_id in task.dependsOn)
        total_duration = max_dep_duration + task.baseDuration
        
        max_durations[task_id] = total_duration
        return total_duration
    
    # Находим максимальную длительность для всех конечных задач
    return max(get_max_path_duration(task.id) for task in order.tasks)


def calculate_working_days(start: date, end: date, holidays: List[date]) -> int:
    """Вычисляет количество рабочих дней между двумя датами (включительно)."""
    delta = end - start
    working_days = 0
    for i in range(delta.days + 1):
        current_date = start + timedelta(days=i)
        if not is_weekend(current_date) and current_date not in holidays:
            working_days += 1
    return working_days


def calculate_task_end_date(start_date: date, base_duration: int, worker_productivity: float, holidays: List[date]) -> date:
    """
    Вычисляет дату окончания задачи с учетом:
    - базовой длительности задачи
    - продуктивности работника
    - выходных и праздничных дней
    
    Args:
        start_date: дата начала задачи
        base_duration: базовая длительность задачи в рабочих днях
        worker_productivity: продуктивность работника (>0)
        holidays: список праздничных дней
    
    Returns:
        date: дата окончания задачи
    """
    actual_duration = ceil(base_duration / worker_productivity)

    end_date = start_date
    working_days_count = 1 # начинаем с единицы, потому что дата начала уже учтена
    while working_days_count < actual_duration:
        end_date += timedelta(days=1)
        if not is_weekend(end_date) and end_date not in holidays:
            working_days_count += 1
            
    return end_date


def load_json(file_name: str) -> Any:
    """
       Загружает данные из JSON-файлов в папке data и возвращает их
    """
    data_path = Path("data") / file_name
    if data_path.exists():
        with open(data_path, "r", encoding="utf-8") as file:
            return json.load(file)


def calculate_order_delay(order: Order, work_plan_dict: Dict[str, AssignedTask]) -> Optional[int]:
    """
    Вычисляет количество дней просрочки заказа.
    Возвращает:
    - Количество дней просрочки (0, если заказ не просрочен).
    - None, если заказ не завершён (отсутствуют задачи в плане работ).
    """
    # Проверяем, что все задачи заказа присутствуют в плане работ
    for task in order.tasks:
        if task.id not in work_plan_dict:
            return None  # Заказ не завершён, так как не все задачи присутствуют в плане

    # Находим максимальную дату окончания среди всех задач заказа
    completion_date = max(
        work_plan_dict[task.id].end
        for task in order.tasks
    )

    # Сравниваем дату завершения с deadline
    delay_days = (completion_date - order.deadline).days

    # Возвращаем количество дней просрочки (но не меньше 0)
    return max(delay_days, 0)

def calculate_order_cost(order: Order, plan: Dict[str, AssignedTask]) -> tuple[float, float, int, bool]:
    """
    Вычисляет стоимость заказа, включая доход, штрафы и задержки.
    
    Args:
        order: заказ для расчета
        plan: план работ
    
    Returns:
        tuple[float, float, int, bool]: (доход, штраф, задержка в днях, статус выполнения)
    """
    delay_days = calculate_order_delay(order, plan)
    if delay_days is None:
        return 0, 0, 0, False
        
    # штраф за просрочку (может быть ноль)
    penalty = order.penaltyByDay * delay_days
    is_completed = penalty < order.earning
    
    return order.earning, penalty, delay_days, is_completed
