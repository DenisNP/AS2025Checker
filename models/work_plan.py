from datetime import date
from typing import List
from pydantic import BaseModel, RootModel
from .orders import Task, Order
from .input_data import Worker

class AssignedTask(BaseModel):
    taskId: str
    workerId: str
    start: date
    end: date

class TaskDetails(BaseModel):
    assigned_task: AssignedTask
    task: Task
    order: Order
    worker: Worker

WorkPlan = RootModel[List[AssignedTask]]
