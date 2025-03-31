from pydantic import TypeAdapter
from checker import check
from ga_optimizer import GaOptimizer
from gantt_chart import create_gantt_chart
from models import InputData, Orders, WorkPlan
from optimizer import optimize, _sort_orders
from utils import load_json


if __name__ == "__main__":
    print("Начинаем проверку")

    input_data = TypeAdapter(InputData).validate_python(load_json("input_data.json"))
    orders = TypeAdapter(Orders).validate_python(load_json("orders.json"))
    # work_plan = TypeAdapter(WorkPlan).validate_python(load_json("work_plan.json"))

    ga_optimizer = GaOptimizer(input_data, orders)
    work_plan = ga_optimizer.optimize()

    work_plan = ga_optimizer.fine_tune_simulated_annealing(work_plan)
    
    with open("data/work_plan.json", "w", encoding="utf-8") as f:
        f.write(work_plan.model_dump_json(indent=2))

    print(f"Всего заказов: {len(orders.root)}")
    result = check(orders, work_plan, input_data)
    print(result)

    #create_gantt_chart(orders, work_plan, input_data)

