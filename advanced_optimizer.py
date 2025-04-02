from datetime import date, timedelta
from models import Orders, InputData, WorkPlan
from models.orders import Order, Task
from models.work_plan import AssignedTask
from utils import calculate_order_duration
from models.input_data import Worker
from date_utils import closest_workday, minimum_allowed_date_by_dependencies, calculate_task_end_date

class AdvancedOptimizer:
    def __init__(self, input_data: InputData, orders: Orders):
        self.input_data = input_data
        self.orders = orders

    def optimize(self) -> WorkPlan:
        """
        Основной метод оптимизации, который будет реализован позже
        """
        pass

    def _sort_orders(self) -> list[Order]:
        """
        Сортировка заказов по приоритету
        """
        pass

    def _task_complexity(self, task: Task) -> float:
        """
        Вычисление сложности задачи
        """
        pass

    def _order_score(self, order: Order) -> float:
        """
        Вычисление оценки заказа
        """
        pass

    def _minimum_allowed_date_by_dependencies(self, task: Task, work_plan_dict: dict[str, AssignedTask]) -> date | None:
        """
        Определение минимальной допустимой даты с учетом зависимостей
        """
        pass

    def _minimum_allowed_date_by_worker_availability(self, task: Task, work_plan_dict: dict[str, AssignedTask], desired_start: date) -> (date, Worker):
        """
        Определение минимальной допустимой даты с учетом доступности работников
        """
        pass

    def _closest_workday(self, date: date) -> date:
        """
        Поиск ближайшего рабочего дня
        """
        pass 