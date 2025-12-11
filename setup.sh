#!/bin/bash
echo "🚀 УСТАНОВКА ТЕЛЕГРАМ БОТА С ЗЕРКАЛАМИ"
echo "======================================"

# Создание папок
mkdir -p databases logs

# Создание requirements.txt
echo "python-telegram-bot==20.7" > requirements.txt

# Установка зависимостей
echo "📦 Установка зависимостей..."
pip install -r requirements.txt 2>/dev/null || pip3 install -r requirements.txt

echo "✅ Установка завершена!"
echo "💡 Запустите бота: python main.py"