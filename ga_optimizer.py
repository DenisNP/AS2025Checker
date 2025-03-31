from datetime import date, timedelta
import math
import random
from typing import Dict, List
import time
from models import Orders, InputData, WorkPlan
from models.orders import Task
from models.work_plan import AssignedTask
from utils import calculate_order_cost, is_weekend, calculate_task_end_date
from models.input_data import Worker
import pygad
from checker import check, only_calculate_earning

class GaOptimizer:
    def __init__(self, input_data: InputData, orders: Orders):
        self.input_data = input_data
        self.orders = orders
        
        # Сортируем задачи внутри каждого заказа по количеству зависимостей
        for order in self.orders.root:
            order.tasks.sort(key=lambda task: len(task.dependsOn))
            
        # Сортируем работников по убыванию продуктивности
        self.input_data.workers.sort(key=lambda worker: worker.productivity, reverse=True)
            
        self.all_tasks_count = sum(len(o.tasks) for o in orders.root)

    def optimize(self) -> WorkPlan:
        start_time = time.time()
        
        ga_instance = pygad.GA(
            num_generations=20,
            num_parents_mating=6,
            fitness_func=self._fitness_function,
            sol_per_pop=10,
            num_genes=len(self.orders.root),
            crossover_type="scattered",
            init_range_low=1,
            init_range_high=len(self.orders.root),
            gene_type=int,
            mutation_type="random",
            mutation_probability=0.1,
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

    def fine_tune_simulated_annealing(self, plan: WorkPlan) -> WorkPlan:
        orders_by_task_id = {}
        tasks_by_task_id = {}
        for order in self.orders.root:
            for task in order.tasks:
                orders_by_task_id[task.id] = order
                tasks_by_task_id[task.id] = task
        
        # собираем все задачи из плана
        tasks = [tasks_by_task_id[task.taskId] for task in plan.root]
        
        # определяем приоритеты заказов в плане
        orders_counted = set()
        priorities = [0] * len(self.orders.root)
        next_priority = 0
        for assigned_task in plan.root:
            order = orders_by_task_id[assigned_task.taskId]
            if order.id not in orders_counted:
                orders_counted.add(order.id)
                order_index = self.orders.root.index(order)
                priorities[order_index] = next_priority
                next_priority += 1
        
        # задаём начальные параметры для имитации отжига
        temperature = 1000
        cooling_rate = 0.999
        max_iterations = 1000
        
        # храним все успешные замены в словаре forced_deps
        forced_deps = {}

        # выполняем имитацию отжига
        for _ in range(max_iterations):
            if len(tasks) < 2:
                continue
                
            # выбираем две соседние задачи
            pos = random.randint(0, len(tasks) - 2)
            task1 = tasks[pos]
            task2 = tasks[pos + 1]
            
            # добавляем новую зависимость в forced_deps
            if task2.id not in forced_deps:
                forced_deps[task2.id] = []
            forced_deps[task2.id].append(task1.id)
            
            # создаём новый план с учетом всех зависимостей и текущих приоритетов
            new_plan = self._create_plan(priorities, forced_dependencies=forced_deps)

            # вычисляем разницу в прибыли
            current_earning = only_calculate_earning(self.orders, plan, self.input_data)
            new_earning = only_calculate_earning(self.orders, new_plan, self.input_data)
            
            # вычисляем относительную разницу в прибыли и масштабируем её
            if current_earning != 0:
                relative_diff = (new_earning - current_earning) / current_earning
                # масштабируем разницу, чтобы она была в том же порядке, что и температура
                scaled_diff = relative_diff * 1000  # температура начинается с 1000
            else:
                scaled_diff = 1000 if new_earning > 0 else 0
            
            # вычисляем вероятность перехода к новому плану
            # используем более крутую функцию для вероятности
            probability = 1 / (1 + math.exp(-scaled_diff / temperature))

            # переходим к новому плану, если он лучше
            if scaled_diff > 0:
                plan = new_plan
                print(f"Приняли изменение. Новая прибыль: {new_earning:.2f}")
            else:
                # если не приняли новый план, удаляем добавленную зависимость
                forced_deps[task2.id].remove(task1.id)
                if not forced_deps[task2.id]:
                    del forced_deps[task2.id]
                print("Отклонили изменение")
            
            # охлаждаем температуру
            temperature *= cooling_rate 

        return plan

    def _on_generation(self, ga_instance):
        print(f"Generation = {ga_instance.generations_completed}")
        print(f"Fitness    = {ga_instance.best_solution(pop_fitness=ga_instance.last_generation_fitness)[1]}")
        #print(f"Solution   = {ga_instance.best_solution(pop_fitness=ga_instance.last_generation_fitness)[0][:10]}")

    def _fitness_function(self, ga, solution: List[int], index: int) -> float:
        plan = self._create_plan(solution)
        result = only_calculate_earning(self.orders, plan, self.input_data)
        #print(f"    {result}")
        return result

    def _create_plan(self, priorities: List[int], forced_dependencies: Dict[str, List[str]] = None) -> WorkPlan:
        work_plan_dict = {}
        priority_by_task_id = {}
        task_by_id = {}
        excluded_task_ids = []
        date_available_by_worker_id = {}

        # предзаполним даты доступности для каждого работника
        for worker in self.input_data.workers:
            date_available_by_worker_id[worker.id] = self.input_data.currentDate

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
                    
                    # Проверяем принудительные зависимости, игнорируя исключенные задачи
                    forced_deps_satisfied = True
                    if forced_dependencies and task_id in forced_dependencies:
                        forced_deps_satisfied = all(dep_id in work_plan_dict for dep_id in forced_dependencies[task_id] if dep_id not in excluded_task_ids)
                    
                    if dependencies_satisfied and forced_deps_satisfied:
                        next_task = task
                        break

            if next_task is not None:
                min_date = self._minimum_allowed_date_by_dependencies(next_task, work_plan_dict)
                
                # Проверяем принудительные зависимости для даты начала, игнорируя исключенные задачи
                if forced_dependencies and next_task.id in forced_dependencies:
                    for dep_id in forced_dependencies[next_task.id]:
                        if dep_id in work_plan_dict and dep_id not in excluded_task_ids:
                            min_date = max(min_date, work_plan_dict[dep_id].end + timedelta(days=1))
                
                worker = self._select_worker(next_task, date_available_by_worker_id)
                min_date = max(min_date, date_available_by_worker_id[worker.id])
                min_date = self._closest_workday(min_date)

                end_date = calculate_task_end_date(min_date, next_task.baseDuration, worker.productivity, self.input_data.holidays)

                # назначаем задачу
                work_plan_dict[next_task.id] = AssignedTask(taskId=next_task.id, workerId=worker.id, start=min_date, end=end_date)
                date_available_by_worker_id[worker.id] = end_date + timedelta(days=1)

                # проверим, завершён ли текущий заказ
                order = next(o for o in self.orders.root if next_task in o.tasks)
                if all(t.id in work_plan_dict for t in order.tasks):
                    order_earning, order_penalty, order_delay, order_is_completed = calculate_order_cost(order, work_plan_dict)
                    if not order_is_completed:
                        # заказ завершён без прибыли, исключим все его задачи из плана
                        for task in order.tasks:
                            work_plan_dict.pop(task.id)
                            excluded_task_ids.append(task.id)

                        # нужно пересчитать даты доступности для всех работников
                        for worker in self.input_data.workers:
                            worker_tasks = [t.end for t in work_plan_dict.values() if t.workerId == worker.id]
                            if worker_tasks:
                                max_task_end_date = max(worker_tasks)
                                date_available_by_worker_id[worker.id] = max_task_end_date + timedelta(days=1)
                            else:
                                date_available_by_worker_id[worker.id] = self.input_data.currentDate

        # сортируем задачи по дате начала
        sorted_tasks = sorted(work_plan_dict.values(), key=lambda x: x.start)
        return WorkPlan(sorted_tasks)

    def _minimum_allowed_date_by_dependencies(self, task: Task, work_plan_dict: dict[str, AssignedTask]) -> date:
        min_date = self.input_data.currentDate
        for dep_id in task.dependsOn:
            min_date = max(min_date, work_plan_dict[dep_id].end + timedelta(days=1))
        return min_date

    def _select_worker(self, task: Task, date_available_by_worker_id: dict[str, date]) -> Worker:
        min_date = date.max
        selected_worker = None
        for worker in self.input_data.workers:
            if task.workTypeId in worker.workTypeIds:
                if date_available_by_worker_id[worker.id] < min_date:
                    min_date = date_available_by_worker_id[worker.id]
                    selected_worker = worker
        return selected_worker

    def _closest_workday(self, date: date) -> date:
        if not is_weekend(date) and date not in self.input_data.holidays:
            return date
        else:
            return self._closest_workday(date + timedelta(days=1))
