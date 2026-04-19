# 🎸 Bocchi Downloader
Загрузчик музыки из сервиса "Яндекс.Музыка" в высоком качестве [с поддержкой CLI](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/ReadmeCLI.md)

> [!WARNING]
> 
> Некоторые функции могут работать нестабильно, возможны ошибки. Если вы столкнулись с проблемой, пожалуйста, сообщите о ней в [Issues](https://github.com/YaroslavGrud/Bocchi-Downloader/issues). Спасибо за ваше терпение и помощь в улучшении проекта!
> 
> Бот может потребовать наличие Telegram Premium разработчика для работы некоторых функций
>
> Основная разработка идёт в `bocchi_bot_host.py`.
> 
> Остальные версии проекта оставлены в качестве ознакомления


[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Supported-2496ED?logo=docker&logoColor=white)](https://hub.docker.com/)


## ✨ Возможности

- 🎵 **Загрузка треков** по ссылкам (одиночные треки и альбомы)
- 📝 **Синхронизированный текст** песен в формате LRC (с таймкодами)
- 🏷️ **Богатые метаданные** из API Яндекс.Музыки и iTunes (исполнитель, альбом, год, жанр)
- 🖼️ **Высококачественные обложки** (до 1000×1000)
- ⏱️ **Корректная длительность** треков в Telegram
- 📊 **Мониторинг состояния** для Raspberry Pi (температура, загрузка, очередь)
- 🔄 **Обработка альбомов** с автоматическим разбиением на треки
- 🚀 **Очередь загрузок** для стабильной работы
- 🛡️ **Защита от ошибок** и таймаутов

## 📋 Требования

- Python 3.8 или выше
- Установленный [yandex-music-downloader](https://github.com/llistochek/yandex-music-downloader)
- Токен Telegram бота (получить у [@BotFather](https://t.me/BotFather))

## 🚀 Установка

### 1. Клонирование репозитория

```bash
git clone https://github.com/YaroslavGrud/Bocchi-Downloader.git
cd Bocchi-Downloader
```

### 2. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 3. Установка внешнего загрузчика

```bash
pip install -U https://github.com/llistochek/yandex-music-downloader/archive/main.zip
yandex-music-downloader --help
```
### 4. Обновление API (MarshalX)

```bash
git clone https://github.com/MarshalX/yandex-music-api
cd yandex-music-api
pip install .          # синхронный клиент
pip install ".[async]" # с поддержкой асинхронного клиента
```

## 🤖 Установка под Android
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

## 📊 Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Начать диалог с ботом |
| `/status` | Показать состояние сервера (CPU, память, температура, очередь загрузок) |
| `/logout` | Удалить сохранённый токен и выйти из аккаунта |

Остальные команды расположены в `main_menu_keyboard`

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
Проект распространяется под лицензией MIT. Подробности в файле [LICENSE](LICENSE).
## 🙏 Благодарности
- [yandex-music-downloader](https://github.com/llistochek/yandex-music-downloader) — загрузчик для Яндекс.Музыки (оставлен для совместимости)
- [MarshalX](https://github.com/MarshalX) - обновлённый API и поддержка плейлистов
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) — мощная библиотека для Telegram ботов
- [catboxpy](https://github.com/anshonweb/catboxpy) — обёртка для Catbox/Litterbox
- [Bothost](https://bothost.ru/) в предоставлении хостинг услуг
- Человеку, что подал идею создать бота (спасибо Yume)
---

⭐ **Если вам понравился проект, поставьте звезду на GitHub!**
