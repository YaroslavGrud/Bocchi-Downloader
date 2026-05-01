# 🎸 Bocchi Downloader 🎸
Загрузчик музыки из сервиса "Яндекс.Музыка" в высоком качестве [с поддержкой CLI](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/ReadmeCLI.md)

> [!CAUTION]
> Ваш токен Яндекс.Музыки может быть [виден на сервере](https://github.com/YaroslavGrud/Bocchi-Downloader/edit/Yaroslav_grud/SECURITY.md)

> [!WARNING]
> 
> Некоторые функции могут работать нестабильно. \
> Если вы столкнулись с проблемой, [сообщите о ней](https://github.com/YaroslavGrud/Bocchi-Downloader/issues) 

Спасибо за ваше терпение и помощь в улучшении проекта!

## 📌 Состояние проекта


| Показатель | Бейдж |
|------------|-------|
| Язык | [![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=fff)](https://www.python.org/) |
| Лицензия | [![License: NonCommercial](https://img.shields.io/badge/License-NonCommercial-red?logo=gavel&logoColor=white)](LICENSE) |

## 🐳 Серверная сборка (Docker)

| Компонент | Бейдж |
|-----------|-------|
| GitHub Actions | [![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?logo=github-actions&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/actions) |
| Docker Hub | [![Docker Hub](https://img.shields.io/badge/Docker_Hub-0db7ed?logo=docker&logoColor=white)](https://hub.docker.com/r/yaroslavgrud/bocchi-downloader-server-edition) |
| Dockerfile | [![Dockerfile](https://img.shields.io/badge/Dockerfile-2496ED?logo=docker&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/Dockerfile) |
| docker-compose | [![docker-compose](https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/docker-compose.yml) |

## 🤖 Версии бота

| Режим | Бейдж |
|-------|-------|
| Стабильная | [![Stable bot](https://img.shields.io/badge/bocchi__bot__host.py-стабильный-success)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/bocchi_bot_host.py) |
| Бета | [![Beta bot](https://img.shields.io/badge/bocchi__host__full.py-бета-orange)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/bocchi_host_full.py) |

## 🖥️ Десктопные и мобильные версии

| Платформа | Бейдж |
|-----------|-------|
| Windows | [![Windows](https://custom-icon-badges.demolab.com/badge/Windows-0078D6?logo=windows11&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/Bocchi_Downloader/bocchi_bot_windows.py) |
| CLI (консоль) | [![CLI](https://img.shields.io/badge/CLI-4D4D4D?logo=gnubash&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/Bocchi_Downloader/bocchi_bot_CLI.py) |
| Raspberry Pi | [![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-C51A4A?logo=raspberrypi&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/Bocchi_Downloader/bocchi_bot_raspberry.py) |
| Raspberry Pi Legacy | [![Raspberry Pi Legacy](https://img.shields.io/badge/Raspberry_Pi_Legacy-C51A4A?logo=raspberrypi&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/Bocchi_Downloader/bocchi_Legacy_bot_raspberry.py)
| Android | [![Android](https://img.shields.io/badge/Android-3DDC84?logo=android&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/Bocchi_Downloader/bocchi_bot_android.py) |

## 🛠️ Управление и документация

| Скрипт / Инструкция | Бейдж |
|----------------------|-------|
| Shell-инструкция | [![Shell guide](https://img.shields.io/badge/Shell-инструкция-0078D6?logo=gnu-bash&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/readme_sh.md) |
| CLI-инструкция | [![CLI guide](https://img.shields.io/badge/CLI-инструкция-0078D6?logo=gnubash&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/ReadmeCLI.md) |
| Установка (deploy) | [![deploy.sh](https://img.shields.io/badge/deploy.sh-установка-116062?logo=gnubash&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/deploy.sh) |
| Перезапуск (restart) | [![restart.sh](https://img.shields.io/badge/restart.sh-перезапуск-orange?logo=gnubash&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/restart.sh) |
| Очистка (clean) | [![clean.sh](https://img.shields.io/badge/docker_clean.sh-очистка-C51A4A?logo=gnubash&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/docker_clean.sh) |
## ✨ Возможности

- 🎵 **Загрузка треков** по ссылкам (одиночные треки и альбомы)
- 📝 **Синхронизированный текст** песен в формате LRC (с таймкодами)
- 🏷️ **Богатые метаданные** (исполнитель, альбом, год, жанр)
- 🖼️ **Высококачественные обложки**
- ⏱️ **Корректная длительность** треков в Telegram
- 📊 **Мониторинг состояния** (поддерживается не во всех версиях)
- 🔄 **Обработка альбомов** с автоматическим разбиением на треки
- 🚀 **Очередь загрузок** для стабильной работы
- 🛡️ **Защита от ошибок** и таймаутов

## 📋 Требования

- Установленный [Python](https://www.python.org/)
- Установленный [yandex-music-downloader](https://github.com/llistochek/yandex-music-downloader)
- Обновлённый [API от MarshalX](https://github.com/MarshalX/yandex-music-api)
- Токен Telegram бота который нужно получить у [@BotFather](https://t.me/BotFather)

## 🚀 Установка

### Установка внешнего загрузчика

```bash
pip install -U https://github.com/llistochek/yandex-music-downloader/archive/main.zip
yandex-music-downloader --help
```
### Обновлённый API (MarshalX)

```bash
git clone https://github.com/MarshalX/yandex-music-api
cd yandex-music-api
pip install .          # синхронный клиент
pip install ".[async]" # с поддержкой асинхронного клиента
```

## 🤖 Установка бота под Android

> [!WARNING]
> 
> Эта часть проекта может не содержать возможностей предоставленных в серверных решениях бота

```bash
termux-setup-storage && pkg update -y && pkg upgrade -y && pkg install python ffmpeg git binutils wget -y && pip install -U https://github.com/llistochek/yandex-music-downloader/archive/main.zip && python -m venv bocchi_env && bocchi_env/bin/pip install setuptools wheel && bocchi_env/bin/pip install python-telegram-bot[job-queue] catboxpy mutagen requests python-dotenv yandex-music && wget -O bocchi_bot_android.py https://raw.githubusercontent.com/YaroslavGrud/Bocchi-Downloader/Yaroslav_grud/Bocchi_Downloader/bocchi_bot_android.py && read -p "Введите токен Telegram бота: " TOKEN && echo "TELEGRAM_TOKEN=$TOKEN" > .env.example && bocchi_env/bin/python bocchi_bot_android.py
```

Для последующих запусков (после установки)

```bash
bocchi_env/bin/python bocchi_bot_android.py
```

## 🎮 Использование

1. Начните диалог с ботом командой `/start`
2. Нажмите кнопку «🎵 Начать работу»
3. Авторизуйтесь через Яндекс.Музыку (бот пришлёт ссылку для получения токена)
4. Отправляйте ссылки на треки, альбомы или плейлисты

### Примеры ссылок

- **Трек**: `https://music.yandex.ru/track/12345678`
- **Альбом**: `https://music.yandex.ru/album/87654321`
- **Плейлист**: `https://music.yandex.ru/playlists/123`

## 📊 Команды бота

> [!TIP]
> Основные команды расположены в `main_menu_keyboard` \
> Ниже представлена таблица практически для всех версий


| Команда | Описание |
|---------|----------|
| `/start` | Начать диалог с ботом |
| `/status` | Показать состояние сервера (CPU, память, температура, очередь загрузок) |
| `/logout` | Удалить сохранённый токен и выйти из аккаунта |



## 🔧 Особенности работы

### Получение метаданных

- **Из API Яндекс.Музыки**: исполнитель, название, длительность
- **Из iTunes**: альбом, год, жанр, обложка высокого разрешения
- **Из загрузчика**: текст песни в формате LRC (с таймкодами)

### Обработка ссылок

- **Одиночные треки** → загружаются как есть
- **Альбомы** → автоматически разбиваются на отдельные треки
- **Плейлисты** → автоматически разбиваются на отдельные треки (Спасибо [MarshalX](https://github.com/MarshalX))


### Формат вывода

- **Имя файла**: `Исполнитель — Название.расширение`
- **Метаданные**: встроены в аудиофайл (ID3 для MP3, MP4 для M4A)
- **Текст песен**: встроен в теги (USLT для MP3, `©lyr` для M4A) с сохранением таймкодов

### Облачное хранилище
Файлы размером более 49 МБ не могут быть отправлены через Telegram Bot API. В этом случае бот использует:

1. Litterbox – временное хранилище (ссылка действует 24 часа)
2. Catbox – постоянное хранилище (резервный вариант)

Ссылки приходят в чат и файл можно скачать по ним.

---
> [!IMPORTANT]
> ### Бот не отвечает
> - Проверьте, что токен Telegram корректен
> - Убедитесь, что бот запущен и не упал с ошибкой
> ### Ошибка авторизации в Яндекс.Музыке
> - Перевыпустите токен по ссылке авторизации
> - Убедитесь, что токен начинается с `y0_`
> ### Не скачиваются треки
> - Проверьте путь к `yandex-music-downloader`
> - Убедитесь, что у загрузчика есть права на выполнение
> - Проверьте интернет-соединение
> ### Нет текста песни
> - Убедитесь, что для трека есть текст на Яндекс.Музыке
> - Проверьте, что загрузчик запускается с параметром `--lyrics-format lrc`
---

## 📝 Лицензия
Проект распространяется под некоммерческой лицензией. Подробности в файле [LICENSE](LICENSE).

## 🙏 Благодарности
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) — мощная библиотека для Telegram ботов

### Основная работа
- [yandex-music-downloader](https://github.com/llistochek/yandex-music-downloader) — основной загрузчик Яндекс.Музыки
- [MarshalX](https://github.com/MarshalX) - обновлённый API и поддержка плейлистов

### Отправка в облако
- [catboxpy](https://github.com/anshonweb/catboxpy) — обёртка для Catbox/Litterbox

### Серверные решения
- [Bothost](https://bothost.ru/)
- [Serv.Host](https://serv.host/)

### Особые благодарности
- Человеку, что подал идею создать бота (спасибо Yume)
---

⭐ **Если вам понравился проект, поставьте звезду на GitHub!**
