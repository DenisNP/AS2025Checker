from datetime import date, timedelta
from typing import List
from models import Orders, InputData, WorkPlan
from models.orders import Order, Task
from models.work_plan import AssignedTask
from utils import calculate_order_cost, calculate_order_duration, calculate_placed_order_duration
from models.input_data import Worker
from date_utils import closest_workday, minimum_allowed_date_by_dependencies, calculate_task_end_date
from checker import check

class AdvancedOptimizer:
    def __init__(self, input_data: InputData, orders: Orders):
        self.input_data = input_data
        self.orders = self._filter_orders(orders)
        print(f"Оставлено заказов: {len(self.orders.root)}")

        for order in self.orders.root:
            order.tasks.sort(key=lambda task: len(task.dependsOn))

        # подготовим оценку сложности работ
        self._construct_work_types_complexity()

        # подготовим оценку ценности работников
        self._construct_workers_value()

    def optimize(self, earnings_coefficient: float, availability_coefficient: float) -> WorkPlan:
        work_plan_dict: dict[str, AssignedTask] = {}
        all_tasks: List[Task] = []
        order_by_task_id: dict[str, Order] = {}
        tasks_by_id: dict[str, Task] = {}

        for order in self.orders.root:
            for task in order.tasks:
                all_tasks.append(task)
                order_by_task_id[task.id] = order
                tasks_by_id[task.id] = task

        # сортируем задачи по убыванию ценности
        all_tasks.sort(key=lambda x: self._get_task_score(x, order_by_task_id[x.id], earnings_coefficient), reverse=True)

        # разбираем задачи до тех пор, пока не поставим все
        while len(all_tasks) > 0:
            task = all_tasks.pop(0)

            # проверяем, все ли задачи, от которых зависит эта, уже поставлены, и ищем допустимую дату
            min_date = minimum_allowed_date_by_dependencies(task, work_plan_dict, self.input_data.currentDate)

            if min_date is None:
                continue

            min_date = closest_workday(min_date, self.input_data.holidays)

            # получаем оценки работников для этой задачи
            workers_scores = self._get_workers_scores_for_task(task, work_plan_dict, availability_coefficient, min_date)
            
            # получаем идентификатор работника с максимальным баллом
            worker_id = max(workers_scores, key=workers_scores.get)
            worker = next(w for w in self.input_data.workers if w.id == worker_id)

            # получаем дату, когда этот работник может выполнить задачу
            start_date = self._get_worker_date_availability(worker, task, min_date, work_plan_dict)
            # считаем дату конца
            end_date = calculate_task_end_date(start_date, task.baseDuration, worker.productivity, self.input_data.holidays)
            # добавляем задачу в план
            work_plan_dict[task.id] = AssignedTask(taskId=task.id, workerId=worker_id, start=start_date, end=end_date)

            # проверяем, завершён ли заказ
            order = order_by_task_id[task.id]
            if all(t.id in work_plan_dict for t in order.tasks):
                #wp = WorkPlan(work_plan_dict.values())
                #cr = check(self.orders, wp, self.input_data)
                #print(cr.total_earning)

                order_earning, order_penalty, order_delay, order_is_completed = calculate_order_cost(order, work_plan_dict)
                total_earning = order_earning - order_penalty
                total_duration = calculate_placed_order_duration(order, work_plan_dict)
                total_company_cost = self.input_data.companyDayCost * total_duration
                order_is_profitable = total_earning > total_company_cost

                if not order_is_completed or not order_is_profitable:
                    min_deleted_date = date.max
                    # если заказ не завершён или не прибыльный, удаляем все его задачи из плана
                    for task in order.tasks:
                        # удаляем задачу из плана
                        min_deleted_date = min(min_deleted_date, work_plan_dict[task.id].start)
                        del work_plan_dict[task.id]

                    # убираем из плана все более поздние задачи и возвращаем в общий список
                    later_tasks: List[AssignedTask] = []
                    for task in work_plan_dict.values():
                        if task.start > min_deleted_date:
                            later_tasks.append(task)

                    for task in later_tasks:
                        all_tasks.append(tasks_by_id[task.taskId])
                        del work_plan_dict[task.taskId]

                    all_tasks.sort(key=lambda x: self._get_task_score(x, order_by_task_id[x.id], earnings_coefficient), reverse=True)

        sorted_tasks = sorted(work_plan_dict.values(), key=lambda x: x.start)
        return WorkPlan(sorted_tasks)

    def _get_workers_scores_for_task(self, task: Task, work_plan_dict: dict[str, AssignedTask], availability_coefficient: float, min_date: date) -> dict[str, float]:
        scores = {}
        av_scores = self._worker_availability_scores_for_task(task, work_plan_dict, min_date)
        for worker in self.input_data.workers:
            if task.workTypeId in worker.workTypeIds:
                av_score = av_scores[worker.id]
                value_score = self.workers_value[worker.id]
                scores[worker.id] = availability_coefficient * av_score + (1 - availability_coefficient) * (1.0 - value_score)
            else:
                scores[worker.id] = float('-inf')
        
        return scores

    def _worker_availability_scores_for_task(self, task: Task, work_plan_dict: dict[str, AssignedTask], min_date: date) -> dict[str, float]:
        scores = {}
        for worker in self.input_data.workers:
            date = self._get_worker_date_availability(worker, task, min_date, work_plan_dict)
            scores[worker.id] = date

        max_date = max(scores.values())
        min_date = min(scores.values())
        diff = (max_date - min_date).days + 1

        # нормализуем значения
        return {k: 1.0 - ((v - min_date).days + 1) / diff for k, v in scores.items()}

    def _get_worker_date_availability(self, worker: Worker, task: Task, min_date: date, work_plan_dict: dict[str, AssignedTask]) -> date:
        # извлекаем все задачи, которые назначены на этого работника
        worker_tasks = [t for t in work_plan_dict.values() if t.workerId == worker.id]
        worker_tasks.sort(key=lambda x: x.start)

        # идём по задачам и ищем ту, после которой можно поставить текущую
        assumed_task_start = min_date
        assumed_task_end = calculate_task_end_date(assumed_task_start, task.baseDuration, worker.productivity, self.input_data.holidays)

        # если нет задач или влезает до первой, ставим в min_date
        if len(worker_tasks) == 0 or worker_tasks[0].start > assumed_task_end:
            return assumed_task_start
        
        # если одна задача, смотрим, влезет ли до неё или после
        if len(worker_tasks) == 1:
            return closest_workday(max(min_date, worker_tasks[0].end + timedelta(days=1)), self.input_data.holidays)

        # если несколько задач, идём по всем и ищем ту, после которой можно поставить текущую
        for i in range(len(worker_tasks) - 1):
            assumed_task_start = closest_workday(max(min_date, worker_tasks[i].end + timedelta(days=1)), self.input_data.holidays)
            assumed_task_end = calculate_task_end_date(assumed_task_start, task.baseDuration, worker.productivity, self.input_data.holidays)

            if assumed_task_end < worker_tasks[i + 1].start:
                return assumed_task_start

        # если ничего не подошло, ставим после последней задачи
        return closest_workday(max(min_date, worker_tasks[-1].end + timedelta(days=1)), self.input_data.holidays)

    def _get_task_score(self, task: Task, order: Order, earning_coefficient: float) -> float:
        # для начала поймём нормализованное количество зависимых задач
        order_dependants_by_task_id = {}
        for order_task in order.tasks:
            order_dependants_by_task_id[order_task.id] = len([o for o in order.tasks if order_task.id in o.dependsOn])

        # рассчитаем нормализованную степень влияния задачи на зависимые
        max_dependants = max(order_dependants_by_task_id.values())
        task_influence = 0 if max_dependants == 0 else order_dependants_by_task_id[task.id] / max(order_dependants_by_task_id.values())

        # оценка задачи зависит от ценности заказа и степени влияния задачи на зависимые
        order_earning = self.orders_earning[order.id]
        orders_importance = self.orders_importance[order.id]
        base_score = earning_coefficient * order_earning + (1 - earning_coefficient) * orders_importance
        task_score = 0.95 * base_score + 0.05 * task_influence

        return task_score

    def _normalize_values(self, values: dict) -> dict:
        """
        Нормализует значения в словаре в диапазон [0, 1]
        """
        min_value = min(values.values())
        max_value = max(values.values())
        return {key: (value - min_value) / (max_value - min_value) for key, value in values.items()}

    def _filter_orders(self, orders: Orders) -> Orders:
        _orders = []
        self.orders_earning = {}
        self.orders_importance = {}
        for order in orders.root:
            earning = self._estimated_total_order_earning(order)
            if earning > 0:
                _orders.append(order)
                self.orders_earning[order.id] = earning
                self.orders_importance[order.id] = (order.deadline - self.input_data.currentDate).days
        # нормализуем orders_earning        
        self.orders_earning = self._normalize_values(self.orders_earning)
        self.orders_importance = self._normalize_values(self.orders_importance)
        self.orders_importance = {k: 1.0 - v for k, v in self.orders_importance.items()}

        return Orders(_orders)

    def _construct_workers_value(self):
        self.workers_value = {}
        for worker in self.input_data.workers:
            self.workers_value[worker.id] = self._get_worker_value(worker)

        # нормализуем значения
        self.workers_value = self._normalize_values(self.workers_value)

    def _get_worker_value(self, worker: Worker) -> float:
        # ценность работника - это максимум из ценностей всех его типов работ
        return max(self.work_types_complexity[work_type_id] for work_type_id in worker.workTypeIds)

    def _construct_work_types_complexity(self):
        self.work_types_complexity = {}
        for work_type in self.input_data.workTypes:
            self.work_types_complexity[work_type.id] = self._get_work_type_complexity(work_type.id)

        # нормализуем значения
        self.work_types_complexity = self._normalize_values(self.work_types_complexity)

    def _get_work_type_complexity(self, work_type_id: str) -> float:
        # сначала посчитаем сколько в заказах суммарно дней на этот тип работ
        total_days = 0
        for order in self.orders.root:
            for task in order.tasks:
                if task.workTypeId == work_type_id:
                    total_days += task.baseDuration

        # теперь посчитаем общую продуктивность работников, которые могут делать этот тип задач            
        total_productivity = 0
        for worker in self.input_data.workers:
            if work_type_id in worker.workTypeIds:
                total_productivity += worker.productivity

        return total_days / total_productivity
                    

    def _estimated_total_order_earning(self, order: Order) -> float:
        duration = calculate_order_duration(order, self.input_data)
        total_company_cost = self.input_data.companyDayCost * duration
        return order.earning - total_company_cost