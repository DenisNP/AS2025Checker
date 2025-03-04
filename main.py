from pydantic import TypeAdapter
from checker import check
from models import InputData, Orders, WorkPlan
from utils import load_json

if __name__ == "__main__":
    print("Начинаем проверку")

    input_data = TypeAdapter(InputData).validate_python(load_json("input_data.json"))
    orders = TypeAdapter(Orders).validate_python(load_json("orders.json"))
    work_plan = TypeAdapter(WorkPlan).validate_python(load_json("work_plan.json"))

    print(f"Всего заказов: {len(orders.root)}")
    result = check(orders, work_plan, input_data)
    print(result)
