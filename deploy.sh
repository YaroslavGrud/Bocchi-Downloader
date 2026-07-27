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

# Проверка Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker не установлен.${NC}"
    exit 1
fi

# Подготовка директории
echo -e "\n📁 Подготовка директории..."
rm -rf "$WORKDIR"
mkdir -p "$WORKDIR"
cd "$WORKDIR" || { echo -e "${RED}❌ Не удалось перейти в $WORKDIR${NC}"; exit 1; }

# Запрос токена
echo -e "\n🔑 Введите токен Telegram бота:"
printf "✏️  Токен: "
read -r TOKEN

# Клонирование репозитория
echo -e "\n📥 Клонирование репозитория (ветка $BRANCH)..."
git clone --branch "$BRANCH" "$REPO_URL" .

# Создание .env
cat > .env <<EOF
TELEGRAM_TOKEN=$TOKEN
BOT_MODE=beta
EOF
echo -e "${GREEN}✅ .env создан (режим beta)${NC}"

# Настройка папки data
echo -e "\n📂 Настройка папки для данных..."
mkdir -p "$WORKDIR/data"
if [ "$EUID" -eq 0 ]; then
    chown -R "$BOCCHI_UID:$BOCCHI_UID" "$WORKDIR/data"
    echo -e "${GREEN}✅ Права на data исправлены.${NC}"
else
    echo -e "${RED}⚠️ Запустите скрипт с sudo для автоматической настройки прав,${NC}"
    echo "   либо выполните: sudo chown -R $BOCCHI_UID:$BOCCHI_UID $WORKDIR/data"
    printf "Нажмите Enter после исправления прав... "
    read -r
fi

# Создание файла active_status_msgs.json
if [ ! -f active_status_msgs.json ]; then
    echo '{}' > active_status_msgs.json
    chmod 666 active_status_msgs.json
    echo -e "${GREEN}✅ active_status_msgs.json создан.${NC}"
fi

# Сборка Docker-образа
echo -e "\n🐳 Сборка Docker-образа..."
docker build -t bocchi_bot .

# Настройка docker-compose.yml для использования локального образа
if [ -f docker-compose.yml ]; then
    echo -e "\n🔧 Настройка docker-compose.yml для локального образа..."
    sed -i 's|image: yaroslavgrud/bocchi-downloader-server-edition:latest|image: bocchi_bot|g' docker-compose.yml
    echo -e "${GREEN}✅ docker-compose.yml обновлён.${NC}"
else
    echo -e "${RED}⚠️ docker-compose.yml не найден, пропускаем.${NC}"
fi

# Остановка старых контейнеров
echo -e "\n🔄 Очистка старых контейнеров..."
docker stop bocchi_bot 2>/dev/null || true
docker rm bocchi_bot 2>/dev/null || true

# Запуск через docker compose
echo -e "\n🚀 Запуск контейнера через docker compose..."
docker compose down 2>/dev/null || true
docker compose up -d

# Финальное сообщение
echo -e "\n${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              ✅ БОТ УСПЕШНО ЗАПУЩЕН!                 ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}"
echo -e "\n📋 Логи: docker logs -f bocchi_bot"
echo -e "🛑 Остановка: docker stop bocchi_bot"
echo -e "▶️  Запуск: docker start bocchi_bot"
echo -e "💾 Данные на хосте: $WORKDIR/data"
echo -e "\n🔁 Для переключения версий используйте:"
echo -e "   • Стабильная: curl -fsSL https://raw.githubusercontent.com/YaroslavGrud/Bocchi-Downloader/Yaroslav_grud/switch_to_stable.sh | bash"
echo -e "   • Бета:       curl -fsSL https://raw.githubusercontent.com/YaroslavGrud/Bocchi-Downloader/Yaroslav_grud/switch_to_beta.sh | bash"
