#!/bin/bash
set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

WORKDIR="$HOME/bocchi_bot"
REPO_URL="https://github.com/YaroslavGrud/Bocchi-Downloader.git"
BRANCH="Yaroslav_grud"

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
BOCCHI_UID=1000

CURRENT_OWNER=$(stat -c "%u" "$WORKDIR/data" 2>/dev/null || echo "")
if [ "$CURRENT_OWNER" != "$BOCCHI_UID" ]; then
    if [ "$EUID" -eq 0 ]; then
        chown -R "$BOCCHI_UID:$BOCCHI_UID" "$WORKDIR/data"
        echo -e "${GREEN}✅ Права на data исправлены.${NC}"
    else
        echo -e "${RED}⚠️ Запустите скрипт с sudo для автоматической настройки прав,${NC}"
        echo "   либо выполните: sudo chown -R $BOCCHI_UID:$BOCCHI_UID $WORKDIR/data"
        printf "Нажмите Enter после исправления прав... "
        read -r
    fi
fi

echo -e "\n🐳 Сборка Docker-образа..."
docker build -t bocchi_bot .

echo -e "\n🔄 Очистка старых контейнеров..."
docker stop bocchi_bot 2>/dev/null || true
docker rm bocchi_bot 2>/dev/null || true

echo -e "\n🚀 Запуск контейнера..."
docker run -d \
    --name bocchi_bot \
    --restart unless-stopped \
    --user "$BOCCHI_UID:$BOCCHI_UID" \
    --env-file .env \
    -v "$WORKDIR/data:/app/data" \
    --tmpfs /tmp \
    --tmpfs /var/tmp \
    --security-opt no-new-privileges:true \
    bocchi_bot
# Флаг --read-only удалён

echo -e "\n${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              ✅ БОТ УСПЕШНО ЗАПУЩЕН!                 ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}"
echo -e "\n📋 Логи: docker logs -f bocchi_bot"
echo -e "🛑 Остановка: docker stop bocchi_bot"
echo -e "▶️  Запуск: docker start bocchi_bot"
echo -e "💾 Данные на хосте: $WORKDIR/data"