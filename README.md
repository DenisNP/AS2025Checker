### Подключение и запуск

```python
from checker import check
from models import InputData, Orders, WorkPlan

# загружаем или иначе собираем из данных модели, всё в формате по документации
input_data = InputData(...) # исходные данные
orders = Orders(...) # список заказов с задачами
work_plan = WorkPlan(...) # план работ

# вызываем функцию проверки
result = check(orders, work_plan, input_data)
print(result)
```

### Содержимое объекта `result`
```python
class CheckResult(BaseModel):
    success: bool # пройдена ли в принципе проверка
    total_earning: float # общий доход за вычетом штрафов и строимости работы фирмы, то есть прибыль
    raw_earning: float # общий доход без учёта потерь, то есть выручка
    total_penalty: float # общий штраф
    total_days: int # общее число календарных дней работы фирмы
    total_cost: float # общая стоимость работы фирмы за всё время
    orders_completed: int # число успешно завершённых заказов
    errors: List[str] # список ошибок
    warnings: List[str] # список дополнительной информации, например о ручном изменении длительности задач
```
