#!/bin/bash
set -e  # выход при любой ошибке

# Переход в рабочую директорию с проверкой
cd /app || { echo "❌ Ошибка: не удалось перейти в /app"; exit 1; }

echo "=== Bocchi Downloader ==="
echo "BOT_MODE = ${BOT_MODE:-default}"

# Если задан BOT_MODE, используем его. Иначе — старая логика (на случай обратной совместимости)
if [ "$BOT_MODE" = "stable" ]; then
    if [ -f "bocchi_bot_host.py" ]; then
        echo "🚀 Запускаем стабильную версию (bocchi_bot_host.py)"
        exec python bocchi_bot_host.py
    else
        echo "❌ Ошибка: файл bocchi_bot_host.py не найден"
        exit 1
    fi
elif [ "$BOT_MODE" = "beta" ]; then
    if [ -f "bocchi_host_full.py" ]; then
        echo "⚡ Запускаем бета-версию (bocchi_host_full.py)"
        exec python bocchi_host_full.py
    else
        echo "❌ Ошибка: файл bocchi_host_full.py не найден"
        exit 1
    fi
else
    # Поведение по умолчанию: приоритет полной версии, если есть
    if [ -f "bocchi_host_full.py" ]; then
        echo "⚡ Запускаем полную версию (по умолчанию)"
        exec python bocchi_host_full.py
    elif [ -f "bocchi_bot_host.py" ]; then
        echo "🚀 Запускаем классическую версию"
        exec python bocchi_bot_host.py
    else
        echo "❌ Ошибка: ни один файл бота не найден!"
        exit 1
    fi
fi