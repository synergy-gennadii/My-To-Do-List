import os
import sys
import pyodbc
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# --- Настройки логирования ---
LOG_FOLDER = "logs"
LOG_FILE = os.path.join(LOG_FOLDER, "app_startup_nginx.log")

# Исправляем ошибку: RotatingFileFileHandler был неправильно определен или отсутствовал импорт.
# Если вы используете RotatingFileHandler из logging.handlers, то класс выше не нужен.
# Удаляем: class RotatingFileFileHandler: pass

file_handler = None

if not os.path.exists(LOG_FOLDER):
    try:
        os.makedirs(LOG_FOLDER)
        # Убедитесь, что здесь используется правильный RotatingFileHandler из logging.handlers
        file_handler = RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
    except OSError as e:
        print(f"ERROR: Could not create log directory {LOG_FOLDER}: {e}", file=sys.stderr)
else:
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

if file_handler:
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

logger.info("Приложение FastAPI запускается...")

# --- Настройки подключения к SQL Server ---
SERVER_NAME = r"KORSAVEC\SQLEXPRESS"
DATABASE_NAME = "WebAppDataBase"
DRIVER = "{ODBC Driver 18 for SQL Server}" # Или "{ODBC Driver 17 for SQL Server}"

def get_db_connection():
    connection_string = (
        f"DRIVER={DRIVER};"
        f"SERVER={SERVER_NAME};"
        f"DATABASE={DATABASE_NAME};"
        f"Trusted_Connection=yes;"
        f"TrustServerCertificate=yes;" # Важно для само-подписанных сертификатов
    )
    try:
        conn = pyodbc.connect(connection_string)
        logger.info("Успешное подключение к базе данных с аутентификацией Windows.")
        return conn
    except pyodbc.Error as ex:
        sqlstate = ex.args[0]
        logger.error(f"Ошибка подключения к базе данных: {ex}")
        logger.error(f"SQLSTATE: {sqlstate}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database connection error: {ex}")

# --- НОВАЯ ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ПОЛУЧЕНИЯ ЗАДАЧИ ПО ID ---
class TodoItem:
    def __init__(self):
        self.title = None
        self.is_completed = None

    pass


