from datetime import date
from typing import List
from pydantic import BaseModel, RootModel


class Task(BaseModel):
    id: str
    workTypeId: str
    dependsOn: List[str]
    baseDuration: int

class Order(BaseModel):
    id: str
    tasks: List[Task]
    deadline: date
    earning: float
    penaltyByDay: float

Orders = RootModel[List[Order]]
