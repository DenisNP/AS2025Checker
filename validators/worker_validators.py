from models import TaskDetails


def validate_task_worker_compatibility(task_details: TaskDetails, errors: list):
    # Проверяем, есть ли тип работ задачи в списке типов работ работника
    if task_details.task.workTypeId not in task_details.worker.workTypeIds:
        # Формируем сообщение об ошибке
        error_message = (
            f"Задача {task_details.task.id} с типом работ {task_details.task.workTypeId} "
            f"назначена работнику {task_details.worker.name} ({task_details.worker.id}), "
            f"у которого нет такого типа работ"
        )
        errors.append(error_message)  # Добавляем ошибку в глобальный список