async def _get_todo_from_db(todo_id: int, conn: pyodbc.Connection) -> TodoItem | None:
    """Вспомогательная функция для получения одной задачи из БД по ID."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, title, is_completed, created_at FROM Todos WHERE id = ?", todo_id)
        row = cursor.fetchone()
        if row:
            return TodoItem(
                id=row[0],
                title=row[1],
                is_completed=bool(row[2]),
                created_at=row[3]
            )
        return None
    except pyodbc.Error as ex:
        logger.error(f"Ошибка БД в _get_todo_from_db для ID {todo_id}: {ex}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error retrieving todo: {ex}")
    finally:
        cursor.close() # Важно закрывать курсор после использования

app = FastAPI(
    title="Simple Todo List App",
    description="FastAPI Backend для простого списка дел с MS SQL Server.",
    version="1.0.0",
)

# Pydantic модели для валидации данных Todo
class TodoItem(BaseModel):
    id: int
    title: str
    is_completed: bool
    created_at: datetime

class TodoCreate(BaseModel):
    title: str

class TodoUpdate(BaseModel):
    title: str | None = None
    is_completed: bool | None = None

# Монтируем папку 'static' для статических файлов
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=FileResponse)
async def read_root_html():
    """Отдача HTML-страницы для Todo List из файла."""
    html_file_path = os.path.join("static", "index.html")
    if not os.path.exists(html_file_path):
        logger.error(f"Файл HTML не найден: {html_file_path}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="HTML file not found")
    logger.info(f"Запрос к корневому пути '/', отдача {html_file_path}.")
    return FileResponse(html_file_path)

# --- API endpoints для Todo List ---

@app.post("/api/todos", response_model=TodoItem, status_code=status.HTTP_201_CREATED)
async def create_todo(todo: TodoCreate):
    """Добавляет новую задачу."""
    logger.info(f"Получен запрос на создание задачи: {todo.title}")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO Todos (title) OUTPUT INSERTED.id, INSERTED.title, INSERTED.is_completed, INSERTED.created_at VALUES (?)",
            todo.title
        )
        new_todo_data = cursor.fetchone()
        conn.commit()
        if new_todo_data:
            new_todo = TodoItem(
                id=new_todo_data[0],
                title=new_todo_data[1],
                is_completed=bool(new_todo_data[2]),
                created_at=new_todo_data[3]
            )
            logger.info(f"Задача '{new_todo.title}' успешно добавлена с ID: {new_todo.id}")
            return new_todo
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve created todo item.")
    except pyodbc.Error as ex:
        logger.error(f"Ошибка БД при создании задачи: {ex}")
        conn.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error creating todo: {ex}")
    finally:
        conn.close()

@app.get("/api/todos", response_model=list[TodoItem])
async def get_all_todos():
    """Возвращает все задачи."""
    logger.info("Получен запрос на получение всех задач.")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, title, is_completed, created_at FROM Todos ORDER BY created_at DESC")
        rows = cursor.fetchall()
        todos = []
        for row in rows:
            todos.append(TodoItem(
                id=row[0],
                title=row[1],
                is_completed=bool(row[2]),
                created_at=row[3]
            ))
        logger.info(f"Получено {len(todos)} задач из БД.")
        return todos
    except pyodbc.Error as ex:
        logger.error(f"Ошибка БД при получении задач: {ex}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error fetching todos: {ex}")
    finally:
        conn.close()

@app.get("/api/todos/{todo_id}", response_model=TodoItem)
async def get_todo_by_id(todo_id: int):
    """Возвращает задачу по ID."""
    logger.info(f"Получен запрос на получение задачи с ID: {todo_id}")
    conn = get_db_connection()
    try:
        todo = await _get_todo_from_db(todo_id, conn) # Используем новую вспомогательную функцию
        if todo:
            logger.info(f"Задача с ID {todo_id} найдена.")
            return todo
        logger.warning(f"Задача с ID {todo_id} не найдена.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found")
    except pyodbc.Error as ex: # Отдельный отлов ошибок БД для этого endpoint, если нужно
        logger.error(f"Ошибка БД при получении задачи по ID: {ex}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error fetching todo: {ex}")
    finally:
        conn.close()

@app.put("/api/todos/{todo_id}", response_model=TodoItem)
async def update_todo(todo_id: int, todo: TodoUpdate):
    """Обновляет существующую задачу."""
    logger.info(f"Получен запрос на обновление задачи с ID: {todo_id} с данными: {todo.model_dump()}")
    conn = get_db_connection()
    try:
        # Сначала получаем текущее состояние через вспомогательную функцию
        current_todo = await _get_todo_from_db(todo_id, conn)
        if not current_todo:
            logger.warning(f"Попытка обновить несуществующую задачу с ID: {todo_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found")

        # Используем текущие значения, если новые не предоставлены
        updated_title = todo.title if todo.title is not None else current_todo.title
        updated_is_completed = todo.is_completed if todo.is_completed is not None else current_todo.is_completed

        cursor = conn.cursor() # Создаем курсор здесь
        cursor.execute(
            "UPDATE Todos SET title = ?, is_completed = ? WHERE id = ?",
            updated_title, updated_is_completed, todo_id
        )
        conn.commit()

        # Получаем обновленную задачу через вспомогательную функцию
        updated_todo = await _get_todo_from_db(todo_id, conn)
        if updated_todo:
            logger.info(f"Задача с ID {todo_id} успешно обновлена.")
            return updated_todo
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve updated todo item after update.")
    except pyodbc.Error as ex:
        logger.error(f"Ошибка БД при обновлении задачи: {ex}")
        conn.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error updating todo: {ex}")
    finally:
        conn.close()

@app.delete("/api/todos/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_todo(todo_id: int):
    """Удаляет задачу по ID."""
    logger.info(f"Получен запрос на удаление задачи с ID: {todo_id}")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM Todos WHERE id = ?", todo_id)
        if cursor.rowcount == 0:
            logger.warning(f"Попытка удалить несуществующую задачу с ID: {todo_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found")
        conn.commit()
        logger.info(f"Задача с ID {todo_id} успешно удалена.")
        return
    except pyodbc.Error as ex:
        logger.error(f"Ошибка БД при удалении задачи: {ex}")
        conn.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error deleting todo: {ex}")
    finally:
        conn.close()

@app.get("/status")
async def get_status():
    """Проверяет статус подключения к базе данных и возвращает текущее время."""
    logger.info("Запрос к '/status'")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT GETDATE()")
        current_time = cursor.fetchone()[0]
        conn.close()
        logger.info("Статус базы данных: Успешно")
        return {"database_connection": "successful", "current_db_time": str(current_time)}
    except HTTPException as ex:
        logger.error(f"Ошибка получения статуса БД: {ex.detail}")
        raise ex
    except Exception as ex:
        logger.error(f"Неизвестная ошибка при получении статуса: {ex}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unknown error occurred: {ex}")

# Запуск Uvicorn при прямом вызове (для удобства, но не основной способ)
if __name__ == "__main__":
    logger.info("main.py запущен напрямую. Используйте uvicorn для запуска приложения. Рекомендуемый способ запуска FastAPI-приложения — это использование команды: 'uvicorn main:app --host 127.0.0.1 --port 8000' в командной строке")
    # uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)