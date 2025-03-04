from typing import Dict
from models import TaskDetails, InputData
from math import ceil
from utils import calculate_working_days

def validate_task_overlap(task_details: TaskDetails, all_task_details: Dict[str, TaskDetails], errors: list):
    # Получаем данные текущей задачи
    current_task = task_details.assigned_task
    current_worker_id = current_task.workerId
    current_start = current_task.start
    current_end = current_task.end

    # Проходим по всем задачам в словаре
    for task_id, details in all_task_details.items():
        if task_id == current_task.taskId:
            continue  # Пропускаем текущую задачу

        # Проверяем, назначена ли задача на того же работника
        if details.assigned_task.workerId == current_worker_id:
            other_start = details.assigned_task.start
            other_end = details.assigned_task.end

            # Проверяем пересечение дат
            if not (current_end < other_start or current_start > other_end):
                # Формируем сообщение об ошибке
                error_message = (
                    f"Задача {current_task.taskId} (с {current_start} по {current_end}) "
                    f"пересекается с задачей {details.assigned_task.taskId} "
                    f"(с {other_start} по {other_end}) "
                    f"у работника {task_details.worker.name} ({task_details.worker.id})"
                )
                errors.append(error_message)  # Добавляем ошибку в глобальный список

def validate_task_duration(task_details: TaskDetails, input_data: InputData, warnings: list):
    """Проверяет длительность задачи или фиксирует простой."""
    start_date = task_details.assigned_task.start
    end_date = task_details.assigned_task.end

    # Вычисляем фактическую длительность в рабочих днях (с учетом праздников)
    actual_duration = calculate_working_days(start_date, end_date, input_data.holidays)

    if task_details.task is None:
        # Если задача отсутствует, фиксируем простой
        warnings.append(
            f"На работника {task_details.worker.name} оформлен простой "
            f"с {start_date} по {end_date} в течение {actual_duration} раб.дн."
        )
    else:
        # Если задача есть, проверяем длительность
        base_duration = task_details.task.baseDuration
        worker_productivity = task_details.worker.productivity
        calculated_duration = ceil(base_duration / worker_productivity)

        if calculated_duration != actual_duration:
            warnings.append(
                f"Задача {task_details.task.id} имеет рассчитанную длительность {calculated_duration} раб.дн., "
                f"но фактическая длительность составляет {actual_duration} раб.дн. "
                f"(с {start_date} по {end_date})"
            )
