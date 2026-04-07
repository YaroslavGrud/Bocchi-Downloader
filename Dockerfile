FROM python:3.11-slim

# Установка ffmpeg (обязательно для аудио/видео)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Создаём правильный requirements.txt (на основе предоставленного списка)
RUN echo 'aiofiles==25.1.0' >> requirements.txt && \
    echo 'aiohappyeyeballs==2.6.1' >> requirements.txt && \
    echo 'aiohttp==3.13.5' >> requirements.txt && \
    echo 'aiosignal==1.4.0' >> requirements.txt && \
    echo 'anyio==4.13.0' >> requirements.txt && \
    echo 'APScheduler==3.11.2' >> requirements.txt && \
    echo 'attrs==26.1.0' >> requirements.txt && \
    echo 'catboxpy==0.1.1.1' >> requirements.txt && \
    echo 'certifi==2026.2.25' >> requirements.txt && \
    echo 'charset-normalizer==3.4.7' >> requirements.txt && \
    echo 'frozenlist==1.8.0' >> requirements.txt && \
    echo 'h11==0.16.0' >> requirements.txt && \
    echo 'httpcore==1.0.9' >> requirements.txt && \
    echo 'httpx==0.28.1' >> requirements.txt && \
    echo 'idna==3.11' >> requirements.txt && \
    echo 'multidict==6.7.1' >> requirements.txt && \
    echo 'mutagen==1.47.0' >> requirements.txt && \
    echo 'propcache==0.4.1' >> requirements.txt && \
    echo 'psutil==7.2.2' >> requirements.txt && \
    echo 'pycryptodome==3.23.0' >> requirements.txt && \
    echo 'PySocks==1.7.1' >> requirements.txt && \
    echo 'python-dotenv==1.2.2' >> requirements.txt && \
    echo 'python-telegram-bot==22.7' >> requirements.txt && \
    echo 'requests==2.33.1' >> requirements.txt && \
    echo 'StrEnum==0.4.15' >> requirements.txt && \
    echo 'typing_extensions==4.15.0' >> requirements.txt && \
    echo 'tzdata==2026.1' >> requirements.txt && \
    echo 'tzlocal==5.3.1' >> requirements.txt && \
    echo 'urllib3==2.6.3' >> requirements.txt && \
    echo 'yandex-music @ https://github.com/llistochek/yandex-music-api/archive/9623fbca7704f47766614efe51d66c9fd496714c.zip#sha256=44c897892a8a6463246b5dc18c340ddb0f25a312b12b1727820de8387235c857' >> requirements.txt && \
    echo 'yandex-music-downloader @ https://github.com/llistochek/yandex-music-downloader/archive/main.zip#sha256=16ebe9e4b6ac1b4f88c6eb64ad9bf7d101f103f7ffd060a6f9f09ef4103eb323' >> requirements.txt && \
    echo 'yarl==1.23.0' >> requirements.txt

# Установка зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код репозитория (как есть, с main.py в корне)
COPY . .

# Создаём нужную структуру внутри контейнера:
#   - папку Bocchi_Downloader
#   - перемещаем туда все исходники (handlers, keyboards, states, main.py)
#   - создаём bocchi_bot_host.py как копию main.py
RUN mkdir -p /app/Bocchi_Downloader && \
    mv main.py handlers keyboards states /app/Bocchi_Downloader/ 2>/dev/null || true && \
    cp /app/Bocchi_Downloader/main.py /app/Bocchi_Downloader/bocchi_bot_host.py

# Добавляем корень /app в PYTHONPATH, чтобы импорты "from handlers import ..." работали
ENV PYTHONPATH=/app

# Создаём рабочие папки (для загрузок, данных, временных файлов)
RUN mkdir -p /app/data /app/downloads /app/temp && chmod 777 /app/data /app/downloads /app/temp

# Проверяем, что точка входа создалась
RUN if [ ! -f "/app/Bocchi_Downloader/bocchi_bot_host.py" ]; then \
        echo "❌ Ошибка: не удалось создать bocchi_bot_host.py" && exit 1; \
    fi

# Запуск бота
CMD ["python", "/app/Bocchi_Downloader/bocchi_bot_host.py"]
