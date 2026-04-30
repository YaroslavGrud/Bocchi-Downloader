#!/bin/bash
set -e

# ============================================================
#  Единый скрипт развёртывания Bocchi Downloader
#  (исправленная версия с полной очисткой)
# ============================================================

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

WORKDIR=~/bocchi_bot
REPO_URL="https://github.com/YaroslavGrud/Bocchi-Downloader.git"
BRANCH="Yaroslav_grud"

echo -e "${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║        🚀 BOCCHI DOWNLOADER — АВТО-УСТАНОВКА         ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}"

# 1. Проверка наличия Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker не установлен. Установите Docker и повторите запуск.${NC}"
    exit 1
fi

# 2. Полная очистка и подготовка рабочей директории
echo -e "\n📁 Очистка и подготовка рабочей директории..."
rm -rf "$WORKDIR"           # удаляем всё, что накопилось
mkdir -p "$WORKDIR"
cd "$WORKDIR"

# 3. Запрос токена Telegram (в переменную, пока не в файл)
echo -e "\n🔑 Введите токен Telegram бота (можно получить у @BotFather):"
read -p "✏️  Токен: " TOKEN

# 4. Клонирование репозитория (теперь папка гарантированно пуста)
echo -e "\n📥 Клонирование репозитория (ветка $BRANCH)..."
git clone --branch "$BRANCH" "$REPO_URL" .

# 5. Запись .env ПОСЛЕ клонирования
echo "TELEGRAM_TOKEN=$TOKEN" > .env
echo -e "${GREEN}✅ Токен сохранён в .env${NC}"

# 6. Создаём Dockerfile прямо здесь (перезаписываем, если есть)
echo -e "\n🐳 Генерация Dockerfile с вшитым entrypoint..."
cat > Dockerfile <<'DOCKERFILE_EOF'
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN git clone https://github.com/MarshalX/yandex-music-api && \
    cd yandex-music-api && \
    pip install --no-cache-dir . && \
    pip install --no-cache-dir ".[async]" && \
    cd .. && rm -rf yandex-music-api

RUN pip install --no-cache-dir -U https://github.com/llistochek/yandex-music-downloader/archive/main.zip

COPY requirements.txt .
RUN grep -v "yandex-music" requirements.txt | grep -v "yandex-music-downloader" > requirements_clean.txt && \
    pip install --no-cache-dir -r requirements_clean.txt && rm requirements.txt requirements_clean.txt

COPY . .

ENV PYTHONUNBUFFERED=1
RUN mkdir -p /app/data
ENV STATS_FILE=/app/data/stats.txt

RUN echo '#!/bin/bash\n\
cd /app\n\
if [ -f "bocchi_host_full.py" ]; then\n\
    echo "🚀 Запускаем полную версию бота (bocchi_host_full.py)"\n\
    exec python bocchi_host_full.py\n\
elif [ -f "bocchi_bot_host.py" ]; then\n\
    echo "🚀 Запускаем классическую версию бота (bocchi_bot_host.py)"\n\
    exec python bocchi_bot_host.py\n\
else\n\
    echo "❌ Ошибка: не найден ни один файл бота!"\n\
    exit 1\n\
fi' > /entrypoint.sh && chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
DOCKERFILE_EOF

echo -e "${GREEN}✅ Dockerfile создан${NC}"

# 7. Сборка образа
echo -e "\n🐳 Сборка Docker-образа..."
docker build -t bocchi_bot .

# 8. Остановка и удаление старого контейнера
echo -e "\n🔄 Очистка старых контейнеров..."
docker stop bocchi_bot 2>/dev/null || true
docker rm bocchi_bot 2>/dev/null || true

# 9. Запуск нового контейнера
echo -e "\n🚀 Запуск контейнера..."
docker run -d \
    --name bocchi_bot \
    --restart unless-stopped \
    --env-file .env \
    -v "$(pwd)/data:/app/data" \
    bocchi_bot

# 10. Финал
echo -e "\n${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              ✅ БОТ УСПЕШНО ЗАПУЩЕН!                 ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}"
echo -e "\n📋 Просмотр логов: docker logs -f bocchi_bot"
echo -e "🛑 Остановка бота:   docker stop bocchi_bot"
echo -e "▶️  Запуск бота:      docker start bocchi_bot"
