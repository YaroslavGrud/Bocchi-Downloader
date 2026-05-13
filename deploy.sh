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

# 1. Проверка Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker не установлен. Установите Docker и повторите запуск.${NC}"
    exit 1
fi

# 2. Очистка и подготовка рабочей директории
echo -e "\n📁 Очистка и подготовка рабочей директории..."
rm -rf "$WORKDIR"
mkdir -p "$WORKDIR"
cd "$WORKDIR"

# 3. Запрос токена Telegram (безопасный read -r)
echo -e "\n🔑 Введите токен Telegram бота (можно получить у @BotFather):"
printf "✏️  Токен: "
read -r TOKEN

# 4. Клонирование репозитория
echo -e "\n📥 Клонирование репозитория (ветка $BRANCH)..."
git clone --branch "$BRANCH" "$REPO_URL" .

# 5. Запись .env
echo "TELEGRAM_TOKEN=$TOKEN" > .env
echo -e "${GREEN}✅ Токен сохранён в .env${NC}"

# 6. Проверка наличия Dockerfile в репозитории
if [ ! -f Dockerfile ]; then
    echo -e "${RED}❌ Dockerfile не найден в репозитории!${NC}"
    echo "Ожидается, что Dockerfile есть в корне. Скопируйте его вручную или укажите правильную ветку."
    exit 1
fi

# 7. Создание entrypoint.sh, если его нет в репозитории
if [ ! -f entrypoint.sh ]; then
    echo -e "\n📝 Создаём entrypoint.sh (адаптация под новый Dockerfile)..."
    cat > entrypoint.sh <<'ENTRYPOINT_EOF'
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
ENTRYPOINT_EOF
    chmod +x entrypoint.sh
    echo -e "${GREEN}✅ entrypoint.sh создан${NC}"
else
    echo -e "${GREEN}✅ entrypoint.sh уже есть в репозитории${NC}"
fi

# 8. Сборка образа (используем существующий Dockerfile)
echo -e "\n🐳 Сборка Docker-образа..."
docker build -t bocchi_bot .

# 9. Остановка и удаление старого контейнера
echo -e "\n🔄 Очистка старых контейнеров..."
docker stop bocchi_bot 2>/dev/null || true
docker rm bocchi_bot 2>/dev/null || true

# 10. Запуск нового контейнера (именованный том для данных, не-root пользователь)
echo -e "\n🚀 Запуск контейнера..."
docker run -d \
    --name bocchi_bot \
    --restart unless-stopped \
    --env-file .env \
    -v bocchi_data:/app/data \
    bocchi_bot

# 11. Финальные инструкции
echo -e "\n${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              ✅ БОТ УСПЕШНО ЗАПУЩЕН!                 ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}"
echo -e "\n📋 Просмотр логов: docker logs -f bocchi_bot"
echo -e "🛑 Остановка бота:   docker stop bocchi_bot"
echo -e "▶️  Запуск бота:      docker start bocchi_bot"
echo -e "💾 Данные хранятся в Docker volume: bocchi_data"