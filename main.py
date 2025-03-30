from pydantic import TypeAdapter
from checker import check
from gantt_chart import create_gantt_chart
from models import InputData, Orders, WorkPlan
from optimizer import optimize
from utils import load_json
from datetime import timedelta
from models.orders import Order, Task
from models.input_data import Worker
from copy import deepcopy

if __name__ == "__main__":
    print("Начинаем проверку")

    input_data = TypeAdapter(InputData).validate_python(load_json("input_data.json"))
    orders = TypeAdapter(Orders).validate_python(load_json("orders.json"))
    # work_plan = TypeAdapter(WorkPlan).validate_python(load_json("work_plan.json"))
    work_plan = optimize(orders, input_data)
    with open("data/work_plan.json", "w", encoding="utf-8") as f:
        f.write(work_plan.model_dump_json(indent=2))

    print(f"Всего заказов: {len(orders.root)}")
    result = check(orders, work_plan, input_data)
    print(result)

    create_gantt_chart(orders, work_plan, input_data)

def change_day_cost(input_data: InputData, new_day_cost: float) -> InputData:
    return InputData(
        **input_data.model_dump(),
        dayCost=new_day_cost
    )

def change_workers(input_data: InputData, min_workers: int) -> InputData:
    # Создаем глубокую копию входных данных
    new_data = InputData(**input_data.model_dump())
    workers = deepcopy(new_data.workers)
    
    # Функция для проверки, можно ли удалить работника
    def can_remove_worker(worker: Worker) -> bool:
        # Проверяем, не потеряем ли мы единственного носителя какого-то типа работ
        for wt_id in worker.workTypeIds:
            # Проверяем, есть ли еще кто-то с этим типом работ
            has_other_worker = any(
                wt_id in w.workTypeIds and w.id != worker.id 
                for w in workers
            )
            if not has_other_worker:
                return False
        return True
    
    # Пока количество работников больше минимального
    while len(workers) > min_workers:
        # Ищем последнего работника, которого можно удалить
        worker_to_remove = None
        for worker in reversed(workers):
            if can_remove_worker(worker):
                worker_to_remove = worker
                break
        
        # Если не нашли работника для удаления, прерываем цикл
        if worker_to_remove is None:
            break
            
        # Удаляем работника
        workers.remove(worker_to_remove)
    
    # Обновляем список работников в новых данных
    new_data.workers = workers
    return new_data

def change_deadline(orders: Orders, add_days: int) -> Orders:
    new_orders = []
    for order in orders.root:
        # Создаем новый список задач
        new_tasks = [
            Task(
                id=task.id,
                workTypeId=task.workTypeId,
                dependsOn=task.dependsOn.copy(),
                baseDuration=task.baseDuration
            )
            for task in order.tasks
        ]
        
        # Создаем новый заказ с измененным дедлайном
        new_order = Order(
            id=order.id,
            tasks=new_tasks,
            deadline=order.deadline + timedelta(days=add_days),
            earning=order.earning,
            penaltyByDay=order.penaltyByDay
        )
        new_orders.append(new_order)
    
    return Orders(root=new_orders)

def calculate_variant(orders: Orders, input_data: InputData) -> float:
    # Создаем план работ для текущего варианта
    work_plan = optimize(orders, input_data)
    # Проверяем план и получаем результат
    result = check(orders, work_plan, input_data)
    return result.total_earning

def create_variants(orders: Orders, input_data: InputData) -> dict:
    # Создаем матрицу результатов
    matrix = {}
    
    # Перебираем количество сотрудников от 5 до 15
    for workers_count in range(5, 16):
        # Модифицируем input_data для текущего количества сотрудников
        modified_input = change_workers(input_data, workers_count)
        
        # Создаем строку матрицы для текущего количества работников
        matrix[workers_count] = {}
        
        # Перебираем сдвиг дедлайна от 0 до 150 дней с шагом 15
        for deadline_shift in range(0, 151, 15):
            # Модифицируем заказы для текущего сдвига дедлайна
            modified_orders = change_deadline(orders, deadline_shift)
            
            # Рассчитываем результат для текущего варианта
            result = calculate_variant(modified_orders, modified_input)
            
            # Сохраняем результат в матрицу
            matrix[workers_count][deadline_shift] = result
    
    return matrix