from typing import List
from pydantic import BaseModel
from models import WorkPlan, Orders, InputData
from utils import aggregate_work_plan
from validators import validate_task_duration, validate_task_worker_compatibility, validate_task_overlap, \
    validate_dependencies, calculate_order_delay


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
