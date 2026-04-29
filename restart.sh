#!/bin/bash

# Переходим в папку с ботом
cd ~/bocchi_bot

# Проверяем наличие файла .env, если нет — запрашиваем токен
if [ ! -f .env ]; then
    echo "📝 Файл .env не найден."
    read -p "Введите токен Telegram бота: " TOKEN
    echo "TELEGRAM_TOKEN=$TOKEN" > .env
    echo "✅ Файл .env создан."
fi

# Останавливаем и удаляем старый контейнер
echo "🛑 Останавливаем и удаляем старый контейнер..."
docker stop bocchi_bot 2>/dev/null && echo "   Контейнер остановлен."
docker rm bocchi_bot 2>/dev/null && echo "   Контейнер удалён."

# Пересобираем образ
echo "🐳 Пересобираем образ..."
docker build -t bocchi_bot .

# Запускаем новый контейнер
echo "🚀 Запускаем контейнер..."
docker run -d \
  --name bocchi_bot \
  --restart unless-stopped \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  bocchi_bot

echo "✅ Бот перезапущен!"
echo "📋 Логи: docker logs -f bocchi_bot"
echo "🛑 Остановить: docker stop bocchi_bot"
