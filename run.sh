#!/bin/bash
set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║            🚀 BOCCHI DOWNLOADER — ЗАПУСК              ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}"

# 1. Подготовка директории
echo -e "\n📁 Подготовка рабочей директории..."
mkdir -p ~/bocchi_bot && cd ~/bocchi_bot

# 2. Запрос токена Telegram
echo -e "\n🔑 Введите токен Telegram бота (можно получить у @BotFather):"
read -p "✏️  Токен: " TOKEN
echo "TELEGRAM_TOKEN=$TOKEN" > .env
echo -e "${GREEN}✅ Токен сохранён в .env${NC}"

# 3. Клонирование репозитория
echo -e "\n📥 Клонирование репозитория..."
if [ ! -d "Bocchi-Downloader" ]; then
    git clone --branch Yaroslav_grud https://github.com/YaroslavGrud/Bocchi-Downloader.git .
else
    echo "Репозиторий уже существует, выполняю git pull..."
    git pull origin Yaroslav_grud
fi

# 4. Сборка Docker-образа
echo -e "\n🐳 Сборка Docker-образа (это займёт несколько минут)..."
docker build -t bocchi_bot .

# 5. Остановка и удаление старого контейнера (если есть)
echo -e "\n🔄 Проверка и очистка старых контейнеров..."
docker stop bocchi_bot 2>/dev/null || true
docker rm bocchi_bot 2>/dev/null || true

# 6. Запуск нового контейнера
echo -e "\n🚀 Запуск контейнера..."
docker run -d \
    --name bocchi_bot \
    --restart unless-stopped \
    --env-file .env \
    -v $(pwd)/data:/app/data \
    bocchi_bot

# 7. Финальный вывод
echo -e "\n${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              ✅ БОТ УСПЕШНО ЗАПУЩЕН!                 ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}"
echo -e "\n📋 Просмотр логов: docker logs -f bocchi_bot"
echo -e "🛑 Остановка бота:   docker stop bocchi_bot"
echo -e "▶️  Запуск бота:      docker start bocchi_bot"
