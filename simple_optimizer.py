from datetime import date, timedelta
from models import Orders, InputData, WorkPlan
from models.orders import Order, Task
from models.work_plan import AssignedTask
from utils import calculate_order_duration
from models.input_data import Worker
from date_utils import closest_workday, minimum_allowed_date_by_dependencies, calculate_task_end_date

class SimpleOptimizer:
    def __init__(self, input_data: InputData, orders: Orders):
        self.input_data = input_data
        self.orders = orders

    def optimize(self) -> WorkPlan:
        # сортируем заказы по убыванию прибыли на день
        sorted_orders = self._sort_orders()

        # создадим пустой план словарём для быстрого поиска
        work_plan_dict = {}

        for order in sorted_orders:
            # создадим список для ещё не назначенных задач
            tasks = order.tasks.copy()
            total_tasks = len(tasks)
            attempts = 0
            while tasks:
                # если мы уже проверили все задачи 3 раза, а разместить не можем, значит есть циклическая зависимость
                if attempts >= total_tasks * 3:
                    raise Exception(f"Обнаружена циклическая зависимость: {order.id}")

                task = tasks.pop(0)

                # находим минимальную дату, когда можно начать выполнение задачи в зависимости от задач, от которых она зависит
                min_date = minimum_allowed_date_by_dependencies(task, work_plan_dict, self.input_data.currentDate)

                # если такой даты нет, значит, не все влияющие задачи назначены, возвращаем задачу в конец списка
                if min_date is None:
                    tasks.append(task)
                    attempts += 1
                    continue

                # находим минимальную дату, когда можно начать выполнение задачи в зависимости от доступности работника
                min_date, worker = self._minimum_allowed_date_by_worker_availability(task, work_plan_dict, min_date)

                # находим ближайший рабочий день
                min_date = closest_workday(min_date, self.input_data.holidays)

                # рассчитываем дату окончания задачи
                end_date = calculate_task_end_date(min_date, task.baseDuration, worker.productivity, self.input_data.holidays)

                # назначаем задачу
                work_plan_dict[task.id] = AssignedTask(taskId=task.id, workerId=worker.id, start=min_date, end=end_date)
                attempts = 0

        return WorkPlan(list(work_plan_dict.values()))

    def _sort_orders(self) -> list[Order]:
        # фильтруем заказы с положительной оценкой и сортируем по убыванию
        return sorted(
            [order for order in self.orders.root if self._order_score(order) >= 0],
            key=lambda order: self._order_score(order),
            reverse=True
        )

    def _task_complexity(self, task: Task) -> float:
        # Находим всех работников, которые могут выполнить задачу
        capable_workers = [w for w in self.input_data.workers if task.workTypeId in w.workTypeIds]

        # Суммируем их производительность
        total_productivity = sum(w.productivity for w in capable_workers)

        # Чем больше производительность и меньше длительность, тем проще задача
        return total_productivity / task.baseDuration if task.baseDuration > 0 else float('inf')

    def _order_score(self, order: Order) -> float:
        # Вычисляем среднюю сложность задач заказа
        tasks_complexity = [self._task_complexity(task) for task in order.tasks]
        avg_complexity = sum(tasks_complexity) / len(tasks_complexity) if tasks_complexity else 0

        # Нормализуем сложность к диапазону 0.1-1.0 чтобы не слишком сильно влияла на итоговую оценку
        normalized_complexity = 1.0 - (0.9 * (avg_complexity / (avg_complexity + 1.0)))

        # Учитываем оба фактора: доход за день и сложность выполнения
        # normalized_complexity близка к 1 для простых задач и к 0.1 для сложных
        duration = calculate_order_duration(order)
        earning_per_day = order.earning / duration
        if earning_per_day <= self.input_data.companyDayCost:
            return float('-inf')
        return earning_per_day * normalized_complexity

    def _minimum_allowed_date_by_worker_availability(self, task: Task, work_plan_dict: dict[str, AssignedTask], desired_start: date) -> (date, Worker):
        """
        Определение минимальной допустимой даты с учетом доступности работников
        
        Args:
            task: задача для которой ищем дату
            work_plan_dict: словарь с назначенными задачами
            desired_start: желаемая дата начала
            
        Returns:
            tuple[date, Worker]: минимальная допустимая дата и выбранный работник
        """
        min_date = date.max
        selected_worker = None
        # перебираем всех работников с тем же типом работ
        for worker in self.input_data.workers:
            if task.workTypeId in worker.workTypeIds:
                worker_min_date = desired_start

                # ищем все назначенные задачи для этого работника
                for assigned_task in work_plan_dict.values():
                    if assigned_task.workerId == worker.id:
                        # минимальная дата, когда конкретно этот работник может взять новую задачу
                        worker_min_date = max(worker_min_date, assigned_task.end + timedelta(days=1))

                # выбираем минимальную дату из всех работников
                if worker_min_date < min_date:
                    min_date = worker_min_date
                    selected_worker = worker

        return min_date, selected_worker 