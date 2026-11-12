# 🎸 Bocchi Downloader — Server Status Dashboard

Красивый, анимированный дашборд мониторинга сервера \
Данные получаются через **Glances API** + FastAPI, отображаются в реальном времени и обновляются каждые 2 секунды.

![Dashboard Preview](https://raw.githubusercontent.com/StalkerBocchi/Bocchi-Downloader/main/image.png)

> [!Important]
> ## Обнаружены особенности работы дашборда
> При использовании дашборда вы можете заметить некоторые нюансы, которые объясняются особенностями работы сети и браузеров. Ниже описаны две наиболее частые ситуации и способы их решения.

> [!Warning]
> ## Задержка отклика при обращении к Яндекс.Музыке кажется значительной
> Пинг Яндекс.Музыки, который можно увидеть на дашборде, измеряется с помощью HTTP/HTTPS-запросов. В норме он составляет примерно 180–220 миллисекунд. Этот показатель помогает проверить доступность веб-ресурса, оценить скорость загрузки страниц и обнаружить проблемы на прикладном уровне. Реальное время отклика ICMP составляет около 47 миллисекунд.

> [!Warning]
> ## Проблемы с отображением данных
> Иногда вы можете заметить, что на компьютере, телефоне или планшете данные на дашборде не совпадают. Это не ошибка дашборда и не сбой сервера, а особенность работы браузеров, которая называется **кешированием**.
> ### Что такое кеширование?
> Чтобы страницы загружались быстрее, браузер запоминает некоторые данные: картинки, стили, а иногда и ответы от сервера. Когда вы заходите на сайт повторно, браузер показывает сохранённую копию, а не запрашивает всё заново. Это экономит трафик и ускоряет работу.
> ### Почему это влияет на дашборд?
> Дашборд обновляет данные каждые 2 секунды — он показывает текущую загрузку процессора, памяти, сети и состояние бота. Но если браузер запомнил старый ответ от сервера, он может продолжать показывать устаревшие данные, даже если на сервере они уже изменились. Особенно это заметно, если вы долго не обновляли страницу или открыли её на одном устройстве, а потом зашли с другого — на одном устройстве может остаться старая версия.
> ### Это ошибка дашборда?
> Нет, это нормальное поведение любого браузера. Сам дашборд всегда показывает актуальные данные, которые получает напрямую из системы каждые 2 секунды. Проблема только в том, что браузер может «застрять» на старой версии. Режим инкогнито или жёсткая перезагрузка решают это мгновенно.
>
> Если вы открыли дашборд в инкогнито и данные всё ещё не обновляются — значит, проблема не в кеше. \
> Если у вас возникли проблемы, пожалуйста, сообщите о них [здесь](https://github.com/StalkerBocchi/Bocchi-Downloader/issues). Мы обязательно поможем вам разобраться.

## 📊 Отображаемые метрики

*   Загрузка **CPU** (процент, график, load average)
*   Использование **оперативной памяти** (занято, свободно, всего)
*   **Сетевой трафик** (входящий/исходящий, автоматический выбор единиц)
*   Суммарное использование **дискового пространства**
*   **Время работы сервера** (на русском языке, с точностью до секунды)
*   **Статус Docker-контейнера** `bocchi_bot` (онлайн/офлайн)
*   **Графики истории** (20 точек) для CPU, RAM, сети и диска
*   **Пинг** напрямую с сервера до `music.yandex.ru`

## 🏗 Архитектура

```
Браузер → Nginx (:61209) → FastAPI (:61211) → Glances (:61208)
```

FastAPI — тонкая прослойка: «сырые» метрики (CPU, память, сеть, диски, ОС) она проксирует из Glances без изменений, а три показателя вычисляет сама:

* **Пинг** — реальный замер задержки HTTPS-запроса до `music.yandex.ru`;
* **Аптайм** — строка Glances конвертируется в секунды;
* **Статус бота** — честный `docker inspect` контейнера `bocchi_bot` (running/exited/missing).

Отдельный пинг-сервер и порт 61210 не используются — всё считается внутри FastAPI.

## 🚀 Быстрый старт (Ubuntu 22.04/24.04)

### 0️⃣ Развёртывание бота (Docker)

> [!Warning]
> Скрипт `deploy.sh` очищает директорию, из которой запускается, и клонирует туда репозиторий.
> Запускайте его **только в пустой папке** (например, `/root/deploy-tmp`) — не в `/root/bocchi_bot` и не в `/root`.

```bash
mkdir -p /root/deploy-tmp && cd /root/deploy-tmp
curl -fsSL https://raw.githubusercontent.com/StalkerBocchi/Bocchi-Downloader/main/deploy.sh -o deploy.sh && bash deploy.sh
```

Скрипт спросит токен Telegram-бота и соберёт контейнер `bocchi_bot`.

Проверка: `docker logs --tail 20 bocchi_bot` → `Application started`, polling без ошибок.
Если видите `InvalidToken` — токен неверный или отозван: поправьте `.env` в папке деплоя и выполните `docker restart bocchi_bot`.

### 1️⃣ Установка Glances

```bash
apt update && apt install -y pipx python3-dev python3-venv
pipx ensurepath
source ~/.bashrc
pipx install 'glances[all]'
```

### 2️⃣ Запуск Glances как службы systemd

```bash
cat > /etc/systemd/system/glances.service << 'EOF'
[Unit]
Description=Glances Web Server
After=network.target

[Service]
Type=simple
ExecStartPre=/bin/bash -c 'fuser -k 61208/tcp 2>/dev/null || true'
ExecStart=/root/.local/bin/glances -w --bind 0.0.0.0 --port 61208 -t 1 --disable-plugin smart --disable-plugin gpu
Restart=on-failure
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now glances
```

Проверьте работу: `curl http://127.0.0.1:61208/api/4/cpu` → должен вернуть JSON.

### 3️⃣ Виртуальное окружение дашборда

```bash
apt install -y git nginx
cd /root
git clone -b main https://github.com/StalkerBocchi/Bocchi-Downloader.git bocchi_bot
cd /root/bocchi_bot
python3 -m venv venv
venv/bin/pip install fastapi "uvicorn[standard]"
```

> [!Important]
> Библиотека `httpx` **не нужна и не должна устанавливаться** — в окружениях Python 3.14 она падает на создании SSL-контекста (нет CA-сертификатов внутри venv). Бэкенд работает на стандартном `urllib` + системном `ping`.

### 4️⃣ Служба FastAPI-дашборда

```bash
cat > /etc/systemd/system/bocchi-dashboard.service << 'EOF'
[Unit]
Description=Bocchi Dashboard (FastAPI)
After=network.target

[Service]
WorkingDirectory=/root/bocchi_bot
ExecStart=/root/bocchi_bot/venv/bin/python -m uvicorn Dashboard_Endpoint:app --host 127.0.0.1 --port 61211
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now bocchi-dashboard
```

> [!TIP]
> Проверка синтаксиса перед рестартом (полезная привычка):

```bash
cd /root/bocchi_bot && venv/bin/python -c "import Dashboard_Endpoint" && echo "SYNTAX OK"
```

### 5️⃣ Nginx

```bash
cat > /etc/nginx/sites-available/dashboard << 'EOF'
server {
    listen 61209;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:61211;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
EOF

ln -sf /etc/nginx/sites-available/dashboard /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
```

### 6️⃣ Файрвол

```bash
ufw allow 61209/tcp
```

### 7️⃣ Проверка

Откройте браузер по адресу `http://<IP-сервера>:61209`. Дашборд обновляется каждые 2 секунды; зелёная точка и «Бот онлайн» — значит контейнер `bocchi_bot` запущен.

Контрольный набор с сервера:

```bash
docker ps | grep bocchi_bot                        # контейнер Up
systemctl is-active glances bocchi-dashboard nginx # active ×3
ss -tlnp | grep -E "61208|61209|61211"             # три живых порта
curl -s http://127.0.0.1:61211/api/ping            # ~180–250, не -1
curl -s http://127.0.0.1:61211/api/4/uptime        # число секунд
curl -s http://127.0.0.1:61211/api/4/cpu | head -c 100
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:61209/   # 200
```

## ⚙️ Проблемы и решения

| Проблема | Решение |
|---|---|
| Сайт отдаёт **502** | FastAPI не отвечает: `systemctl status bocchi-dashboard`. `203/EXEC` + «venv/bin/python: No such file» — пересоздать venv (шаг 3). `status=1` — проверить синтаксис (см. TIP выше). |
| `curl http://127.0.0.1:61208/api/4/cpu` не работает | Glances не запущен: `systemctl status glances`. |
| **Пинг `-1`** | Сервис работает, но не достучался до `music.yandex.ru`. Проверьте `curl -I https://music.yandex.ru` с сервера. |
| `ModuleNotFoundError: httpx` | На диске старая версия `Dashboard_Endpoint.py`. Обновите репозиторий: `git pull`, затем `systemctl restart bocchi-dashboard`. |
| `{"detail":"Not Found"}` на порту 61209 | Путь не зарегистрирован в FastAPI — вероятно, на диске старая версия файла. `git pull` + рестарт. На порту 61212 — Nginx не проксирует `/api/` в Glances, проверьте конфиг. |
| Данные нулевые | Откройте консоль браузера (F12). Если запросы к `/api/4/...` возвращают 404 — проблема в Nginx. Если возвращают JSON, но дашборд не обновляется — возможно, кеш браузера (Ctrl+F5). |
| Диск отображается как 0 GB | Убедитесь, что в `curl http://127.0.0.1:61208/api/4/fs` есть разделы. Суммируются только разделы с `fs_type` не `squashfs`, `tmpfs`, `devtmpfs`, `overlay` и не `/snap/*`. |
| Не отображается статус бота | Проверьте, что контейнер `bocchi_bot` запущен: `docker ps`. Через бэкенд: `curl http://127.0.0.1:61211/api/4/containers`. |
| Графики не строятся | Подождите 10 секунд — графики заполняются историей. Убедитесь, что в консоли нет ошибок JavaScript. |
| Разные данные на разных устройствах | Кеш браузера: инкогнито или Ctrl+F5. Сам дашборд всегда актуален. |

## 🧹 Обновление дашборда

> [!Tip]
> Новый дашборд отдаётся **прямо из репозитория** (`/root/bocchi_bot/bocchi_dashboard.html`) — копия в `/var/www` для него не нужна:

```bash
cd /root/bocchi_bot
git pull
systemctl restart bocchi-dashboard
```

Затем обновите страницу в браузере (Ctrl+F5). Копия в `/var/www/dashboard/index.html` нужна только старому дашборду на порту 61212 — его можно обновить так:

```bash
curl -o /var/www/dashboard/index.html https://raw.githubusercontent.com/StalkerBocchi/Bocchi-Downloader/main/bocchi_dashboard.html
```

> [!Warning]
> Скрипт `deploy.sh` очищает директорию, из которой запускается, и пересоздаёт окружение. Запускайте его **только в пустой папке** — никогда из `/root/bocchi_bot`, иначе будут удалены venv дашборда и локальные правки.

## 🙏 Благодарности

*   [Glances](https://github.com/nicolargo/glances) — инструмент сбора метрик.
*   [Chart.js](https://www.chartjs.org/) — библиотека для графиков.
*   Font Awesome — иконки.
