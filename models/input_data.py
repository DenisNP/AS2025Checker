from datetime import date
from typing import List
from pydantic import BaseModel

class WorkType(BaseModel):
    name: str
    id: str

class Worker(BaseModel):
    id: str
    name: str
    workTypeIds: List[str]
    productivity: float

class InputData(BaseModel):
    workTypes: List[WorkType]
    companyDayCost: float
    workers: List[Worker]
    holidays: List[date]
    currentDate: date
