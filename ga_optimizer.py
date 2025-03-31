from datetime import date, timedelta
from typing import List
from models import Orders, InputData, WorkPlan
from models.orders import Task
from models.work_plan import AssignedTask
from utils import calculate_order_cost, is_weekend, calculate_task_end_date
from models.input_data import Worker
import pygad
from checker import check

global orders
global input_data

def ga_optimize(_input_data: InputData, _orders: Orders) -> WorkPlan:
    global input_data
    global orders
    input_data = _input_data
    orders = _orders

    # общее количество задач по всем заказам
    all_tasks_count = sum(len(o.tasks) for o in orders.root)

    ga_instance = pygad.GA(num_generations=100,
                           num_parents_mating=10,
                           fitness_func=fitness_function,
                           sol_per_pop=20,
                           num_genes=all_tasks_count,
                           crossover_type="scattered",
                           init_range_low = 1,
                           init_range_high = all_tasks_count,
                           gene_type=int,
                           mutation_type = "random",
                           mutation_probability = 0.01,
                           on_generation=on_generation
                           )
    ga_instance.run()
    solution, solution_fitness, solution_idx = ga_instance.best_solution()
    return create_plan(solution)


def on_generation(ga_instance):
    print(f"Generation = {ga_instance.generations_completed}")
    print(f"Fitness    = {ga_instance.best_solution(pop_fitness=ga_instance.last_generation_fitness)[1]}")


def fitness_function(ga, solution: List[float], index: int) -> float:
    plan = create_plan(solution)
    result = check(orders, plan, input_data)
    return result.total_earning
    
def create_plan(priorities: List[float]) -> WorkPlan:
    # создаём план
    work_plan_dict = {}
    priority_by_task_id = {}
    task_by_id = {}
    excluded_task_ids = []
    priority_sorted_task_ids = []

    # запоминаем приоритеты для каждой задачи
    next_index = 0
    for order in orders.root:
        for task in order.tasks:
            priority_by_task_id[task.id] = priorities[next_index]
            task_by_id[task.id] = task
            next_index += 1

    priority_sorted_task_ids = sorted(priority_by_task_id, key=lambda x: priority_by_task_id[x], reverse=True)

    while len(work_plan_dict) + len(excluded_task_ids) < len(task_by_id):
        # ищем следующую по приоритету задачу
        next_task = None
        for task_id in priority_sorted_task_ids:
            task = task_by_id[task_id]
            if task_id not in work_plan_dict and task_id not in excluded_task_ids:
                # если все влияющие задачи назначены, то назначаем задачу
                if all(dep_id in work_plan_dict for dep_id in task.dependsOn):
                    next_task = task
                    break

        if next_task is not None:
            # ищем минимальную дату для назначения задачи
            min_date = _minimum_allowed_date_by_dependencies(next_task, work_plan_dict, input_data)
            min_date, worker = _minimum_allowed_date_by_worker_availability(next_task, work_plan_dict, min_date, input_data)
            min_date = _closest_workday(min_date, input_data)

            end_date = calculate_task_end_date(min_date, next_task.baseDuration, worker.productivity, input_data.holidays)

            # назначаем задачу
            work_plan_dict[next_task.id] = AssignedTask(taskId=next_task.id, workerId=worker.id, start=min_date, end=end_date)
            
            # проверим, завершён ли текущий заказ
            order = next(o for o in orders.root if next_task in o.tasks)
            if all(t.id in work_plan_dict for t in order.tasks):
                order_earning, order_penalty, order_delay, order_is_completed = calculate_order_cost(order, work_plan_dict)
                if not order_is_completed:
                    # заказ завершён без прибыли, исключим все его задачи из плана
                    for task in order.tasks:
                        work_plan_dict.pop(task.id)
                        excluded_task_ids.append(task.id)

    # возвращаем план
    return WorkPlan(list(work_plan_dict.values()))
            

def _minimum_allowed_date_by_dependencies(task: Task, work_plan_dict: dict[str, AssignedTask], input_data: InputData) -> date:
    min_date = input_data.currentDate
    # ищем все задачи, от которых зависит данная
    for dep_id in task.dependsOn:
        # если влияющаязадача уже назначена, то берём дату её окончания + 1 день
        min_date = max(min_date, work_plan_dict[dep_id].end + timedelta(days=1))

    return min_date

def _minimum_allowed_date_by_worker_availability(task: Task, work_plan_dict: dict[str, AssignedTask], desired_start: date, input_data: InputData) -> (date, Worker):
    min_date = date.max
    selected_worker = None
    # перебираем всех работников с тем же типом работ
    for worker in input_data.workers:
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

def _minimum_allowed_date_by_worker(work_plan_dict: dict[str, AssignedTask], desired_start: date, selected_worker: Worker) -> date:
    min_date = desired_start

    # ищем все назначенные задачи для этого работника
    for assigned_task in work_plan_dict.values():
        if assigned_task.workerId == selected_worker.id:
            # минимальная дата, когда конкретно этот работник может взять новую задачу
            worker_min_date = max(worker_min_date, assigned_task.end + timedelta(days=1))

    return min_date


def _closest_workday(date: date, input_data: InputData) -> date:
    if not is_weekend(date) and date not in input_data.holidays:
        return date
    else:
        return _closest_workday(date + timedelta(days=1), input_data)
