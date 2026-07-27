#!/bin/bash
set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

WORKDIR="$HOME/bocchi_bot"
REPO_URL="https://github.com/YaroslavGrud/Bocchi-Downloader.git"
BRANCH="Yaroslav_grud"
BOCCHI_UID=1000

echo -e "${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}        🚀 BOCCHI DOWNLOADER — АВТО-УСТАНОВКА         ${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker не установлен.${NC}"
    exit 1
fi

echo -e "\n📁 Подготовка директории..."
rm -rf "$WORKDIR"
mkdir -p "$WORKDIR"
cd "$WORKDIR" || { echo -e "${RED}❌ Не удалось перейти в $WORKDIR${NC}"; exit 1; }

echo -e "\n🔑 Введите токен Telegram бота:"
printf "✏️  Токен: "
read -r TOKEN

echo -e "\n📥 Клонирование репозитория (ветка $BRANCH)..."
git clone --branch "$BRANCH" "$REPO_URL" .

cat > .env <<EOF
TELEGRAM_TOKEN=$TOKEN
BOT_MODE=beta
EOF
echo -e "${GREEN}✅ .env создан (режим beta)${NC}"

echo -e "\n📂 Настройка папки для данных..."
mkdir -p "$WORKDIR/data"
if [ "$EUID" -eq 0 ]; then
    chown -R "$BOCCHI_UID:$BOCCHI_UID" "$WORKDIR/data"
    echo -e "${GREEN}✅ Права на data исправлены.${NC}"
else
    echo -e "${RED}⚠️ Запустите скрипт с sudo для автоматической настройки прав.${NC}"
    printf "Нажмите Enter после исправления прав... "
    read -r
fi

if [ ! -f active_status_msgs.json ]; then
    echo '{}' > active_status_msgs.json
    chmod 666 active_status_msgs.json
    echo -e "${GREEN}✅ active_status_msgs.json создан.${NC}"
fi

echo -e "\n🐳 Сборка Docker-образа..."
docker build -t bocchi_bot .

echo -e "\n🔧 Создание docker-compose.yml с обходом AppArmor..."
cat > docker-compose.yml <<EOF
services:
  bocchi-bot:
    image: bocchi_bot
    container_name: bocchi-bot
    restart: unless-stopped
    volumes:
      - ./data:/app/data
      - ./active_status_msgs.json:/app/active_status_msgs.json
    environment:
      - TELEGRAM_TOKEN=\${TELEGRAM_TOKEN}
      - BOT_MODE=\${BOT_MODE:-stable}
    entrypoint: []
    command: python3 /app/bocchi_bot_host.py
    security_opt:
      - apparmor=unconfined
EOF

echo -e "\n🔄 Очистка старых контейнеров..."
docker stop bocchi-bot 2>/dev/null || true
docker rm bocchi-bot 2>/dev/null || true

echo -e "\n🚀 Запуск контейнера через docker compose..."
docker compose down 2>/dev/null || true
docker compose up -d

echo -e "\n${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              ✅ БОТ УСПЕШНО ЗАПУЩЕН!                 ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}"
echo -e "\n📋 Логи: docker logs -f bocchi-bot"
echo -e "🛑 Остановка: docker stop bocchi-bot"
echo -e "▶️  Запуск: docker start bocchi-bot"
echo -e "💾 Данные на хосте: $WORKDIR/data"
