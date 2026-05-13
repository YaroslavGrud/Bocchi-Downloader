#!/bin/bash
set -e  # прерывать выполнение при любой ошибке

# Переход в рабочую директорию с проверкой
cd "$HOME/bocchi_bot" || { echo "❌ Папка $HOME/bocchi_bot не найдена"; exit 1; }

echo "🛑 Останавливаем и удаляем старый контейнер..."
docker stop bocchi_bot 2>/dev/null && echo "   Контейнер остановлен"
docker rm bocchi_bot 2>/dev/null && echo "   Контейнер удалён"

echo "🔑 Введите токен Telegram бота:"
read -r TOKEN

# Если токен не введён – показываем инструкцию и выходим
if [ -z "$TOKEN" ]; then
    echo "❌ Токен не введён. Перезапуск отменён."
    echo "💡 Выполните вручную:"
    echo "cd \"$HOME/bocchi_bot\" && docker stop bocchi_bot 2>/dev/null ; docker rm bocchi_bot 2>/dev/null ; read -r -p \"Введите токен: \" TOKEN && docker run -d --name bocchi_bot --restart unless-stopped -e TELEGRAM_TOKEN=\"\$TOKEN\" -v \"\$(pwd)/data:/app/data\" bocchi_bot && docker logs -f bocchi_bot"
    exit 1
fi

echo "🚀 Запускаем новый контейнер..."
if docker run -d \
  --name bocchi_bot \
  --restart unless-stopped \
  -e "TELEGRAM_TOKEN=$TOKEN" \
  -v "$(pwd)/data:/app/data" \
  bocchi_bot
then
    echo "✅ Бот перезапущен. Показываем логи (нажмите Ctrl+C для выхода):"
    docker logs -f bocchi_bot
else
    echo "❌ Ошибка при запуске контейнера."
    echo "💡 Попробуйте выполнить вручную:"
    echo "cd \"$HOME/bocchi_bot\" && docker stop bocchi_bot 2>/dev/null ; docker rm bocchi_bot 2>/dev/null ; read -r -p \"Введите токен: \" TOKEN && docker run -d --name bocchi_bot --restart unless-stopped -e TELEGRAM_TOKEN=\"\$TOKEN\" -v \"\$(pwd)/data:/app/data\" bocchi_bot && docker logs -f bocchi_bot"
    exit 1
fi