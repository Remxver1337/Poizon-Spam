#!/bin/bash
echo "🤖 Запуск Telegram Mirror Bot..."

# Проверка .env файла
if [ ! -f .env ]; then
    echo "❌ Ошибка: Файл .env не найден!"
    echo "   Создайте его из .env.example"
    exit 1
fi

# Проверка зависимостей
if [ ! -d "venv" ] && [ ! -f "requirements.txt" ]; then
    echo "⚠️ Зависимости не установлены"
    read -p "Установить зависимости? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        pip install -r requirements.txt
    fi
fi

# Запуск бота
echo "🚀 Запуск основного бота..."
python main.py