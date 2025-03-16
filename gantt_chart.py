from datetime import datetime, date, timedelta
import plotly.figure_factory as ff
from typing import Dict, List
from models import WorkPlan, Orders, InputData, TaskDetails
from utils import aggregate_work_plan
from dash import Dash, html, dcc
import webbrowser
from threading import Timer
import random
import colorsys

def generate_random_color(h_min=0, h_max=1, s_min=0.6, s_max=0.95, v_min=0.6, v_max=0.95):
    """
    Генерирует случайный цвет в формате HEX с контролем яркости и насыщенности.
    
    Args:
        h_min, h_max: float - диапазон оттенка (0-1)
        s_min, s_max: float - диапазон насыщенности (0-1)
        v_min, v_max: float - диапазон яркости (0-1)
    
    Returns:
        str: Цвет в формате HEX (#RRGGBB)
    """
    h = random.uniform(h_min, h_max)
    s = random.uniform(s_min, s_max)
    v = random.uniform(v_min, v_max)
    
    rgb = tuple(round(i * 255) for i in colorsys.hsv_to_rgb(h, s, v))
    return f'#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}'

def create_gantt_chart(orders: Orders, work_plan: WorkPlan, input_data: InputData, port: int = 8050) -> None:
    """
    Создает интерактивную диаграмму Ганта на основе плана работ и показывает её в браузере.
    
    Args:
        orders: Orders - список заказов
        work_plan: WorkPlan - план работ
        input_data: InputData - входные данные
        port: int - порт для локального сервера (по умолчанию 8050)
    """
    # Агрегируем данные плана работ
    plan_details, _ = aggregate_work_plan(orders, work_plan, input_data)
    
    # Подготавливаем данные для диаграммы
    gantt_data = []
    
    # Словарь для хранения цветов по заказам
    order_colors = {}
    
    # Создаем словарь цветов для каждого заказа
    # Равномерно распределяем оттенки по цветовому кругу
    total_orders = len(orders.root)
    for i, order in enumerate(orders.root):
        # Используем равномерное распределение оттенков
        hue = i / total_orders
        order_colors[order.id] = generate_random_color(h_min=hue, h_max=hue)
    
    # Создаем записи для диаграммы Ганта
    for task_id, details in plan_details.items():
        task = details.task
        assigned_task = details.assigned_task
        worker = details.worker
        order = details.order
        
        # Определяем цвет для заказа
        color = order_colors.get(order.id, '#808080')
        
        # Формируем описание задачи
        description = (f"Заказ: {order.id}<br>"
                      f"Задача: {task_id}<br>"
                      f"Тип работы: {task.workTypeId}<br>"
                      f"Работник: {worker.name}<br>"
                      f"Базовая длительность: {task.baseDuration} дн.<br>"
                      f"Продуктивность работника: {worker.productivity}")
        
        # Добавляем один день к конечной дате для корректного отображения
        end_date = assigned_task.end + timedelta(days=1)
        
        gantt_data.append({
            'Task': worker.name,  # Группировка по работникам
            'Start': assigned_task.start.strftime('%Y-%m-%d'),
            'Finish': end_date.strftime('%Y-%m-%d'),  # Используем дату + 1 день
            'Description': description,
            'Resource': order.id,  # Используем ID заказа вместо ID задачи
            'Complete': 100,
            'Color': color
        })

    # Создаем фигуру диаграммы Ганта
    if gantt_data:
        fig = ff.create_gantt(gantt_data,
                            colors=dict((task['Resource'], task['Color']) for task in gantt_data),
                            index_col='Resource',
                            show_colorbar=True,
                            group_tasks=True,
                            showgrid_x=True,
                            showgrid_y=True)
        
        # Настраиваем внешний вид
        fig.update_layout(
            title='План работ',
            xaxis_title='Дата',
            yaxis_title='Работники',
            height=max(len(set(task['Task'] for task in gantt_data)) * 100, 600),
            showlegend=True
        )
        
        # Создаем Dash приложение
        app = Dash(__name__)
        
        # Определяем layout приложения
        app.layout = html.Div([
            html.Div(style={'width': '100%', 'height': '100vh'}, children=[
                dcc.Graph(figure=fig, style={'height': '100%'})
            ])
        ])
        
        # Функция для открытия браузера
        def open_browser():
            webbrowser.open_new(f'http://localhost:{port}/')
        
        # Открываем браузер через 1 секунду после запуска сервера
        Timer(1, open_browser).start()
        
        # Запускаем сервер
        print(f"\nЗапускаем сервер на http://localhost:{port}")
        print("Для завершения работы нажмите Ctrl+C")
        app.run_server(debug=False, port=port) 