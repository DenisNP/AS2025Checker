from typing import List
from pydantic import BaseModel
from models import WorkPlan, Orders, InputData
from utils import aggregate_work_plan
from validators import validate_task_duration, validate_task_worker_compatibility, validate_task_overlap, \
    validate_dependencies, calculate_order_delay


class CheckResult(BaseModel):
    success: bool
    total_earning: float
    raw_earning: float
    total_penalty: float
    total_days: int
    total_cost: float
    orders_completed: int
    errors: List[str]
    warnings: List[str]

    def __str__(self):
        w = "\n\t\t ".join(self.warnings)
        e = "\n\t\t ".join(self.errors)
        return (
            f"  Проверка пройдена: {self.success}\n"
            f"  Общая прибыль: {'{:,}'.format(self.total_earning).replace(',', ' ')}\n"
            f"  Общая выручка: {'{:,}'.format(self.raw_earning).replace(',', ' ')}\n" 
            f"  Общий штраф: {'{:,}'.format(self.total_penalty).replace(',', ' ')}\n"
            f"  Общие расходы: {'{:,}'.format(self.total_cost).replace(',', ' ')}\n"
            f"  Дней работы фирмы: {'{:,}'.format(self.total_days).replace(',', ' ')}\n"
            f"  Заказов завершено: {'{:,}'.format(self.orders_completed).replace(',', ' ')}\n"
            f"  Предупреждения:\n\t\t {w}\n"
            f"  Ошибки:\n\t\t {e}\n"
        )


def check(orders: Orders, work_plan: WorkPlan, input_data: InputData) -> CheckResult:
    result = CheckResult(
        success=False,
        total_earning=0,
        raw_earning=0,
        total_penalty=0,
        total_days=0,
        total_cost=0,
        orders_completed=0,
        errors=[],
        warnings=[]
    )

    plan, total_days = aggregate_work_plan(orders, work_plan, input_data)
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
                result.raw_earning += order.earning

    # общие показатели
    result.total_days = total_days
    result.total_cost = total_days * input_data.companyDayCost
    result.total_earning = result.raw_earning - result.total_penalty - result.total_cost

    # проверка успешна, если нет критических ошибок
    result.success = len(result.errors) == 0
    return result
