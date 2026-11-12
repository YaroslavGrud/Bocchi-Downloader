# 🎸 Bocchi Downloader 🎸



Консольный и Telegram-загрузчик музыки из **«Яндекс.Музыки»** в максимальном качестве. Написан на Python, умеет держать очередь, расставлять теги, резать альбомы на треки и выгружать тяжелые файлы в облако. **🥁 Нидзика** говорит, что без нормальной автоматизации группа далеко не уедет, так что всё работает стабильно!

> [!CAUTION]
> **Ваш токен Яндекс.Музыки используется на ваш страх и риск**  
>
>> *«Эй, следи за своими секретами! Я не собираюсь отвечать, если ты сам их разболтал».* — **⚒️ Автор проекта (StalkerBocchi)**
>
> Ответственность за передачу токена аккаунта лежит **исключительно на Вас**, а не на авторе проекта.
>
> ![Вас об этом предупредили!](https://img.shields.io/badge/%D0%92%D0%B0%D1%81%20%D0%BE%D0%B1%20%D1%8D%D1%82%D0%BE%D0%BC%20%D0%BF%D1%80%D0%B5%D0%B4%D1%83%D0%BF%D1%80%D0%B5%D0%B4%D0%B8%D0%BB%D0%B8!-red?style=for-the-badge)

> [!WARNING]
> **Не злоупотребляйте ресурсами сервера!**
>> *«У-у-уа-а! Слишком много ссылок... Если бот упадет от перегрузки, я закроюсь в коморке и никогда больше не возьму в руки гитару!»* — **🎸 Хитори Гото**
> Если вы решите запустить скачивание сразу тысячи треков, бот захлебнется, а железо сгорит (у нас нет бюджета на новый сервер). За попытки положить бота или абьюзить уязвимости — моментальный бан без права на амнистию.

> [!TIP]
> **✨ Кита-аура поддержки! `(ﾉ◕ヮ◕)ﾉ*:･ﾟ✧`**
>
> Если вы столкнулись с проблемой, багом или у вас есть крутая идея — не стесняйтесь, сообщите о ней! Мы обязательно всё посмотрим!
>
>[![🎸 Починить аппаратуру→](https://img.shields.io/badge/🎸_Починить_бота-F4A5B0?style=for-the-badge&labelColor=2b2d42&color=B4698C)](https://github.com/StalkerBocchi/Bocchi-Downloader/issues)
> [![💡 Предложить идею](https://img.shields.io/badge/💡_Предложить_идею-2b2d42?style=for-the-badge&labelColor=2b2d42)](https://github.com/StalkerBocchi/Bocchi-Downloader/issues/new)

> [!TIP]
> **Поддержать автора** 🤝
> 
>> *«Я сказала Боччи, что если мы не соберем на поддержку проекта, ей придется идти работать в кафе. Спасите её от общения с незнакомцами — задонатьте!»* — **🪙 Рё Ямада**
> 
> [![💸 Поддержать проект](https://img.shields.io/badge/💸_Поддержать_проект-375B9D?style=for-the-badge&labelColor=2b2d42&color=375B9D)](https://pay.cloudtips.ru/p/26816273)
> 
> **Все донаты идут на оплату хостинга и спасение Боччи от социофобии.**
---
## 📋 Требования (Чек-лист перед выходом на сцену STARRY)

> *«Так, девочки, проверяем аппаратуру! Без этого мы даже не настроим гитары, не то что концерт отыграем! (ง •̀_•́)ง»* — **Нидзика Идзити**

| Компонент / Инструмент | Ссылка | Комментарий от участниц Kessoku Band |
| :--- | :--- | :--- |
| 🐍 **Интерпретатор** | [![Python](https://img.shields.io/badge/-Python-ff69b4?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)| «Б-базовая база... Без него всё сразу рухнет, и я уползу в свою коробку от стыда... — **🎸 Боччи** |
| ⬇️ **Внешний загрузчик** | [![yandex-music-downloader](https://img.shields.io/badge/-yandex--music--downloader-375B9D?style=flat-square&logo=github&logoColor=white&labelColor=2b2d42)](https://github.com/llistochek/yandex-music-downloader)| «Главный усилитель! Именно он вытягивает треки с серверов на максимальной громкости! — **✨  Кита** |
| 🔌 **Обновлённый API** | [![API от MarshalX](https://img.shields.io/badge/-API_MarshalX-375B9D?style=flat-square&logo=github&logoColor=white&labelColor=2b2d42)](https://github.com/MarshalX/yandex-music-api)| *«Мост для связи с Яндекс.Музыкой. И главное — полностью бесплатный, бюджет группы не пострадает (￣▽￣)»* — **🪙 Рё** |
| 🤖 **Токен Telegram-бота** | [![@BotFather](https://img.shields.io/badge/-@BotFather-229ED9?style=flat-square&logo=telegram&logoColor=white&labelColor=2b2d42)](https://t.me/BotFather) | *«Пропуск за кулисы! Получите его у Отца Ботов, чтобы наш скрипт вообще ожил и начал отвечать! ♪(´▽｀)»* — **🥁 Нидзика** |

## ✨ Возможности проекта `(☆▽☆)`


> «Смотрите, сколько всего он умеет! И обложки красивые ставит, и тексты для караоке добавляет — прямо как на нашем концерте в STARRY!» — **✨ Икуё Кита**

| Функция | Что делает (в стиле *Kessoku Band*) |
| :--- | :--- |
| 🎵 **Загрузка треков** | Скачивает музыку по ссылкам (одиночные треки, альбомы и целые плейлисты) `♪(´▽｀)` |
| 📝 **Синхронизированный текст** | Вшивает тексты песен в формате `.lrc` с таймкодами — можно подпевать как Кита-чан! |
| 🏷️ **Богатые метаданные** | Аккуратно прописывает теги (исполнитель, альбом, год, жанр) — Нидзика любит порядок |
| 🖼️ **Высококачественные обложки** | Достаёт обложки в максимальном разрешении, чтобы в плеере всё сияло |
| 📊 **Мониторинг состояния** | Следит за пульсом сервера *(поддерживается не во всех версиях, чтобы Боччи меньше нервничала)* |
| 🔄 **Обработка альбомов** | Автоматически нарезает длинные альбомы и плейлисты на отдельные треки |
| 🚀 **Очередь загрузок** | Выстраивает запросы в ровную шеренгу для стабильной работы без падений |

---

## 📌 Состояние и 📊 Дашборд

| Категория | Показатель | Бейдж / Ссылка |
| :--- | :--- | :--- |
| 💻 **Разработка** | Язык проекта | [![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=fff)](https://www.python.org/) |
| 📈 **Мониторинг** | **Bocchi Dashboard** | [![Bocchi Dashboard](https://img.shields.io/badge/Bocchi_Dashboard-ff69b4)](http://185.170.153.38:61209/) |
| ⚖️ **Права** | Лицензия | [![License: NonCommercial](https://img.shields.io/badge/License-NonCommercial-red?logo=gavel&logoColor=white)](LICENSE) |
---

## 🐳 Серверная сборка `(¬_¬ )`

> «Изолировать всё в контейнеры, чтобы оно крутилось само по себе и не требовало лишних вложений... Эффективно. Сэкономленные деньги пойдут на новую бас-гитару и обед». — **🪙 Рё Ямада**

| Компонент | Бейдж | Назначение |
| :--- | :--- | :--- |
| **GitHub Actions** | [![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?logo=github-actions&logoColor=white)](https://github.com/StalkerBocchi/Bocchi-Downloader/actions) | Автоматическая сборка и CI/CD пайплайны |
| **Docker Hub** | [![Docker Hub](https://img.shields.io/badge/Docker_Hub-0db7ed?logo=docker&logoColor=white)](https://hub.docker.com/r/yaroslavgrud/bocchi-downloader-server-edition) | Готовый серверный образ контейнера |
| **Dockerfile** | [![Dockerfile](https://img.shields.io/badge/Dockerfile-2496ED?logo=docker&logoColor=white)](https://github.com/StalkerBocchi/Bocchi-Downloader/blob/Yaroslav_grud/Dockerfile) | Инструкция сборки окружения |
| **docker-compose** | [![docker-compose](https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white)](https://github.com/StalkerBocchi/Bocchi-Downloader/blob/Yaroslav_grud/docker-compose.yml) | Быстрый запуск одной командой |

---

## 🤖 Версии бота

| Режим | Бейдж | Характер сборки |
| :--- | :--- | :--- |
| 🧪 **Бета** | [![Beta bot](https://img.shields.io/badge/bocchi__bot__host.py-бета-orange)](https://github.com/StalkerBocchi/Bocchi-Downloader/blob/Yaroslav_grud/bocchi_bot_host.py) | Экспериментальная версия: новые фичи появляются тут первыми, но иногда может занервничать как Боччи перед соло `(＞﹏＜)` |
| ⭐ **Стабильная** | [![Stable bot](https://img.shields.io/badge/bocchi__host__full.py-стабильный-success)](https://github.com/StalkerBocchi/Bocchi-Downloader/blob/Yaroslav_grud/bocchi_host_full.py) | Надёжная как ритм-секция Нидзики. Рекомендуется для повседневного использования `٩(◕‿◕｡)۶` |

---

## 🛠️ Управление и документация `( •̀ ω •́ )✧`

> «Я расписала все скрипты и инструкции по полочкам! Если нужно развернуть, перезапустить или прибраться на сервере — просто жмите нужную кнопку и не устраивайте бардак!» — **🥁 Нидзика Идзити**

| Скрипт / Инструкция | Бейдж | Описание |
| :--- | :--- | :--- |
| **Shell-инструкция** | [![Shell guide](https://img.shields.io/badge/Shell-инструкция-0078D6?logo=gnu-bash&logoColor=white)](https://github.com/StalkerBocchi/Bocchi-Downloader/blob/Yaroslav_grud/readme_sh.md) | Гайд по работе со скриптами оболочки |
| **CLI-инструкция** | [![CLI guide](https://img.shields.io/badge/CLI-инструкция-0078D6?logo=gnubash&logoColor=white)](https://github.com/StalkerBocchi/Bocchi-Downloader/blob/Yaroslav_grud/ReadmeCLI.md) | Руководство по консольному режиму |
| **Установка (`deploy`)** | [![deploy.sh](https://img.shields.io/badge/deploy.sh-установка-116062?logo=gnubash&logoColor=white)](https://github.com/StalkerBocchi/Bocchi-Downloader/blob/Yaroslav_grud/deploy.sh) | Автоматическое развёртывание на сервере |
| **Перезапуск (`restart`)** | [![restart.sh](https://img.shields.io/badge/restart.sh-перезапуск-orange?logo=gnubash&logoColor=white)](https://github.com/StalkerBocchi/Bocchi-Downloader/blob/Yaroslav_grud/restart.sh) | Мягкий рестарт контейнеров/бота |
| **Очистка (`clean`)** | [![clean.sh](https://img.shields.io/badge/docker_clean.sh-очистка-C51A4A?logo=gnubash&logoColor=white)](https://github.com/StalkerBocchi/Bocchi-Downloader/blob/Yaroslav_grud/docker_clean.sh) | Генеральная уборка кэша и старых образов |

---

## 📜 Устаревшая часть проекта 

> [!NOTE]
> *«Эти старые скрипты как мои первые записи на видеохостинге в костюме из коробки от спелых манго... Немного неловко, но вдруг кому-то ещё пригодятся! `(*/_＼)`»* — **🎸 Хитори Гото (Боччи)**

<details>
<summary><b>📂 Показать устаревшую инструкцию и локальные версии (Нажмите, чтобы заглянуть в коробку)</b></summary>

### 🖥️ Десктопные и мобильные версии

| Платформа | Бейдж |
| :--- | :--- |
| **Windows** | [![Windows](https://custom-icon-badges.demolab.com/badge/Windows-0078D6?logo=windows11&logoColor=white)](https://github.com/StalkerBocchi/Bocchi-Downloader/blob/Yaroslav_grud/Bocchi_Downloader/bocchi_bot_windows.py) |
| **CLI (консоль)** | [![CLI](https://img.shields.io/badge/CLI-4D4D4D?logo=gnubash&logoColor=white)](https://github.com/StalkerBocchi/Bocchi-Downloader/blob/Yaroslav_grud/Bocchi_Downloader/bocchi_bot_CLI.py) |
| **Raspberry Pi** | [![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-C51A4A?logo=raspberrypi&logoColor=white)](https://github.com/StalkerBocchi/Bocchi-Downloader/blob/Yaroslav_grud/Bocchi_Downloader/bocchi_bot_raspberry.py) |
| **Raspberry Pi Legacy** | [![Raspberry Pi Legacy](https://img.shields.io/badge/Raspberry_Pi_Legacy-C51A4A?logo=raspberrypi&logoColor=white)](https://github.com/StalkerBocchi/Bocchi-Downloader/blob/Yaroslav_grud/Bocchi_Downloader/bocchi_Legacy_bot_raspberry.py) |
| **Android** | [![Android](https://img.shields.io/badge/Android-3DDC84?logo=android&logoColor=white)](https://github.com/StalkerBocchi/Bocchi-Downloader/blob/Yaroslav_grud/Bocchi_Downloader/bocchi_bot_android.py) |

### 🚀 Установка вручную

#### 1. Установка внешнего загрузчика

```bash
pip install -U https://github.com/llistochek/yandex-music-downloader/archive/main.zip
yandex-music-downloader --help
```

#### 2. Обновлённый API (MarshalX)

```bash
git clone https://github.com/MarshalX/yandex-music-api
cd yandex-music-api
pip install .          # синхронный клиент
pip install ".[async]" # с поддержкой асинхронного клиента
```

### 🤖 Установка бота под Android (Termux)

*Эта часть проекта может не содержать всех возможностей, представленных в серверных решениях бота.*

```bash
termux-setup-storage && pkg update -y && pkg upgrade -y && pkg install python ffmpeg git binutils wget -y && pip install -U https://github.com/llistochek/yandex-music-downloader/archive/main.zip && python -m venv bocchi_env && bocchi_env/bin/pip install setuptools wheel && bocchi_env/bin/pip install python-telegram-bot[job-queue] catboxpy mutagen requests python-dotenv yandex-music && wget -O bocchi_bot_android.py https://raw.githubusercontent.com/StalkerBocchi/Bocchi-Downloader/Yaroslav_grud/Bocchi_Downloader/bocchi_bot_android.py && read -p "Введите токен Telegram бота: " TOKEN && echo "TELEGRAM_TOKEN=$TOKEN" > .env.example && bocchi_env/bin/python bocchi_bot_android.py
```

Для последующих запусков (после установки):

```bash
bocchi_env/bin/python bocchi_bot_android.py
```

</details>

---

## 🎮 Использование

> *«Всё проще простого! Даже если вы боитесь разговаривать с людьми, с ботом общаться совсем не страшно... Наверное...»* — **🎸 Боччи**

1. Начните диалог с ботом командой `/start`
2. Нажмите кнопку **«🎵 Начать работу»**
3. Авторизуйтесь через Яндекс.Музыку (бот пришлёт ссылку для получения токена)
4. Отправляйте ссылки на треки, альбомы или плейлисты!

### Примеры ссылок

| Тип контента | Пример ссылки |
| :--- | :--- |
| 🎵 **Трек** | `https://music.yandex.ru/track/12345678` |
| 💿 **Альбом** | `https://music.yandex.ru/album/87654321` |
| 📑 **Плейлист** | `https://music.yandex.ru/playlists/123` |

---

## 📊 Команды бота

| Команда | Назначение | Доступность |
| :--- | :--- | :--- |
| `/start` | Запуск бота, авторизация, главное меню | **Все Telegram-версии** (`host_full`, `host`, `raspberry`, `legacy`, `windows`, `android`) |
| `/status` | Состояние сервера (CPU, память, температура, очередь) | `bocchi_host_full.py`, `bocchi_bot_raspberry.py`, `bocchi_Legacy_bot_raspberry.py` |
| `/logout` | Удалить сохранённый токен Яндекса | **Все Telegram-версии** |
| `/quality` | Изменить качество загрузки (Низкое / Среднее / Высокое) | `bocchi_host_full.py`, `bocchi_bot_host.py` |
| `/stop` | Экстренная (жёсткая) остановка всех загрузок | `bocchi_host_full.py`, `bocchi_bot_host.py` |
| `/menu` | Показать главное меню с кнопками | Все серверные (`host_full`, `host`, `raspberry`), `windows`, `android` |
| `/cancel` | Отменить текущий диалог (возврат в меню) | Все серверные, `windows`, `android` |

> [!NOTE]
> * **CLI-версия** (`bocchi_bot_CLI.py`) **не является Telegram-ботом** — это консольное приложение. Управление в нём осуществляется **цифрами** через текстовое меню, а не командами.
> * В версиях для **Android** и **Windows** отсутствуют команды `/status` и `/quality`.
> * В **Legacy Raspberry Pi** нет `/menu`, `/cancel`, `/quality`, `/stop`.
> * Все остальные действия (отправка ссылок, обновление токена, отмена загрузки) доступны через **кнопки главного меню** в серверных версиях.

---

## 🔧 Особенности работы

| Этап обработки | Как всё устроено под капотом |
| :--- | :--- |
| 🏷️ **Получение метаданных** | • **Из API Яндекс.Музыки**: исполнитель, название, длительность<br>• **Из iTunes**: альбом, год, жанр, обложка высокого разрешения<br>• **Из загрузчика**: текст песни в формате LRC (с таймкодами) |
| 🔄 **Обработка ссылок** | • **Одиночные треки** → загружаются как есть<br>• **Альбомы** → автоматически разбиваются на отдельные треки<br>• **Плейлисты** → автоматически разбиваются на отдельные треки *(Спасибо 🧡 [MarshalX](https://github.com/MarshalX))* |
| 📁 **Формат вывода** | • **Имя файла**: `Исполнитель — Название.расширение`<br>• **Метаданные**: встроены в аудиофайл (ID3 для MP3, MP4 для M4A)<br>• **Текст песен**: встроен в теги (USLT для MP3, `©lyr` для M4A) с сохранением таймкодов |
| ☁️ **Облачное хранилище** | Файлы **более 49 МБ** не проходят через лимит Telegram Bot API, поэтому бот отправляет их в облако и присылает ссылку:<br>1. **Litterbox** — временное хранилище (ссылка действует 24 часа)<br>2. **Catbox** — постоянное хранилище (резервный вариант)<br>3. **[/tmp/files](https://tmpfiles.org)** — если другие сервисы не отвечают |

---


> [!NOTE]
> *«А-а-а! Всё сломалось! Я знала, что этим кончится!» — **🎸 Хитори Гото (Боччи)***
> 
> **Бот не отвечает** 
>> «Э-это слишком страшно...» — **🎸 Боччи**
> * Проверьте, что токен Telegram корректен
> * Убедитесь, что бот запущен и не упал в обморок с ошибкой (как Боччи на сцене)
>
> **Ошибка авторизации в Яндекс.Музыке** 
>> «Мой бюджет не выдержит еще одной ошибки...» — **🪙 Рё**
> * Перевыпустите токен по ссылке авторизации
> * Убедитесь, что токен начинается с `y0_`
> 
> **Не скачиваются треки** 
>> Не беда! Главное — позитивный настрой!» — **✨ Кита**
> * Проверьте путь к `yandex-music-downloader`
> * Убедитесь, что у загрузчика есть права на выполнение
> * Проверьте интернет-соединение
> 
> **Нет текста песни** 
>> Эй, где вокал?! Не заставляйте менеджера нервничать!» — 🥁 Ниджика
> * Убедитесь, что для трека вообще есть текст на Яндекс.Музыке
> * Проверьте, что загрузчик запускается с параметром `--lyrics-format lrc`

---

## 🎧 Из чего собран бот (Инструменты группы)

| Категория | Проект | Автор / Команда |
| :--- | :--- | :--- |
| 🐍 **Основная работа** | [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) | Команда разработчиков ([AUTHORS.rst](https://github.com/python-telegram-bot/python-telegram-bot/blob/master/AUTHORS.rst)) |
| 📦 **Ядро загрузки** | [yandex-music-downloader](https://github.com/llistochek/yandex-music-downloader) | 🌿 [llistochek](https://github.com/llistochek) |
| 📦 **Работа с API** | [Yandex Music API](https://github.com/MarshalX/yandex-music-api) | 🧡 [MarshalX](https://github.com/MarshalX) |
| ☁️ **Отправка в облако** | [catboxpy](https://github.com/anshonweb/catboxpy) | ☁️ [anshonweb](https://github.com/anshonweb) |
| ☁️ **Резервное облако** | [/tmp/files](https://tmpfiles.org) | Неизвестен |
| 🖥 **Серверные решения** | 💚 [Serv.Host](https://serv.host/) | Команда Serv.Host |
| 🖥 **Архивный хостинг** | [Bothost](https://bothost.ru/) *(сейчас не используется)* | Команда Bothost |

---

## 🏆 Особые благодарности `(づ｡◕‿‿◕｡)づ`

> *«Без всех этих людей наша группа... то есть наш проект, никогда бы не вышел из шкафа! С-спасибо вам огромное!»* — **StalkerBocchi и Nero** 💖

| Кто | За что |
| :---: | :--- |
| <div align="center"><img src="https://imgproxy.attic.sh/insecure/f:png/plain/https://attic.sh/jv943f5odtpolvryxbw81hut8rqx" width="100" height="100" alt="emoji"><br><b>Nero</b></div> | Главный вдохновитель и первый бета-тестировщик (выдержала все падения бота!).|
| 🧡 **[MarshalX](https://github.com/MarshalX)** | Создание [Yandex Music API](https://github.com/MarshalX/yandex-music-api) — фундамент, на котором держится вся магия с Яндексом.|
| 🌿 **[llistochek](https://github.com/llistochek)** | Создание [yandex-music-downloader](https://github.com/llistochek/yandex-music-downloader) — основа для скачивания треков.|
| 💚 **[Serv.Host](https://serv.host/)** | Лучшая хостинг-площадка для проекта и отличный фирменный мерч!|
| 🐋 **[Docker](https://www.docker.com/)** | Контейнеризация, чтобы код работал везде одинаково.|
| 🛠️ **Тестировщики** | Ребята, которые ловили баги раньше, чем их замечали пользователи.|
| 🤖 **AI-ассистенты** | Помощь в написании кода и спасение от дедлайнов. |
| ☕ **Вам** | За то, что дочитали эту стену текста до конца и пользуетесь нашим ботом. Вы лучшие! 🎸 |

---

## 📝 Лицензия

> «Правила есть правила! Без лицензии Рё запрещает нам выступать.»

Проект распространяется под некоммерческой лицензией. Подробности в файле [LICENSE](LICENSE).

>Сделано с любовью к музыке и лёгкой социофобией 🎸✨ \
> ©️ 2026 StalkerBocchi (Hanako)