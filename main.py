from typing import Dict, List
from pydantic import BaseModel, TypeAdapter
from models import InputData, Orders, WorkPlan, TaskDetails
from utils import load_json
from validators import validate_task_duration, validate_task_worker_compatibility, validate_task_overlap, \
    validate_dependencies, calculate_order_delay


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


class CheckResult(BaseModel):
    success: bool
    total_earning: float
    total_penalty: float
    orders_completed: int
    errors: List[str]
    warnings: List[str]

    def __str__(self):
        w = "\n\t\t ".join(self.warnings)
        e = "\n\t\t ".join(self.errors)
        return (
            f"  Проверка пройдена: {self.success}\n"
            f"  Общий доход: {self.total_earning}\n"
            f"  Общий штраф (уже учтён в доходе): {self.total_penalty}\n"
            f"  Заказов завершено: {self.orders_completed}\n"
            f"  Предупреждения:\n\t\t {w}\n"
            f"  Ошибки:\n\t\t {e}\n"
        )


def check(orders: Orders, work_plan: WorkPlan, input_data: InputData) -> CheckResult:
    result = CheckResult(
        success=False,
        total_earning=0,
        total_penalty=0,
        orders_completed=0,
        errors=[],
        warnings=[]
    )

    plan = aggregate_work_plan(orders, work_plan, input_data)
    for task_id, task in plan.items():
        # критические проверки
        validate_task_worker_compatibility(task, result.errors)
        validate_task_overlap(task, plan, result.errors)
        validate_dependencies(task, plan, result.errors)

        # проверка длительности
        validate_task_duration(task, input_data, result.warnings)

    # считаем доход
    for order in orders.root:
        delay_days = calculate_order_delay(order, plan)
        if not delay_days is None:
            # штраф за просрочку (может быть ноль)
            penalty = order.penaltyByDay * delay_days
            if penalty < order.earning:
                # заказ считаем выполненным, если штраф меньше чем доход
                result.orders_completed += 1
                result.total_penalty += penalty
                result.total_earning += order.earning - penalty

    # проверка успешна, если нет критических ошибок
    result.success = len(result.errors) == 0
    return result


if __name__ == "__main__":
    print("Начинаем проверку")

    input_data = TypeAdapter(InputData).validate_python(load_json("input_data.json"))
    orders = TypeAdapter(Orders).validate_python(load_json("orders.json"))
    work_plan = TypeAdapter(WorkPlan).validate_python(load_json("work_plan.json"))

    print(f"Всего заказов: {len(orders.root)}")
    result = check(orders, work_plan, input_data)
    print(result)


