# 🎸 Bocchi Downloader 🎸
Загрузчик музыки из сервиса "Яндекс.Музыка" в высоком качестве [с поддержкой CLI](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/ReadmeCLI.md)

> [!CAUTION]
> Для загрузки контента применяется токен Яндекс.Музыки вашего аккаунта. \
> Ответственность за его передачу лежит на Вас, а не на авторе проекта.
>
> ![Вас об этом предупредили!](https://img.shields.io/badge/%D0%92%D0%B0%D1%81%20%D0%BE%D0%B1%20%D1%8D%D1%82%D0%BE%D0%BC%20%D0%BF%D1%80%D0%B5%D0%B4%D1%83%D0%BF%D1%80%D0%B5%D0%B4%D0%B8%D0%BB%D0%B8!-red?style=for-the-badge)

> [!NOTE]
> ## Технические неполадки на серверах Яндекса
> Бот функционирует в ограниченном режиме. Некоторые его возможности могут быть недоступны. \
> Сбой вызван техническими проблемами на стороне Яндекса, включая недоступность части серверов
> 
> Upd: Загрузка текстов песен возобновилась. Ожидается восстановление загрузки песен в лучшем качестве. \
> За статусом серверов можно следить только через консоль Yandex Cloud (необходима регистрация)

> [!WARNING]
> ## Разработчик просит Вас не злоупотреблять ресурсами бота
> Нам известно о проблеме, когда бот стремится отправить более 100 или даже 1000 композиций одновременно.
> 
> Мы относимся к каждому пользователю с вниманием и обеспечиваем все необходимые инструменты. Тем не менее, хотим напомнить, что при использовании уязвимостей мы можем ограничить доступ к боту или полностью его прекратить.

> [!TIP]
> Если вы столкнулись с проблемой, сообщите о ней
> 
> [![Сообщить о проблеме](https://img.shields.io/badge/%D0%A1%D0%BE%D0%BE%D0%B1%D1%89%D0%B8%D1%82%D1%8C%20%D0%BE%20%D0%BF%D1%80%D0%BE%D0%B1%D0%BB%D0%B5%D0%BC%D0%B5-%E2%86%92-0969da?style=for-the-badge)](https://github.com/YaroslavGrud/Bocchi-Downloader/issues)

---

## ✨ Возможности проекта

- 🎵 **Загрузка треков** по ссылкам (одиночные треки и альбомы)
- 📝 **Синхронизированный текст** песен в формате LRC (с таймкодами)
- 🏷️ **Богатые метаданные** (исполнитель, альбом, год, жанр)
- 🖼️ **Высококачественные обложки**
- 📊 **Мониторинг состояния** (поддерживается не во всех версиях)
- 🔄 **Обработка альбомов** с автоматическим разбиением на треки
- 🚀 **Очередь загрузок** для стабильной работы

## 📌 Состояние

| Показатель | Бейдж                                                                                                                   |
|------------|-------------------------------------------------------------------------------------------------------------------------|
| Язык       | [![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=fff)](https://www.python.org/)              |
| Лицензия   | [![License: NonCommercial](https://img.shields.io/badge/License-NonCommercial-red?logo=gavel&logoColor=white)](LICENSE) |

## 📊 Дашборд

| Интерфейс                                    | Бейдж                                                                                                     |
|----------------------------------------------|-----------------------------------------------------------------------------------------------------------|
| **Bocchi Dashboard** | [![Bocchi Dashboard](https://img.shields.io/badge/Bocchi_Dashboard-ff69b4)](http://185.170.153.38:61209/) |

## 🐳 Серверная сборка (Docker)

| Компонент      | Бейдж                                                                                                                                                                                        |
|----------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| GitHub Actions | [![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?logo=github-actions&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/actions)                       |
| Docker Hub     | [![Docker Hub](https://img.shields.io/badge/Docker_Hub-0db7ed?logo=docker&logoColor=white)](https://hub.docker.com/r/yaroslavgrud/bocchi-downloader-server-edition)                          |
| Dockerfile     | [![Dockerfile](https://img.shields.io/badge/Dockerfile-2496ED?logo=docker&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/Dockerfile)                 |
| docker-compose | [![docker-compose](https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/docker-compose.yml) |

## 🤖 Версии бота

| Режим      | Бейдж                                                                                                                                                                          |
|------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Бета       | [![Beta bot](https://img.shields.io/badge/bocchi__bot__host.py-бета-orange)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/bocchi_bot_host.py)          |
| Стабильная | [![Stable bot](https://img.shields.io/badge/bocchi__host__full.py-стабильный-success)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/bocchi_host_full.py) |

## 🛠️ Управление и документация

| Скрипт / Инструкция  | Бейдж                                                                                                                                                                                         |
|----------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Shell-инструкция     | [![Shell guide](https://img.shields.io/badge/Shell-инструкция-0078D6?logo=gnu-bash&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/readme_sh.md)       |
| CLI-инструкция       | [![CLI guide](https://img.shields.io/badge/CLI-инструкция-0078D6?logo=gnubash&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/ReadmeCLI.md)            |
| Установка (deploy)   | [![deploy.sh](https://img.shields.io/badge/deploy.sh-установка-116062?logo=gnubash&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/deploy.sh)          |
| Перезапуск (restart) | [![restart.sh](https://img.shields.io/badge/restart.sh-перезапуск-orange?logo=gnubash&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/restart.sh)      |
| Очистка (clean)      | [![clean.sh](https://img.shields.io/badge/docker_clean.sh-очистка-C51A4A?logo=gnubash&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/docker_clean.sh) |

## 📜 Устаревшая часть проекта

> [!NOTE]
> Некоторые разделы переведены в **историческую справку**. Инструкция оставлена для тех, кто запускает старые версии бота.

<details>
<summary><b>Показать устаревшую инструкцию</b></summary>

## 🖥️ Десктопные и мобильные версии

| Платформа           | Бейдж                                                                                                                                                                                                                                     |
|---------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Windows             | [![Windows](https://custom-icon-badges.demolab.com/badge/Windows-0078D6?logo=windows11&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/Bocchi_Downloader/bocchi_bot_windows.py)                    |
| CLI (консоль)       | [![CLI](https://img.shields.io/badge/CLI-4D4D4D?logo=gnubash&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/Bocchi_Downloader/bocchi_bot_CLI.py)                                                  |
| Raspberry Pi        | [![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-C51A4A?logo=raspberrypi&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/Bocchi_Downloader/bocchi_bot_raspberry.py)                    |
| Raspberry Pi Legacy | [![Raspberry Pi Legacy](https://img.shields.io/badge/Raspberry_Pi_Legacy-C51A4A?logo=raspberrypi&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/Bocchi_Downloader/bocchi_Legacy_bot_raspberry.py) |
| Android             | [![Android](https://img.shields.io/badge/Android-3DDC84?logo=android&logoColor=white)](https://github.com/YaroslavGrud/Bocchi-Downloader/blob/Yaroslav_grud/Bocchi_Downloader/bocchi_bot_android.py)                                      |

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
Эта часть проекта может не содержать возможностей предоставленных в серверных решениях бота

```bash
termux-setup-storage && pkg update -y && pkg upgrade -y && pkg install python ffmpeg git binutils wget -y && pip install -U https://github.com/llistochek/yandex-music-downloader/archive/main.zip && python -m venv bocchi_env && bocchi_env/bin/pip install setuptools wheel && bocchi_env/bin/pip install python-telegram-bot[job-queue] catboxpy mutagen requests python-dotenv yandex-music && wget -O bocchi_bot_android.py https://raw.githubusercontent.com/YaroslavGrud/Bocchi-Downloader/Yaroslav_grud/Bocchi_Downloader/bocchi_bot_android.py && read -p "Введите токен Telegram бота: " TOKEN && echo "TELEGRAM_TOKEN=$TOKEN" > .env.example && bocchi_env/bin/python bocchi_bot_android.py
```

Для последующих запусков (после установки)

```bash
bocchi_env/bin/python bocchi_bot_android.py
```
</details>

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

| Команда    | Назначение                                              | Доступность                                                                        |
|------------|---------------------------------------------------------|------------------------------------------------------------------------------------|
| `/start`   | Запуск бота, авторизация, главное меню                  | **Все Telegram-версии** (host_full, host, raspberry, legacy, windows, android)     |
| `/status`  | Состояние сервера (CPU, память, температура, очередь)   | `bocchi_host_full.py`, `bocchi_bot_raspberry.py`, `bocchi_Legacy_bot_raspberry.py` |
| `/logout`  | Удалить сохранённый токен Яндекса                       | **Все Telegram-версии**                                                            |
| `/quality` | Изменить качество загрузки (Низкое / Среднее / Высокое) | `bocchi_host_full.py`, `bocchi_bot_host.py`                                        |
| `/stop`    | Экстренная (жёсткая) остановка всех загрузок            | `bocchi_host_full.py`, `bocchi_bot_host.py`                                        |
| `/menu`    | Показать главное меню с кнопками                        | Все серверные (host_full, host, raspberry), windows, android                       |
| `/cancel`  | Отменить текущий диалог (возврат в меню)                | Все серверные, windows, android                                                    |

> [!NOTE]
> **CLI-версия** (`bocchi_bot_CLI.py`) **не является Telegram-ботом** — это консольное приложение. Управление в нём осуществляется **цифрами** через текстовое меню, а не командами.
>
> В версиях для **Android** и **Windows** отсутствуют команды `/status` и `/quality`.  
> В **Legacy Raspberry Pi** нет `/menu`, `/cancel`, `/quality`, `/stop`.
>
> Все остальные действия (отправка ссылок, обновление токена, отмена загрузки) доступны через **кнопки главного меню** в серверных версиях.

## 🔧 Особенности работы

### Получение метаданных

- **Из API Яндекс.Музыки**: исполнитель, название, длительность
- **Из iTunes**: альбом, год, жанр, обложка высокого разрешения
- **Из загрузчика**: текст песни в формате LRC (с таймкодами)

### Обработка ссылок

- **Одиночные треки** → загружаются как есть
- **Альбомы** → автоматически разбиваются на отдельные треки
- **Плейлисты** → автоматически разбиваются на отдельные треки (Спасибо 🧡[MarshalX](https://github.com/MarshalX))


### Формат вывода

- **Имя файла**: `Исполнитель — Название.расширение`
- **Метаданные**: встроены в аудиофайл (ID3 для MP3, MP4 для M4A)
- **Текст песен**: встроен в теги (USLT для MP3, `©lyr` для M4A) с сохранением таймкодов

### Облачное хранилище
Файлы размером более 49 МБ не могут быть отправлены через Telegram Bot API. В этом случае бот использует:

1. Litterbox – временное хранилище (ссылка действует 24 часа)
2. Catbox – постоянное хранилище (резервный вариант)
3. Сервис [/tmp/files](https://tmpfiles.org) если другие не отвечают

Ссылки приходят в чат и файл можно скачать по ним.

---
> [!NOTE]
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

## 🎧 Из чего собран бот

### 🐍 Основная работа

| Проект | Автор |
|--------|-------|
| [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) | Команда разработчиков проекта представлена в [AUTHORS.rst](https://github.com/python-telegram-bot/python-telegram-bot/blob/master/AUTHORS.rst) проекта |

### 📦 Проекты, без которых нам не обойтись

| Проект | Автор |
|--------|-------|
| [yandex-music-downloader](https://github.com/llistochek/yandex-music-downloader) | 🌿 [llistochek](https://github.com/llistochek) |
| [Yandex Music API](https://github.com/MarshalX/yandex-music-api) | 🧡 [MarshalX](https://github.com/MarshalX) |

### ☁️ Отправка в облако

| Проект | Автор |
|--------|-------|
| [catboxpy](https://github.com/anshonweb/catboxpy) | ☁️ [anshonweb](https://github.com/anshonweb) |
| [/tmp/files](https://tmpfiles.org) | Неизвестен |

### 🖥 Серверные решения

| Проект | Автор |
|--------|-------|
| 💚 [Serv.Host](https://serv.host/) | Команда Serv.Host |
| [Bothost](https://bothost.ru/) (сейчас не используется)| Команда Bothost |
---

## 🏆 Особые благодарности

Здесь мы хотим отдельно отметить людей и компании, чей вклад в проект вышел за рамки обычного «спасибо».

| Кто | За что |
|-----|--------|
| <div align="center"><img src="https://imgproxy.attic.sh/insecure/f:png/plain/https://attic.sh/jv943f5odtpolvryxbw81hut8rqx" width="100" height="100" alt="emoji"><br>Nero</div> | Идею создания бота вдохновила она, первая из тестировщиков. |
| 🧡 [MarshalX](https://github.com/MarshalX) | Создание [Yandex Music API](https://github.com/MarshalX/yandex-music-api) — фундамент, на котором держится вся интеграция с Яндекс.Музыкой |
| 🌿 [llistochek](https://github.com/llistochek) | Создание [yandex-music-downloader](https://github.com/llistochek/yandex-music-downloader) - фундамент, на котором держится загрузка музыки с серверов Яндекс.Музыки |
| 💚 [Serv.Host](https://serv.host/) | Поддержка проекта на всём этапе разработки в качестве площадки для размещения проекта а также предоставленный фирменный мерч |
| 🐋 [Docker](https://www.docker.com/) | Контейнеризация и развёртывание |
| 🛠️ Тестировщики | Участие в тестировании функционала и обратную связь, которая помогала делать бота лучше |
| 🤖 AI-ассистенты | Помощь в отладке кода, исправлении ошибок и рефакторинге проблемных участков проекта |
| ☕ **Вам** | За то, что дочитали эту страницу до конца и, возможно, пользуетесь функциями нашего проекта. Для нас очень важно ваше внимание и участие |

## 📝 Лицензия
Проект распространяется под некоммерческой лицензией. Подробности в файле [LICENSE](LICENSE).
