from typing import Dict, Optional
from models import Order, TaskDetails
from models.work_plan import AssignedTask




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
