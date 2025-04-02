from datetime import date, timedelta
from models.orders import Task
from models.work_plan import AssignedTask
from models.input_data import InputData, Worker
from math import ceil

def is_weekend(d: date) -> bool:
    """Проверяет, является ли дата выходным (суббота или воскресенье)."""
    return d.weekday() >= 5  # 5 = суббота, 6 = воскресенье

def closest_workday(date: date, holidays: list[date]) -> date:
    """
    Поиск ближайшего рабочего дня
    
    Args:
        date: начальная дата
        holidays: список праздничных дней
        
    Returns:
        date: ближайший рабочий день
    """
    if not is_weekend(date) and date not in holidays:
        return date
    else:
        return closest_workday(date + timedelta(days=1), holidays)

def calculate_working_days(start: date, end: date, holidays: list[date]) -> int:
    """Вычисляет количество рабочих дней между двумя датами (включительно)."""
    delta = end - start
    working_days = 0
    for i in range(delta.days + 1):
        current_date = start + timedelta(days=i)
        if not is_weekend(current_date) and current_date not in holidays:
            working_days += 1
    return working_days

def calculate_task_end_date(start_date: date, base_duration: int, worker_productivity: float, holidays: list[date]) -> date:
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

def minimum_allowed_date_by_dependencies(task: Task, work_plan_dict: dict[str, AssignedTask], current_date: date) -> date | None:
    """
    Определение минимальной допустимой даты с учетом зависимостей
    
    Args:
        task: задача для которой ищем дату
        work_plan_dict: словарь с назначенными задачами
        current_date: текущая дата
        
    Returns:
        date | None: минимальная допустимая дата или None если есть незавершенные зависимости
    """
    min_date = current_date
    # ищем все задачи, от которых зависит данная
    for dep_id in task.dependsOn:
        # если влияющая задача уже назначена, то берём дату её окончания + 1 день
        if dep_id in work_plan_dict:
            min_date = max(min_date, work_plan_dict[dep_id].end + timedelta(days=1))
        else:
            # если влияющая задача ещё не назначена, то нельзя назначить зависимую
            return None

    return min_date 