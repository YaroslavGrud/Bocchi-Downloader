#!/bin/bash
cd ~/bocchi_bot

# Если нет .env, запрашиваем токен
if [ ! -f .env ]; then
    echo "Файл .env не найден. Введите токен Telegram бота:"
    read TOKEN
    echo "TELEGRAM_TOKEN=$TOKEN" > .env
    echo "✅ .env создан"
fi

# Остановка и удаление контейнера
docker stop bocchi_bot 2>/dev/null && echo "Контейнер остановлен"
docker rm bocchi_bot 2>/dev/null && echo "Контейнер удалён"

# Пересборка образа
docker build -t bocchi_bot .

# Запуск нового контейнера
docker run -d \
  --name bocchi_bot \
  --restart unless-stopped \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  bocchi_bot

echo "✅ Бот перезапущен"
echo "Логи: docker logs -f bocchi_bot"
