// D:\WebAppNginxSQL\static\script.js

const todoForm = document.getElementById('todoForm');
const todoTitleInput = document.getElementById('todoTitle');
const todoList = document.getElementById('todoList');
const statusMessage = document.getElementById('statusMessage');

async function fetchTodos() {
    try {
        const response = await fetch('/api/todos');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        todoList.innerHTML = '';
        data.forEach(todo => {
            const li = document.createElement('li');
            li.dataset.id = todo.id;
            li.classList.toggle('completed', todo.is_completed);
            li.innerHTML = `
                <span class="todo-title">${todo.title}</span>
                <div class="actions">
                    <button class="complete-btn" data-completed="${todo.is_completed}" title="${todo.is_completed ? 'Пометить как невыполненное' : 'Пометить как выполненное'}">
                        ${todo.is_completed ? '✅' : '❓'}
                    </button>
                    <button class="delete-btn" title="Удалить">🗑️</button>
                </div>
            `;
            todoList.appendChild(li);
        });
        displayStatus('Задачи загружены.', 'success');
    } catch (error) {
        console.error('Ошибка при загрузке задач:', error);
        displayStatus('Не удалось загрузить задачи.', 'error');
    }
}

async function addTodo(title) {
    try {
        const response = await fetch('/api/todos', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: title })
        });
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        await response.json();
        displayStatus('Задача добавлена!', 'success');
        todoTitleInput.value = '';
        fetchTodos();
    } catch (error) {
        console.error('Ошибка при добавлении задачи:', error);
        displayStatus('Не удалось добавить задачу.', 'error');
    }
}

async function toggleTodoCompleted(id, isCompleted) {
    try {
        const response = await fetch(`/api/todos/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_completed: !isCompleted })
        });
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        await response.json();
        displayStatus('Статус задачи обновлен!', 'success');
        fetchTodos();
    } catch (error) {
        console.error('Ошибка при обновлении статуса задачи:', error);
        displayStatus('Не удалось обновить статус задачи.', 'error');
    }
}

async function deleteTodo(id) {
    if (!confirm('Вы уверены, что хотите удалить эту задачу?')) {
        return;
    }
    try {
        const response = await fetch(`/api/todos/${id}`, {
            method: 'DELETE'
        });
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        // await response.json(); // Этот вызов не нужен, т.к. 204 No Content не возвращает JSON

        // --- ДОБАВЛЯЕМ ЭТУ ЧАСТЬ КОДА ---
        // Находим элемент списка (li) по его data-id и удаляем его из DOM
        const itemToRemove = document.querySelector(`li[data-id="${id}"]`);
        if (itemToRemove) {
            itemToRemove.remove(); // Удаляем элемент из HTML
        }
        // --- КОНЕЦ ДОБАВЛЕННОГО КОДА ---

        displayStatus('Задача удалена!', 'success');
        // fetchTodos(); // Этот вызов теперь опционален, т.к. мы удаляем элемент напрямую
                         // Его можно оставить как "запасной" вариант на случай рассинхронизации,
                         // но для быстрого визуального эффекта лучше удалять напрямую.
                         // Для этого приложения, если не будет других проблем, можно убрать.
                         // Пока оставим, чтобы гарантировать синхронизацию.
    } catch (error) {
        console.error('Ошибка при удалении задачи:', error);
        displayStatus('Не удалось удалить задачу.', 'error');
    }
}



function displayStatus(message, type) {
    statusMessage.textContent = message;
    statusMessage.className = `status-message ${type}`;
    setTimeout(() => {
        statusMessage.textContent = '';
        statusMessage.className = 'status-message';
    }, 3000);
}

// Event Listeners
todoForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const title = todoTitleInput.value.trim();
    if (title) {
        addTodo(title);
    } else {
        displayStatus('Пожалуйста, введите название задачи.', 'error');
    }
});

todoList.addEventListener('click', (e) => {
    const listItem = e.target.closest('li');
    if (!listItem) return;

    const todoId = parseInt(listItem.dataset.id);

    if (e.target.classList.contains('complete-btn')) {
        const isCompleted = e.target.dataset.completed === 'true';
        toggleTodoCompleted(todoId, isCompleted);
    } else if (e.target.classList.contains('delete-btn')) {
        deleteTodo(todoId);
    }
});

// Загружаем задачи при загрузке страницы
fetchTodos();