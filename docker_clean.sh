# Оставлен для проверки
# Рекомендован под удаление, но должен быть оставлен


#!/bin/bash

# Цвета (опционально)
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${YELLOW}⚠️  ВНИМАНИЕ! Этот скрипт полностью удалит:${NC}"
echo "   • Контейнер bocchi_bot (если существует)"
echo "   • Образ bocchi_bot (если существует)"
echo "   • Папку ~/bocchi_bot со всеми данными (токены, очередь, логи)"
echo ""
read -p "Вы уверены? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}Очистка отменена.${NC}"
    exit 0
fi

echo -e "\n${GREEN}Начинаю очистку...${NC}"

# Остановка контейнера
docker stop bocchi_bot 2>/dev/null && echo "   Контейнер остановлен" || echo "   Контейнер не работал"

# Удаление контейнера
docker rm bocchi_bot 2>/dev/null && echo "   Контейнер удалён" || echo "   Контейнера не существовало"

# Удаление образа
docker rmi bocchi_bot 2>/dev/null && echo "   Образ удалён" || echo "   Образа не существовало"

# Удаление папки проекта
cd ~ && rm -rf ~/bocchi_bot && echo "   Папка ~/bocchi_bot удалена" || echo "   Папка не найдена"

echo -e "\n${GREEN}✅ Полная очистка выполнена!${NC}"

# Комментарий на случай, если что-то пошло не так
echo -e "\n${YELLOW}💡 Если скрипт не сработал или остались артефакты, выполните вручную эту команду:${NC}"
echo "docker stop bocchi_bot 2>/dev/null; docker rm bocchi_bot 2>/dev/null; docker rmi bocchi_bot 2>/dev/null; cd ~ && rm -rf ~/bocchi_bot; echo \"✅ Очистка выполнена.\""
