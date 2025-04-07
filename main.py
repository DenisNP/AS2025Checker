from pydantic import TypeAdapter

from advanced_optimizer import AdvancedOptimizer
from checker import check, only_calculate_earning
from ga_optimizer import GaOptimizer
from gantt_chart import create_gantt_chart
from models import InputData, Orders, WorkPlan
from simple_optimizer import SimpleOptimizer
from utils import load_json, save_to_file

def optimize_simple(_input_data: InputData, _orders: Orders) -> WorkPlan:
    simple_optimizer = SimpleOptimizer(_input_data, _orders)
    return simple_optimizer.optimize()

def optimize_genetic(_input_data: InputData, _orders: Orders) -> WorkPlan:
    ga_optimizer = GaOptimizer(input_data, orders)
    return ga_optimizer.optimize()

def optimize_advanced(_input_data: InputData, _orders: Orders) -> WorkPlan:
    advanced_optimizer = AdvancedOptimizer(_input_data, _orders)
    best_result = 0
    best_plan = None
    for ec in range(1, 10):
        for ac in range(1, 10):
            current_plan = advanced_optimizer.optimize(ec / 10.0, ac / 10.0)
            current_earning = only_calculate_earning(_orders, current_plan, _input_data)
            print(f"Ec: {ec / 10.0}, Ac: {ac / 10.0}, Earning: {current_earning}")
            if current_earning > best_result:
                best_result = current_earning
                best_plan = current_plan
                
    return best_plan

if __name__ == "__main__":
    print("Начинаем проверку")

    input_data = TypeAdapter(InputData).validate_python(load_json("input_data2.json"))
    orders = TypeAdapter(Orders).validate_python(load_json("orders2.json"))
    work_plan = None

    print(f"Всего заказов: {len(orders.root)}")

    mode = 4

    if mode == 1:
        work_plan = TypeAdapter(WorkPlan).validate_python(load_json("work_plan.json"))
    elif mode == 2:
        work_plan = optimize_simple(input_data, orders)
        save_to_file(work_plan, "work_plan.json")
    elif mode == 3:
        work_plan = optimize_genetic(input_data, orders)
        save_to_file(work_plan, "work_plan.json")
    elif mode == 4:
        work_plan = optimize_advanced(input_data, orders)
        save_to_file(work_plan, "work_plan.json")

    result = check(orders, work_plan, input_data)
    print(result)

    create_gantt_chart(orders, work_plan, input_data)
    

    