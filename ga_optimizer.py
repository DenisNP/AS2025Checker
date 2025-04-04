from datetime import date, timedelta
import math
import random
from typing import List
import time
from models import Orders, InputData, WorkPlan
from models.orders import Order, Task
from models.work_plan import AssignedTask
from date_utils import calculate_working_days, is_weekend, calculate_task_end_date
from utils import calculate_order_cost, calculate_order_duration, calculate_placed_order_duration
from models.input_data import Worker
import pygad
from checker import only_calculate_earning
import multiprocessing as mp
from functools import partial

class GaOptimizer:
    def __init__(self, input_data: InputData, orders: Orders):
        self.input_data = input_data
        self.additional_orders: List[Order] = []
        # создаём копию списка заказов и фильтруем её
        self.orders = Orders([o for o in orders.root if self._estimated_total_order_earning(o) > 0])
        print(f"Оставлено заказов: {len(self.orders.root)}")

        # Сортируем задачи внутри каждого заказа по количеству зависимостей
        for order in self.orders.root:
            order.tasks.sort(key=lambda task: len(task.dependsOn))
            
        # Сортируем работников по убыванию продуктивности
        self.input_data.workers.sort(key=lambda worker: worker.productivity, reverse=True)

    def alt_optimize(self) -> WorkPlan:
        priorities = [round(self._estimated_total_order_earning(o)) for o in self.orders.root]
        plan = self._create_plan(priorities)

        # удалим из orders заказы, которые не входят в план
        order_ids_by_task_id = {}
        for order in self.orders.root:      
            for task in order.tasks:
                order_ids_by_task_id[task.id] = order.id

        # удалим из orders заказы, которые не входят в план
        orders_to_keep: List[str] = []
        for task in plan.root:
            order_id = order_ids_by_task_id[task.taskId]
            orders_to_keep.append(order_id)

        self.additional_orders = sorted([o for o in self.orders.root if o.id not in orders_to_keep], key=lambda x: self._estimated_total_order_earning(x), reverse=True)
        self.orders = Orders([o for o in self.orders.root if o.id in orders_to_keep])

        # выведем доход каждого дополнительного заказа
        #for order in self.additional_orders:
            #print(f"Доход дополнительного заказа {order.id}: {self._estimated_total_order_earning(order)}")

        # и запустим оптимизацию ГА
        print(f"Оставлено после первого шага: {len(self.orders.root)}")
        plan = self.optimize()
        return plan

    def optimize(self) -> WorkPlan:
        start_time = time.time()
        
        ga_instance = pygad.GA(
            num_generations=15,
            num_parents_mating=6,
            fitness_func=self._fitness_function,
            sol_per_pop=20,
            num_genes=len(self.orders.root),
            crossover_type="scattered",
            init_range_low=1,
            init_range_high=len(self.orders.root),
            gene_type=int,
            mutation_type="random",
            mutation_probability=0.2,
            on_generation=self._on_generation,
            parallel_processing=["process", 10]
        )
        ga_instance.run()
        solution, solution_fitness, solution_idx = ga_instance.best_solution()
        ga_instance.plot_fitness()
        result = self._create_plan(solution)
        
        end_time = time.time()
        execution_time = end_time - start_time
        print(f"\nВремя выполнения: {execution_time:.2f} секунд")
        
        return result

    def _on_generation(self, ga_instance):
        print(f"Generation = {ga_instance.generations_completed}")
        print(f"Fitness    = {ga_instance.best_solution(pop_fitness=ga_instance.last_generation_fitness)[1]}")
        #print(f"Solution   = {ga_instance.best_solution(pop_fitness=ga_instance.last_generation_fitness)[0][:10]}")

    def _fitness_function(self, ga, solution: List[int], index: int) -> float:
        plan = self._create_plan(solution)
        result = only_calculate_earning(self.orders, plan, self.input_data)
        #print(f"    {result}")
        return result

    def _create_plan(self, priorities: List[int]) -> WorkPlan:
        work_plan_dict = {}
        priority_by_task_id = {}
        task_by_id = {}
        excluded_task_ids = []

        # запоминаем приоритеты для каждой задачи
        next_index = 0
        for order in self.orders.root:
            for task in order.tasks:
                priority_by_task_id[task.id] = priorities[next_index]
                task_by_id[task.id] = task

            next_index += 1

        priority_sorted_task_ids = sorted(priority_by_task_id, key=lambda x: priority_by_task_id[x], reverse=True)

        while len(work_plan_dict) + len(excluded_task_ids) < len(task_by_id):
            next_task = None
            for task_id in priority_sorted_task_ids:
                task = task_by_id[task_id]
                if task_id not in work_plan_dict and task_id not in excluded_task_ids:
                    # Проверяем все зависимости задачи
                    dependencies_satisfied = all(dep_id in work_plan_dict for dep_id in task.dependsOn)
                    
                    if dependencies_satisfied:
                        next_task = task
                        break

            if next_task is not None:
                min_date = self._minimum_allowed_date_by_dependencies(next_task, work_plan_dict)
                
                worker, min_date = self._select_worker(next_task, min_date, work_plan_dict)
                #min_date = self._closest_workday(min_date)
                end_date = calculate_task_end_date(min_date, next_task.baseDuration, worker.productivity, self.input_data.holidays)

                # назначаем задачу
                work_plan_dict[next_task.id] = AssignedTask(taskId=next_task.id, workerId=worker.id, start=min_date, end=end_date)

                # проверим, завершён ли текущий заказ
                order = next(o for o in self.orders.root if next_task in o.tasks)
                if all(t.id in work_plan_dict for t in order.tasks):
                    order_earning, order_penalty, order_delay, order_is_completed = calculate_order_cost(order, work_plan_dict)
                    total_earning = order_earning - order_penalty
                    total_duration = calculate_placed_order_duration(order, work_plan_dict)
                    total_company_cost = self.input_data.companyDayCost * total_duration
                    order_is_profitable = total_earning > total_company_cost

                    if not order_is_completed or not order_is_profitable:
                        # собираем затронутых сотрудников
                        worker_ids_affected = []
                        # заказ завершён без прибыли, исключим все его задачи из плана
                        for task in order.tasks:
                            worker_ids_affected.append(work_plan_dict[task.id].workerId)
                            work_plan_dict.pop(task.id)
                            excluded_task_ids.append(task.id)

                        # перемещаем влево все задачи задействованных сотрудников    
                        for worker_id in worker_ids_affected:
                            worker_tasks = sorted([t for t in work_plan_dict.values() if t.workerId == worker_id], key=lambda x: x.start)
                            for worker_task in worker_tasks:
                                self._try_move_task_left(task_by_id[worker_task.taskId], work_plan_dict)

        # сортируем задачи по дате начала
        sorted_tasks = sorted(work_plan_dict.values(), key=lambda x: x.start)
        return WorkPlan(sorted_tasks)
    
    def _run_simulated_annealing(self, initial_temperature: float, cooling_rate: float) -> tuple[WorkPlan, float]:
        priorities = [round(self._estimated_total_order_earning(o)) for o in self.orders.root]
        plan = self._create_plan(priorities)
        final_plan = self._fine_tune_simulated_annealing(plan, priorities, initial_temperature, cooling_rate)
        final_earning = only_calculate_earning(self.orders, final_plan, self.input_data)
        return final_plan, final_earning

    def _try_swap_orders(self, order1_idx: int, order2_idx: int, priorities: List[int], plan: WorkPlan) -> tuple[bool, WorkPlan, float]:
        # сохраняем текущие приоритеты
        old_priority1 = priorities[order1_idx]
        old_priority2 = priorities[order2_idx]

        # меняем приоритеты местами
        priorities[order1_idx] = old_priority2
        priorities[order2_idx] = old_priority1

        # создаём новый план с обновленными приоритетами
        new_plan = self._create_plan(priorities)

        # вычисляем разницу в прибыли
        current_earning = only_calculate_earning(self.orders, plan, self.input_data)
        new_earning = only_calculate_earning(self.orders, new_plan, self.input_data)

        # вычисляем относительную разницу в прибыли и масштабируем её
        if current_earning != 0:
            relative_diff = (new_earning - current_earning) / current_earning
            scaled_diff = relative_diff * 1000
        else:
            scaled_diff = 1000 if new_earning > 0 else 0

        # если не приняли новый план, возвращаем старые приоритеты
        if scaled_diff <= 0:
            priorities[order1_idx] = old_priority1
            priorities[order2_idx] = old_priority2
            return False, plan, current_earning

        return True, new_plan, new_earning

    def _parallel_iteration(self, temperature: float, priorities: List[int], plan: WorkPlan) -> tuple[WorkPlan, float]:
        num_processes = 10
        pool = mp.Pool(processes=num_processes)

        # Генерируем пары заказов для каждого процесса
        order_pairs = []
        for _ in range(num_processes):
            order1_idx = random.randint(0, len(self.orders.root) - 1)
            order2_idx = random.randint(0, len(self.orders.root) - 1)
            while order2_idx == order1_idx:
                order2_idx = random.randint(0, len(self.orders.root) - 1)
            order_pairs.append((order1_idx, order2_idx))

        # Запускаем параллельные процессы
        results = pool.starmap(self._try_swap_orders, 
                             [(order1_idx, order2_idx, priorities, plan) 
                              for order1_idx, order2_idx in order_pairs])
        
        # Закрываем пул
        pool.close()
        pool.join()

        # Выбираем лучший результат
        best_result = max(results, key=lambda x: x[2])
        return best_result[1], best_result[2]

    def optimize_with_simulated_annealing(self) -> WorkPlan:
        start_time = time.time()
        
        priorities = [round(self._estimated_total_order_earning(o)) for o in self.orders.root]
        plan = self._create_plan(priorities)
        
        # задаём начальные параметры для имитации отжига
        temperature = 1000
        cooling_rate = 0.9
        max_iterations = 1000

        # список для хранения последних результатов
        last_results = []
        last_results_size = 10

        # выполняем имитацию отжига
        for iteration in range(max_iterations):
            # параллельно проверяем несколько пар заказов
            new_plan, new_earning = self._parallel_iteration(temperature, priorities, plan)
            
            # вычисляем вероятность перехода к новому плану
            current_earning = only_calculate_earning(self.orders, plan, self.input_data)
            if current_earning != 0:
                relative_diff = (new_earning - current_earning) / current_earning
                scaled_diff = relative_diff * 1000
            else:
                scaled_diff = 1000 if new_earning > 0 else 0

            probability = math.exp(-abs(scaled_diff) / (temperature * 0.1))
            print(f"Итерация {iteration}, температура: {temperature:.2f}, вероятность: {probability:.2f}, разница: {scaled_diff:.2f}")

            # переходим к новому плану, если он лучше
            if scaled_diff > 0 or random.random() < probability:
                plan = new_plan
                print(f"    Приняли изменение. Новая прибыль: {new_earning:.2f}")
            else:
                print(f"    Отклонили изменение")

            # добавляем текущий результат в список последних результатов
            last_results.append(new_earning)
            if len(last_results) > last_results_size:
                last_results.pop(0)

            # проверяем, все ли последние результаты одинаковые
            if len(last_results) == last_results_size and all(x == last_results[0] for x in last_results):
                print(f"Прерываем оптимизацию: {last_results_size} последних результатов одинаковые ({last_results[0]:.2f})")
                break

            # охлаждаем температуру
            temperature *= cooling_rate

        end_time = time.time()
        execution_time = end_time - start_time
        print(f"\nВремя выполнения: {execution_time:.2f} секунд")
        
        return plan

    def _fine_tune_simulated_annealing(self, plan: WorkPlan, priorities: List[int], 
                                     initial_temperature: float, cooling_rate: float) -> WorkPlan:
        # задаём начальные параметры для имитации отжига
        temperature = initial_temperature
        max_iterations = 1000

        # выполняем имитацию отжига
        for _ in range(max_iterations):
            # выбираем два случайных заказа для обмена приоритетами
            order1_idx = random.randint(0, len(self.orders.root) - 1)
            order2_idx = random.randint(0, len(self.orders.root) - 1)
            while order2_idx == order1_idx:
                order2_idx = random.randint(0, len(self.orders.root) - 1)

            # сохраняем текущие приоритеты
            old_priority1 = priorities[order1_idx]
            old_priority2 = priorities[order2_idx]

            # меняем приоритеты местами
            priorities[order1_idx] = old_priority2
            priorities[order2_idx] = old_priority1

            # создаём новый план с обновленными приоритетами
            new_plan = self._create_plan(priorities)

            # вычисляем разницу в прибыли
            current_earning = only_calculate_earning(self.orders, plan, self.input_data)
            new_earning = only_calculate_earning(self.orders, new_plan, self.input_data)

            # вычисляем относительную разницу в прибыли и масштабируем её
            if current_earning != 0:
                relative_diff = (new_earning - current_earning) / current_earning
                scaled_diff = relative_diff * 1000
            else:
                scaled_diff = 1000 if new_earning > 0 else 0

            # вычисляем вероятность перехода к новому плану
            probability = math.exp(-abs(scaled_diff) / (temperature * 0.1))
            print(f"Температура: {temperature:.2f}, вероятность: {probability:.2f}, разница: {scaled_diff:.2f}")

            # переходим к новому плану, если он лучше
            if scaled_diff > 0 or random.random() < probability:
                plan = new_plan
                print(f"    Приняли изменение. Новая прибыль: {new_earning:.2f}")
            else:
                # если не приняли новый план, возвращаем старые приоритеты
                priorities[order1_idx] = old_priority1
                priorities[order2_idx] = old_priority2
                print(f"    Отклонили изменение")

            # охлаждаем температуру
            temperature *= cooling_rate

        return plan
    
    def _try_move_task_left(self, task: Task, work_plan_dict: dict[str, AssignedTask]) -> bool:
        assigned_task = work_plan_dict[task.id]
        min_date = self._minimum_allowed_date_by_dependencies(task, work_plan_dict)
        all_worker_tasks = [t for t in work_plan_dict.values() if t.workerId == assigned_task.workerId and t.end < assigned_task.start]
        if len(all_worker_tasks) > 0:
            # отсортируем по дате начала и возьмём последнюю
            last_task = sorted(all_worker_tasks, key=lambda x: x.start)[-1]
            min_date = max(min_date, last_task.end + timedelta(days=1))

        min_date = self._closest_workday(min_date)
        if min_date < assigned_task.start:
            worker = next(w for w in self.input_data.workers if w.id == assigned_task.workerId)
            new_end_date = calculate_task_end_date(min_date, task.baseDuration, worker.productivity, self.input_data.holidays)
            work_plan_dict[task.id] = AssignedTask(taskId=task.id, workerId=assigned_task.workerId, start=min_date, end=new_end_date)
            return True
        return False

    def _minimum_allowed_date_by_dependencies(self, task: Task, work_plan_dict: dict[str, AssignedTask]) -> date:
        min_date = self.input_data.currentDate
        for dep_id in task.dependsOn:
            min_date = max(min_date, work_plan_dict[dep_id].end + timedelta(days=1))
        return min_date
    
    def _estimated_total_order_earning(self, order: Order, end_date: date | None = None) -> float:
        duration = calculate_order_duration(order, self.input_data)
        days_overdue = 0 if end_date is None else max(0, (end_date - order.deadline).days)
        penalty = order.penaltyByDay * days_overdue
        total_earning = max(0, order.earning - penalty)
        total_company_cost = self.input_data.companyDayCost * duration
        return total_earning - total_company_cost

    def _select_worker(self, task: Task, min_date: date, work_plan_dict: dict[str, AssignedTask]) -> (Worker, date):
        selected_worker = None
        selected_date = date.max

        # перебираем только тех работников, у которых есть нужный тип работ
        for worker in self.input_data.workers:
            if task.workTypeId in worker.workTypeIds:
                tasks = [t for t in work_plan_dict.values() if t.workerId == worker.id]
                sorted_tasks = sorted(tasks, key=lambda x: x.start)

                # перебираем задачи с индексом для сравнения текущей и следующей
                for i in range(len(sorted_tasks) - 1):
                    current_task = sorted_tasks[i]
                    start_date = self._closest_workday(max(min_date, current_task.end + timedelta(days=1)))
                    assumed_end_date = calculate_task_end_date(start_date, task.baseDuration, worker.productivity, self.input_data.holidays)
                    next_task = sorted_tasks[i + 1]

                    if assumed_end_date < next_task.start and start_date < selected_date:
                        selected_worker = worker
                        selected_date = start_date
                        break
                    
                # ничего не выбрано, берём дату конца последнего таска  
                if len(tasks) < 1:
                    assumed_start_date = self._closest_workday(min_date)
                    if assumed_start_date < selected_date:
                        selected_worker = worker
                        selected_date = assumed_start_date
                else:
                    closest_date_available = self._closest_workday(max(sorted_tasks[-1].end + timedelta(days=1), min_date))
                    if closest_date_available < selected_date:  
                        selected_worker = worker
                        selected_date = closest_date_available

        return selected_worker, selected_date

    def _closest_workday(self, date: date) -> date:
        if not is_weekend(date) and date not in self.input_data.holidays:
            return date
        else:
            return self._closest_workday(date + timedelta(days=1))
