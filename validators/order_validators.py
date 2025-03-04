from typing import Dict, Optional
from models import Order, TaskDetails


def calculate_order_delay(order: Order, all_task_details: Dict[str, TaskDetails]) -> Optional[int]:
    """
    Вычисляет количество дней просрочки заказа.
    Возвращает:
    - Количество дней просрочки (0, если заказ не просрочен).
    - None, если заказ не завершён (отсутствуют задачи в плане работ).
    """
    # Проверяем, что все задачи заказа присутствуют в плане работ
    for task in order.tasks:
        if task.id not in all_task_details:
            return None  # Заказ не завершён, так как не все задачи присутствуют в плане

    # Находим максимальную дату окончания среди всех задач заказа
    completion_date = max(
        all_task_details[task.id].assigned_task.end
        for task in order.tasks
    )

    # Сравниваем дату завершения с deadline
    delay_days = (completion_date - order.deadline).days

    # Возвращаем количество дней просрочки (но не меньше 0)
    return max(delay_days, 0)


def validate_dependencies(current_task: TaskDetails, all_task_details: Dict[str, TaskDetails], errors: list):
    # Проходим по всем зависимым задачам
    for dependent_task_id in current_task.task.dependsOn:
        if dependent_task_id in all_task_details:
            dependent_task = all_task_details[dependent_task_id].assigned_task

            # Проверяем, завершена ли зависимая задача к началу текущей задачи
            if dependent_task.end >= current_task.assigned_task.start:
                # Формируем сообщение об ошибке
                error_message = (
                    f"Задача {current_task.task.id} зависит от задачи {dependent_task_id}, "
                    f"которая завершается {dependent_task.end}, "
                    f"но текущая задача начинается {current_task.assigned_task.start}"
                )
                errors.append(error_message)  # Добавляем ошибку в глобальный список
        else:
            # Если зависимая задача не найдена в списке задач
            error_message = (
                f"Задача {current_task.task.id} зависит от задачи {dependent_task_id}, "
                f"которая отсутствует в списке задач"
            )
            errors.append(error_message)  # Добавляем ошибку в глобальный список
