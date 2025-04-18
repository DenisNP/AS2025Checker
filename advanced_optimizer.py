from datetime import date, timedelta
from typing import List
import concurrent.futures
import os
import time

from checker import only_calculate_earning
from models import Orders, InputData, WorkPlan
from models.orders import Order, Task
from models.work_plan import AssignedTask
from utils import calculate_order_cost, calculate_order_duration, calculate_placed_order_duration
from models.input_data import Worker
from date_utils import closest_workday, minimum_allowed_date_by_dependencies, calculate_task_end_date

class AdvancedOptimizer:
    def __init__(self, input_data: InputData, orders: Orders):
        self.input_data = input_data
        self.orders = self._filter_orders(orders)
        print(f"Оставлено заказов: {len(self.orders.root)}")

        # подготовим оценку сложности работ
        self._construct_work_types_complexity()

        # подготовим оценку ценности работников
        self._construct_workers_value()

    def optimize(self, orders_window: int, workers_step: float, earning_coefficient: float = 1.0) -> WorkPlan:
        # Засекаем время начала работы
        start_time = time.time()

        work_plan_dict: dict[str, AssignedTask] = {}
        order_by_task_id: dict[str, Order] = {}
        tasks_by_id: dict[str, Task] = {}
        orders = []
        global_best_earning = float('-inf')

        for order in self.orders.root:
            orders.append(order)
            for task in order.tasks:
                order_by_task_id[task.id] = order
                tasks_by_id[task.id] = task

        # сортируем заказы по прибыли
        orders = sorted(orders, key=lambda o: self._get_order_score(o, earning_coefficient), reverse=True)

        # разбираем задачи до тех пор, пока не поставим все
        while len(orders) > 0:
            orders_selected = []
            if len(orders) > orders_window:
                orders_selected = orders[:orders_window].copy()
            else:
                orders_selected = orders.copy()

            best_order = None
            best_earning_for_order = global_best_earning
            best_work_plan = None

            # перебираем окно заказов
            while len(orders_selected) > 0:
                order = orders_selected.pop(0)
                temp_work_plan_for_order = work_plan_dict.copy()

                # ищем лучшее распределение по работникам для этого заказа
                current_best_earning, current_best_work_plan, best_availability_coefficient = self._select_best_workers(order, temp_work_plan_for_order, workers_step)

                # Если текущий результат лучше лучшего найденного ранее, обновляем лучший результат
                if current_best_earning > best_earning_for_order:
                    best_earning_for_order = current_best_earning
                    best_order = order
                    best_work_plan = current_best_work_plan.copy()
                    print(f"Earning: {best_earning_for_order:,.2f}".replace(',', ' '), f"orders left: {len(orders)}, availability coefficient: {best_availability_coefficient:.1f}")

            if best_order is None:
                break
            else:
                orders.remove(best_order)
                work_plan_dict = best_work_plan.copy()
                global_best_earning = best_earning_for_order

        sorted_tasks = sorted(work_plan_dict.values(), key=lambda x: x.start)

        # Вычисляем время работы в секундах
        end_time = time.time()
        execution_time = end_time - start_time
        print(f"Время работы optimize: {execution_time:.2f} секунд")

        return WorkPlan(sorted_tasks)

    def _select_best_workers(self, order: Order, work_plan_dict: dict[str, AssignedTask], workers_step: float) -> (float, dict[str, AssignedTask], float):
        # ищем лучшее распределение по работникам для этого заказа
        best_earning_for_worker = float('-inf')
        best_work_plan_for_worker = None
        best_availability_coefficient = 0

        # Создаем список всех коэффициентов доступности для перебора
        availability_coefficients = [i * workers_step for i in range(int(1/workers_step) + 1)]

        # Функция для обработки одного коэффициента доступности
        def process_coefficient(coefficient):
            # Создаем копию текущего плана работ
            temp_work_plan = work_plan_dict.copy()

            # Пытаемся разместить заказ с текущим коэффициентом
            self._place_order(order, temp_work_plan, coefficient)

            # Проверяем, прибылен ли заказ
            current_earning = only_calculate_earning(self.orders, WorkPlan(temp_work_plan.values()), self.input_data)

            return coefficient, current_earning, temp_work_plan

        # Определяем количество потоков (используем количество ядер процессора)
        max_workers = len(availability_coefficients)

        # Запускаем параллельную обработку
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Запускаем задачи и получаем результаты
            future_to_coefficient = {executor.submit(process_coefficient, coefficient): coefficient
                                    for coefficient in availability_coefficients}

            # Обрабатываем результаты по мере их завершения
            for future in concurrent.futures.as_completed(future_to_coefficient):
                coefficient, current_earning, temp_work_plan = future.result()

                # Если текущий результат лучше, сохраняем его
                if current_earning > best_earning_for_worker:
                    best_earning_for_worker = current_earning
                    best_work_plan_for_worker = temp_work_plan
                    best_availability_coefficient = coefficient

        return best_earning_for_worker, best_work_plan_for_worker, best_availability_coefficient

    def _place_order(self, order: Order, work_plan_dict: dict[str, AssignedTask], availability_coefficient: float):
        tasks_to_place = order.tasks.copy()

        while len(tasks_to_place) > 0:
            task = tasks_to_place.pop(0)

            # проверяем, все ли задачи, от которых зависит эта, уже поставлены, и ищем допустимую дату
            min_date = minimum_allowed_date_by_dependencies(task, work_plan_dict, self.input_data.currentDate)

            if min_date is None:
                tasks_to_place.append(task)
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

    def _get_order_score(self, order: Order, earning_coefficient: float) -> float:
        order_earning = self.orders_earning[order.id]
        orders_importance = self.orders_importance[order.id]
        return earning_coefficient * order_earning + (1 - earning_coefficient) * orders_importance;

    def _get_task_importance(self, task: Task, order: Order) -> float:
        # для начала поймём нормализованное количество зависимых задач
        #order_dependants_by_task_id = {}
        #for order_task in order.tasks:
        #    order_dependants_by_task_id[order_task.id] = len([o for o in order.tasks if order_task.id in o.dependsOn])

        # влияние задачи это число задач, которые от неё зависят, а вторым приоритетом число её собственных зависимостей
        #task_influence = order_dependants_by_task_id[task.id] * 1000 + len(task.dependsOn)

        return len(task.dependsOn)

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
