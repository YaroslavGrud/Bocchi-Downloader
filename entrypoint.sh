#!/bin/bash
cd /app
if [ -f "bocchi_host_full.py" ]; then
    echo "🚀 Запускаем полную версию бота (bocchi_host_full.py)"
    exec python bocchi_host_full.py
elif [ -f "bocchi_bot_host.py" ]; then
    echo "🚀 Запускаем классическую версию бота (bocchi_bot_host.py)"
    exec python bocchi_bot_host.py
else
    echo "❌ Ошибка: не найден ни один файл бота!"
    exit 1
fi
