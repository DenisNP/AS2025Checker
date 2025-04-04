import json
from datetime import date, timedelta
from pathlib import Path
from typing import List, Any, Dict, Optional
from math import ceil
from models import Orders, WorkPlan, InputData, TaskDetails
from models.orders import Order, Task
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


def calculate_order_duration(order: Order, input_data: InputData | None = None) -> int:
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
        task_duration = task.baseDuration
        if input_data is not None:
            task_duration = ceil(task.baseDuration / top_productivity_by_work_type(task, input_data))
        
        # Если нет зависимостей, возвращаем базовую длительность
        if not task.dependsOn:
            max_durations[task_id] = task_duration
            return task_duration
            
        # Иначе находим максимальный путь через зависимости
        max_dep_duration = max(get_max_path_duration(dep_id) for dep_id in task.dependsOn)
        total_duration = max_dep_duration + task_duration
        
        max_durations[task_id] = total_duration
        return total_duration
    
    # Находим максимальную длительность для всех конечных задач
    return max(get_max_path_duration(task.id) for task in order.tasks)


def top_productivity_by_work_type(task: Task, input_data: InputData) -> float:
    """
    Возвращает максимальную продуктивность для заданного типа работы.
    """
    return max(worker.productivity for worker in input_data.workers if task.workTypeId in worker.workTypeIds)


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

def calculate_placed_order_duration(order: Order, plan: Dict[str, AssignedTask]) -> int:
    """
    Вычисляет длительность заказа как разницу между датой завершения и датой начала
    """
    start_date = min(plan[task.id].start for task in order.tasks if task.id in plan)
    end_date = max(plan[task.id].end for task in order.tasks if task.id in plan)
    return (end_date - start_date).days

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

def save_to_file(_work_plan: WorkPlan, file_name: str):
    with open(f"data/{file_name}", "w") as f:
        f.write(_work_plan.model_dump_json(indent=2))
