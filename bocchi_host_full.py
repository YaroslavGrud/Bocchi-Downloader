# (c) 2026 Hanako
# Bocchi Downloader (Server Edition)
# Полная версия со всеми исправлениями и подробными комментариями.
# Все ошибки NameError (cancel, menu и др.) устранены.

import asyncio                                      # Асинхронная работа, создание задач, блокировки, очереди
import aiohttp                                      # Асинхронные HTTP-запросы (API Яндекс.Музыки, обложки)
import logging                                      # Запись логов
import os                                           # Переменные окружения, файловая система
import json                                         # Сериализация/десериализация JSON (состояние бота)
import random                                       # Случайные числа (анимации, фразы)
import re                                           # Регулярные выражения (парсинг ссылок, токенов)
import shutil                                       # Операции с файлами и папками (удаление, проверка диска)
import subprocess                                   # Запуск внешних процессов (ping)
import time                                         # Метки времени, задержки
import urllib.parse                                 # Парсинг URL (urlparse, parse_qs)
import uuid                                         # Генерация уникальных идентификаторов
from pathlib import Path                            # Удобная работа с путями
import io                                           # Работа с байтовыми потоками (сжатие обложек)
import gc                                           # Сборщик мусора (очистка памяти)

import psutil                                       # Информация о системе (CPU, память, диск)
from catboxpy import AsyncCatboxClient, LitterboxClient  # Загрузка больших файлов на файловые хостинги
from dotenv import load_dotenv                      # Загрузка переменных окружения из .env
from mutagen.easyid3 import EasyID3                 # Простой доступ к ID3 тегам MP3
from mutagen.id3 import ID3, USLT, TDRC, TCON, TALB, APIC, TPE2  # Детальная работа с ID3 тегами
from mutagen.mp3 import MP3                         # Объект MP3-файла
from mutagen.mp4 import MP4, MP4Cover               # Объект MP4/M4A-файла + обложка
from mutagen import File                            # Универсальное открытие аудиофайла
from PIL import Image                               # Работа с изображениями (сжатие обложек)
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
)                                                   # Объекты Telegram Bot API
from telegram.constants import ChatAction           # Действия в чате (печатает...)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, ConversationHandler, filters
)                                                   # Фреймворк для создания бота
from yandex_music import ClientAsync                # Асинхронный клиент Яндекс.Музыки

# ---------------------- НАСТРОЙКА ЛОГИРОВАНИЯ ----------------------
logging.getLogger("httpx").setLevel(logging.WARNING)   # Убираем лишние логи от httpx
load_dotenv()                                          # Загружаем переменные окружения из .env

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(message)s')
logger = logging.getLogger("BocchiStation")            # Основной логгер бота

# ---------------------- ПАПКА ДЛЯ ДАННЫХ ----------------------
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)                          # Создаём папку data (если её нет) при старте

# ---------------------- КОНФИГУРАЦИЯ ----------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТОКЕН_ЗДЕСЬ")
# Токен Telegram бота. Если не задан в .env, используется заглушка.

DOWNLOADER_PATH = os.getenv("DOWNLOADER_PATH", "yandex-music-downloader")
# Путь к исполняемому файлу загрузчика yandex-music-downloader.

STATS_FILE = os.getenv("STATS_FILE", "data/stats.txt")
# Файл, в котором хранится общий объём скачанных данных (в байтах).

MAX_LINKS = int(os.getenv("MAX_LINKS", "10"))
# Максимальное количество ссылок, принимаемых от пользователя за один раз.

DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", "600"))
# Таймаут (в секундах) на скачивание одного трека.

TOKEN_LIFETIME = int(os.getenv("TOKEN_LIFETIME", "86400"))
# Срок жизни токена пользователя в секундах (по умолчанию 24 часа).

CLOUD_TIMEOUT = int(os.getenv("CLOUD_TIMEOUT", "120"))
# Таймаут (в секундах) на загрузку файла на облачный сервис (при превышении 49 МБ).

DEFAULT_QUALITY = int(os.getenv("DEFAULT_QUALITY", "2"))
# Качество загрузки по умолчанию: 0 – низкое, 1 – среднее, 2 – высокое.

MIN_FREE_DISK_MB = int(os.getenv("MIN_FREE_DISK_MB", "20"))
# Минимальное свободное место на диске (в МБ), необходимое для продолжения загрузки.

TRACK_DELAY_SECONDS = float(os.getenv("TRACK_DELAY_SECONDS", "5.0"))
# Пауза между отправкой треков в Telegram (чтобы избежать превышения лимитов).

STUCK_TIMEOUT = int(os.getenv("STUCK_TIMEOUT", "120"))
# Если загрузка длится дольше этого времени, задача считается зависшей и появляется кнопка перезапуска.

ACCUMULATION_DELAY = float(os.getenv("ACCUMULATION_DELAY", "5.0"))
# Время, в течение которого бот ждёт новые ссылки перед началом обработки (пакетный режим).

# ---------------------- ФАЙЛЫ СОСТОЯНИЯ ----------------------
QUEUE_STATE_FILE = "data/download_queue_state.json"
# Сохраняет очередь задач между перезапусками бота.

USER_TOKENS_FILE = "data/user_tokens.json"
# Содержит токены пользователей с временными метками.

ACTIVE_MSGS_FILE = "data/active_status_msgs.json"
# Содержит информацию о статусных сообщениях (для удаления после перезапуска).

PENDING_TASKS_FILE = "data/pending_tasks.json"
# Содержит отложенные задачи (когда чат был недоступен).

# ---------------------- ВРЕМЯ ЗАПУСКА И АНТИСПАМ ----------------------
BOT_START_TIME = time.time()
# Время запуска бота (unix timestamp). Сообщения, отправленные до этого момента, игнорируются.

COMMAND_COOLDOWN = 5.0
# Минимальный интервал (в секундах) между обработкой команд меню (защита от спама).

last_command_time = {}
# Словарь {user_id: timestamp} для хранения времени последней выполненной команды меню.

# ---------------------- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ----------------------
download_semaphore = None
# Семафор (asyncio.Semaphore), ограничивающий одновременное скачивание до 1 трека.

download_queue = None
# Очередь задач (asyncio.Queue), из которой воркер получает треки на скачивание.

link_accumulators = {}
# Словарь {user_id: [url1, url2, ...]} для накопления ссылок перед пакетной обработкой.

user_delay_tasks = {}
# Словарь {user_id: asyncio.Task}, хранящий активную задачу отложенной обработки ссылок.

user_processing = {}
# Флаг {user_id: True}, указывающий, что пользователь уже находится в процессе обработки.

worker_busy = False
# Глобальный флаг, показывающий, занят ли воркер в данный момент.

active_tasks_count = 0
# Количество задач, которые находятся в очереди или выполняются в данный момент.

last_auth_warning = {}
# {user_id: timestamp} последнего предупреждения о необходимости авторизации.
# Используется, чтобы не спамить сообщениями.

WARNING_COOLDOWN = 60
# Минимальный интервал между повторными предупреждениями о необходимости токена (сек).

worker_task = None
# Ссылка на asyncio.Task, в котором работает воркер.

token_checker_task = None
# Ссылка на asyncio.Task периодической проверки истёкших токенов.

memory_cleaner_task = None
# Ссылка на asyncio.Task фоновой очистки памяти (если потребление > 50%).

last_processed_msg = {}
# Словарь {user_id: message_id} для предотвращения дублирования сообщений (из-за ретраев).

user_locks = {}
# Словарь {user_id: asyncio.Lock} для блокировки операций авторизации (избегаем гонок).

user_tokens = {}
# Словарь {user_id: {"token": "y0_...", "timestamp": 1234567890}} – сохранённые токены.

active_status_msgs = {}
# Словарь {task_id: {"chat_id": ..., "message_id": ...}} активных статусных сообщений загрузки.

pending_tasks = {}
# Словарь {chat_id: [task1, task2, ...]} отложенных задач, которые не удалось отправить из-за блокировки.

current_task_info = {}
# Словарь {task_id: {"start_time":..., "chat_id":..., "task":..., "process":..., "status_msg_id":...}}
# Информация о задаче, которая выполняется прямо сейчас.

# ---------------------- СОСТОЯНИЯ ДИАЛОГА ----------------------
WAITING_FOR_TOKEN, WAITING_FOR_LINK = range(2)
# Используются в ConversationHandler: состояние ожидания токена и ожидания ссылок.

# ---------------------- НАЗВАНИЯ КАЧЕСТВА ----------------------
QUALITY_NAMES = {0: "Низкое", 1: "Среднее", 2: "Высокое"}
# Отображение числовых значений качества в читаемый вид.

QUALITY_NAMES_GENITIVE = {0: "низкого", 1: "среднего", 2: "высокого"}
# Родительный падеж для фраз типа "понижаю до среднего".

QUALITY_BUTTONS = {"Низкое": 0, "Среднее": 1, "Высокое": 2}
# Обратное отображение для кнопок выбора качества.

# ---------------------- КЛАВИАТУРЫ ----------------------
quality_keyboard = [[KeyboardButton("Низкое"), KeyboardButton("Среднее"), KeyboardButton("Высокое")]]
quality_markup = ReplyKeyboardMarkup(quality_keyboard, resize_keyboard=True, one_time_keyboard=True)
# Клавиатура, показываемая при смене качества.

main_menu_keyboard = [
    ["▶ Начать загрузку", "⏹ Отменить загрузку"],
    ["🔓 Удалить токен", "🔄 Обновить токен"],
    ["🎵 Качество", "📊 Статус"],
    ["🆘 Экстренная остановка"]
]
main_markup = ReplyKeyboardMarkup(main_menu_keyboard, resize_keyboard=True)
# Основное меню бота.


# ======================================================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С ТОКЕНАМИ
# ======================================================================

def save_user_tokens():
    """Сохраняет словарь user_tokens в JSON-файл."""
    try:
        with open(USER_TOKENS_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_tokens, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения токенов: {e}")

def load_user_tokens():
    """Загружает токены из файла; просроченные удаляются."""
    global user_tokens
    if not os.path.exists(USER_TOKENS_FILE):
        return
    try:
        with open(USER_TOKENS_FILE, 'r', encoding='utf-8') as f:
            loaded = json.loads(f.read().strip())
        now = time.time()
        # Оставляем только токены, не превысившие срок жизни
        user_tokens = {
            uid: data for uid, data in loaded.items()
            if now - data.get('timestamp', 0) <= TOKEN_LIFETIME
        }
        logger.info(f"Загружено {len(user_tokens)} действующих токенов")
    except Exception as e:
        logger.error(f"Ошибка загрузки токенов: {e}")

def is_token_valid_by_id(user_id: int) -> bool:
    """Проверяет, валиден ли токен пользователя (не истёк)."""
    data = user_tokens.get(str(user_id))
    return data is not None and (time.time() - data['timestamp']) <= TOKEN_LIFETIME

def get_user_token(user_id: int) -> str | None:
    """Возвращает строку токена, если он ещё действителен, иначе None."""
    data = user_tokens.get(str(user_id))
    if data and is_token_valid_by_id(user_id):
        return data['token']
    return None

def set_user_token(user_id: int, token: str):
    """Сохраняет токен пользователя с текущим временем."""
    user_tokens[str(user_id)] = {"token": token, "timestamp": time.time()}
    save_user_tokens()

def delete_user_token(user_id: int):
    """Удаляет токен пользователя."""
    user_tokens.pop(str(user_id), None)
    save_user_tokens()


# ======================================================================
# ФУНКЦИИ ДЛЯ СТАТУСНЫХ СООБЩЕНИЙ
# ======================================================================

def save_active_msgs():
    """Сохраняет информацию о статусных сообщениях загрузки (для перезапуска)."""
    try:
        with open(ACTIVE_MSGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(active_status_msgs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения активных сообщений: {e}")

def load_active_msgs():
    """Загружает статусные сообщения из файла."""
    global active_status_msgs
    if os.path.exists(ACTIVE_MSGS_FILE):
        try:
            with open(ACTIVE_MSGS_FILE, 'r', encoding='utf-8') as f:
                active_status_msgs = json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки активных сообщений: {e}")

async def cleanup_orphan_messages(app):
    """Удаляет «висящие» статусные сообщения, оставшиеся после прошлого запуска бота."""
    for task_id, info in list(active_status_msgs.items()):
        try:
            await app.bot.delete_message(chat_id=info['chat_id'], message_id=info['message_id'])
        except:
            pass
        active_status_msgs.pop(task_id, None)
    save_active_msgs()


# ======================================================================
# ФУНКЦИИ ДЛЯ ОТЛОЖЕННЫХ ЗАДАЧ
# ======================================================================

def save_pending_tasks():
    """Сохраняет отложенные задачи в JSON."""
    try:
        with open(PENDING_TASKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(pending_tasks, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения отложенных задач: {e}")

def load_pending_tasks():
    """Загружает отложенные задачи из файла."""
    global pending_tasks
    if os.path.exists(PENDING_TASKS_FILE):
        try:
            with open(PENDING_TASKS_FILE, 'r', encoding='utf-8') as f:
                pending_tasks = json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки отложенных задач: {e}")

def add_pending_task(chat_id: int, task: dict):
    """Добавляет задачу в список отложенных для конкретного чата."""
    pending_tasks.setdefault(str(chat_id), []).append(task)
    save_pending_tasks()

def get_pending_tasks(chat_id: int) -> list:
    """Возвращает список отложенных задач для чата."""
    return pending_tasks.get(str(chat_id), [])

def clear_pending_tasks(chat_id: int):
    """Очищает отложенные задачи для чата."""
    pending_tasks.pop(str(chat_id), None)
    save_pending_tasks()


# ======================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ======================================================================

def is_message_too_old(update: Update) -> bool:
    """Проверяет, было ли сообщение отправлено до старта бота (игнорируем старые)."""
    return update.message and update.message.date.timestamp() < BOT_START_TIME

def is_token_valid(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет, действителен ли токен, сохранённый в контексте пользователя."""
    return is_token_valid_by_id(context._user_id)

def get_plural_tracks(n: int) -> str:
    """Возвращает "N трек" / "N трека" / "N треков" с правильным склонением."""
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} трек"
    elif 2 <= n % 10 <= 4 and (n % 100 < 10 or n % 100 >= 20):
        return f"{n} трека"
    return f"{n} треков"

# ---------- Обложки ----------
async def fetch_cover_from_yandex(cover_uri: str) -> bytes | None:
    """Скачивает обложку высокого разрешения с Яндекс.Музыки по cover_uri."""
    if not cover_uri:
        return None
    try:
        cover_url = f"https://{cover_uri.replace('%%', '1000x1000')}"
        async with aiohttp.ClientSession() as session:
            async with session.get(cover_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    return await resp.read()
    except:
        pass
    return None

def compress_cover(cover_bytes: bytes, max_size_bytes: int = 200 * 1024) -> bytes | None:
    """
    Сжимает изображение обложки в JPEG так, чтобы размер не превышал max_size_bytes.
    Использует снижение качества и ресайз. Если сжать не удаётся, возвращает None.
    """
    if not cover_bytes or len(cover_bytes) <= max_size_bytes:
        return cover_bytes
    try:
        img = Image.open(io.BytesIO(cover_bytes)).convert('RGB')
        # Пробуем уменьшать качество
        for quality in [85, 75, 65, 55, 45, 35, 25]:
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=quality, optimize=True)
            if buf.tell() <= max_size_bytes:
                return buf.getvalue()
        # Уменьшаем размер
        for scale in [0.75, 0.5, 0.3, 0.2, 0.15]:
            w, h = int(img.width * scale), int(img.height * scale)
            if w < 10 or h < 10: continue
            resized = img.resize((w, h), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            resized.save(buf, format='JPEG', quality=75, optimize=True)
            if buf.tell() <= max_size_bytes:
                return buf.getvalue()
        # Экстремальное сжатие
        for scale in [0.1, 0.08]:
            w, h = int(img.width * scale), int(img.height * scale)
            if w < 8 or h < 8: continue
            resized = img.resize((w, h), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            resized.save(buf, format='JPEG', quality=30, optimize=True)
            if buf.tell() <= max_size_bytes:
                return buf.getvalue()
    except Exception as e:
        logger.error(f"Ошибка сжатия обложки: {e}")
    return None

def extract_cover_from_audio(file_path: Path) -> bytes | None:
    """Извлекает встроенную обложку из MP3/M4A-файла."""
    try:
        audio = File(file_path)
        if audio is None: return None
        # MP3: ищем APIC:
        if hasattr(audio, 'tags') and audio.tags:
            if 'APIC:' in audio.tags:
                for tag in audio.tags.values():
                    if isinstance(tag, APIC):
                        return tag.data
            # M4A: ищем covr
            if 'covr' in audio.tags and audio.tags['covr']:
                if isinstance(audio.tags['covr'][0], MP4Cover):
                    return bytes(audio.tags['covr'][0])
    except:
        pass
    return None

def get_audio_duration(file_path: Path) -> int:
    """Возвращает длительность аудио в секундах."""
    try:
        if file_path.suffix.lower() == '.m4a':
            return int(MP4(file_path).info.length)
        return int(MP3(file_path).info.length)
    except:
        return 0

# ---------- Диск, мусор, статистика ----------
def check_disk_space(min_free_mb: int = MIN_FREE_DISK_MB) -> tuple[bool, float]:
    """Проверяет, достаточно ли свободного места. Возвращает (хватает?, свободно_МБ)."""
    try:
        stat = shutil.disk_usage(Path.cwd())
        free_mb = stat.free / (1024 * 1024)
        return free_mb >= min_free_mb, free_mb
    except:
        return True, 9999.0

def cleanup_old_tmp_dirs():
    """Удаляет временные папки bocchi_tmp_*, оставшиеся от предыдущих загрузок."""
    cnt = 0
    for tmp_dir in Path('.').glob('bocchi_tmp_*'):
        if tmp_dir.is_dir():
            shutil.rmtree(tmp_dir, ignore_errors=True)
            cnt += 1
    if cnt:
        logger.info(f"Удалено старых временных папок: {cnt}")

def add_stats(bytes_added: int):
    """Увеличивает счётчик скачанных байт в файле статистики."""
    try:
        current = 0.0
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, "r") as f:
                current = float(f.read())
        with open(STATS_FILE, "w") as f:
            f.write(str(current + bytes_added))
    except:
        pass

def get_formatted_stats() -> str:
    """Возвращает строку с общим объёмом скачанного (Б, КБ, МБ, ГБ, ТБ)."""
    try:
        if not os.path.exists(STATS_FILE):
            return "0 Б"
        with open(STATS_FILE, "r") as f:
            val = float(f.read())
        for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
            if val < 1024.0:
                return f"{val:.2f} {unit}"
            val /= 1024.0
        return f"{val:.2f} ТБ"
    except:
        return "0 Б"

def get_ping() -> float:
    """
    Измеряет пинг до ya.ru с помощью системной утилиты ping.
    Никаких лишних логов, только число (мс) или 0 при ошибке.
    """
    try:
        out = subprocess.check_output(["ping", "-c", "1", "-W", "1", "ya.ru"],
                                      stderr=subprocess.DEVNULL, text=True)
        match = re.search(r'time=([\d\.]+)', out)
        if match:
            return float(match.group(1))
    except:
        pass
    return 0.0

def get_user_quality(context: ContextTypes.DEFAULT_TYPE) -> int:
    """Возвращает текущее значение качества пользователя (по умолчанию DEFAULT_QUALITY)."""
    return context.user_data.get('quality', DEFAULT_QUALITY)

def set_user_quality(context: ContextTypes.DEFAULT_TYPE, quality: int) -> bool:
    """Задаёт качество пользователя, если значение входит в QUALITY_NAMES."""
    if quality in QUALITY_NAMES:
        context.user_data['quality'] = quality
        return True
    return False


# ======================================================================
# ПАРСИНГ ССЫЛОК ЯНДЕКС.МУЗЫКИ
# ======================================================================

def extract_base_url(url: str) -> str:
    """Извлекает домен и подставляет /music, если его нет."""
    m = re.match(r'(https?://(?:[a-z0-9-]+\.)*yandex\.[a-z]{2,3})(?:/music)?', url, re.IGNORECASE)
    if m:
        base = m.group(1)
        return base if '/music' in url else f"{base}/music"
    return "https://music.yandex.ru"

def parse_yandex_url(url: str):
    """
    Распознаёт тип контента в ссылке Яндекс.Музыки.
    Возвращает (тип, идентификатор, владелец/username) или (None, None, None).
    """
    parsed = urlparse(url)
    path = parsed.path
    query = parse_qs(parsed.query)

    # iframe плейлист
    m = re.search(r'/iframe/playlist/([^/]+)/(\d+)', path)
    if m: return ('iframe_playlist', m.group(2), m.group(1))
    # трек
    m = re.search(r'/track/(\d+)', path)
    if m: return ('track', m.group(1), None)
    # альбом
    m = re.search(r'/album/(\d+)', path)
    if m: return ('album', m.group(1), None)
    # плейлист пользователя
    m = re.search(r'/users/([^/]+)/playlists/(\d+)', path)
    if m: return ('playlist', m.group(2), m.group(1))
    # плейлист по id
    m = re.search(r'/playlist/(\d+)', path)
    if m: return ('playlist', m.group(1), None)
    # плейлист по uuid
    m = re.search(r'/playlists/([a-z0-9\-\.]+)', path)
    if m: return ('uuid_playlist', m.group(1), None)
    # js-обработчик
    if 'handlers/playlist.jsx' in path:
        owner = query.get('owner', [None])[0]
        kinds = query.get('kinds', [None])[0]
        if owner and kinds: return ('playlist', kinds, owner)
    return (None, None, None)


# ======================================================================
# АНИМИРОВАННАЯ ОТПРАВКА СООБЩЕНИЙ
# ======================================================================

async def send_animated_message(bot, chat_id, text, delay=0.4, max_retries=3, **kwargs):
    """
    Отправляет сообщение с эффектом печати (черновик -> реальное сообщение).
    После отправки очищает черновик коротким уведомлением.
    """
    draft_id = int(time.time() * 1000) + random.randint(1, 10000)
    for attempt in range(max_retries):
        try:
            # показываем черновик
            await bot.send_message_draft(chat_id=chat_id, draft_id=draft_id, text=text)
            await asyncio.sleep(delay)
            # отправляем реальное сообщение
            msg = await bot.send_message(chat_id=chat_id, text=text, **kwargs)
            # очищаем черновик
            await bot.send_message_draft(chat_id=chat_id, draft_id=draft_id, text="⏳ Ожидаю новое сообщение")
            return msg
        except Exception as e:
            logger.warning(f"Анимация {attempt+1}: {e}")
            if attempt == max_retries - 1:
                return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
            await asyncio.sleep(0.5 * (attempt + 1))
    return await bot.send_message(chat_id=chat_id, text=text, **kwargs)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает главное меню."""
    await send_animated_message(context.bot, update.effective_chat.id,
                                "🎸 Главное меню:", reply_markup=main_markup)

async def show_main_menu_from_chat(bot, chat_id):
    """Показывает главное меню в произвольном чате."""
    await send_animated_message(bot, chat_id, "🎸 Главное меню:", reply_markup=main_markup)


# ======================================================================
# КОМАНДА /quality
# ======================================================================

async def cmd_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает текущее качество и клавиатуру для его смены."""
    if is_message_too_old(update): return
    current = get_user_quality(context)
    await update.message.reply_text(
        f"🎵 Текущее качество: *{QUALITY_NAMES[current]}*\n\n"
        "Выберите новое качество кнопками ниже:",
        parse_mode='Markdown', reply_markup=quality_markup
    )


# ======================================================================
# КОМАНДА /status (АНИМИРОВАННЫЙ СТАТУС)
# ======================================================================

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Анимированный статус сервера: CPU, память, пинг, очередь загрузок.
    Обновляет черновик несколько раз, затем очищает его.
    """
    if is_message_too_old(update): return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # Если был открыт другой черновик статуса – завершаем его
    old = context.user_data.get('status_draft')
    if old:
        try:
            await context.bot.send_message_draft(chat_id=old['chat_id'], draft_id=old['draft_id'],
                                                 text="⏹️ Статус прерван")
        except: pass
        context.user_data.pop('status_draft', None)

    draft_id = int(time.time() * 1000) + user_id
    try:
        await context.bot.send_message_draft(chat_id=chat_id, draft_id=draft_id,
                                             text="🌸 Секретный блокнот Хитори 🎸\n\nПодожди, собираю данные...")
        context.user_data['status_draft'] = {'draft_id': draft_id, 'chat_id': chat_id}
    except Exception as e:
        logger.error(f"Ошибка запуска черновика: {e}")
        await send_animated_message(context.bot, chat_id, "❌ Не удалось показать анимацию статуса.")
        await show_main_menu(update, context)
        return

    try:
        steps = 8
        anim_frames = ["🎸", "🎧", "🌸", "🎵"]
        for step in range(1, steps + 1):
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory()

            # CPU
            if cpu < 15: c_status = "тихим ожиданием новых задач"
            elif cpu < 45: c_status = "активной проверкой твоих ссылок"
            elif cpu < 80: c_status = "сложными расчетами и очередью"
            else: c_status = "попытками не сломаться от нагрузки"

            # ОЗУ
            if mem.percent < 30: m_status = "приятной пустотой, мне дышится легко"
            elif mem.percent < 70: m_status = "самыми важными вещами, всё под рукой"
            else: m_status = "почти целиком, мне становится тесно"

            res_block = (f"Моё самочувствие 🌸\n"
                         f"• Мысли заняты {c_status} ({cpu}%)\n"
                         f"• Память заполнена {m_status} ({mem.percent}%)\n\n")

            # Пинг
            ping_val = get_ping()
            if ping_val > 0:
                if ping_val < 20: n_lvl = "сейчас просто идеальная"
                elif ping_val < 60: n_lvl = "вполне стабильная"
                elif ping_val < 100: n_lvl = "стала какой-то слабой"
                else: n_lvl = "почти совсем пропала..."
                net_text = f"• Сеть: {n_lvl} ({ping_val} мс до Яндекса)\n\n"
            else:
                net_text = "• Сеть: не могу достучаться до Яндекса...\n\n"

            # Очередь
            q = active_tasks_count
            if q == 0: queue_text = "• Сейчас я свободна, жду новых ссылок 🎸"
            elif q == 1: queue_text = f"• Сейчас меня ждёт {get_plural_tracks(q)}"
            else: queue_text = f"• Сейчас меня ждут {get_plural_tracks(q)}"

            work_block = (f"Очередь и загрузки 📥\n{queue_text}\n"
                          f"• Всего с запуска я скачала треков на {get_formatted_stats()}\n\n")

            live_thoughts = [
                "Так... вроде всё крутится, ничего не задымилось...",
                "Ой, а это что за цифра? Надеюсь, это не важно...",
                "Вентилятор так шумит... тебе не мешает?",
                "Стараюсь записывать всё-всё до единой циферки...",
                "Хух, кажется, я справляюсь... пока что..."
            ]
            footer = f"⏱ Побуду с тобой еще {steps - step} сек...\n{random.choice(live_thoughts)}"
            anim = anim_frames[step % len(anim_frames)]
            status_text = f"🌸 Секретный блокнот Хитори 🎸\n\n{res_block}{net_text}{work_block}{footer}\n\n{anim}"

            for retry in range(2):
                try:
                    await context.bot.send_message_draft(chat_id=chat_id, draft_id=draft_id, text=status_text)
                    break
                except Exception as e:
                    logger.warning(f"Ошибка обновления черновика (шаг {step}, попытка {retry+1}): {e}")
                    if retry == 1:
                        await context.bot.send_message(chat_id, "❌ Ошибка при обновлении статуса.")
                        await context.bot.send_message_draft(chat_id=chat_id, draft_id=draft_id,
                                                             text="📊 Статус завершён")
                        context.user_data.pop('status_draft', None)
                        await show_main_menu(update, context)
                        return
                    await asyncio.sleep(0.5)
            await asyncio.sleep(2)
    finally:
        # гарантированно очищаем черновик
        try:
            await context.bot.send_message_draft(chat_id=chat_id, draft_id=draft_id, text="📊 Статус завершён")
        except: pass
        context.user_data.pop('status_draft', None)

    await show_main_menu(update, context)


# ======================================================================
# ХЕНДЛЕРЫ АВТОРИЗАЦИИ
# ======================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start – приветствие и кнопка «Начать работу»."""
    if is_message_too_old(update): return WAITING_FOR_LINK
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    lock = user_locks.setdefault(user_id, asyncio.Lock())
    async with lock:
        text = (
            "🌸 Привет! Я Боччи… То есть Bocchi Downloader 🎸\n\n"
            "Я живу на сервере и попробую помочь скачать музыку из Яндекс.Музыки.\n\n"
            "✨ Как это работает:\n"
            f"• Можно прислать до {MAX_LINKS} ссылок за раз.\n"
            "• Я буду скачивать всё по очереди, аккуратно…\n\n"
            "⚠️ Высокое качество нагружает сервер. Если я зависну, попробуй понизить качество.\n\n"
            "Нажми кнопку внизу, чтобы войти в аккаунт и начать!"
        )
        await send_animated_message(
            context.bot, chat_id, text,
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🎵 Начать работу")]], resize_keyboard=True)
        )
        return WAITING_FOR_LINK

async def check_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверяет сессию: если токен активен – меню, иначе запрашивает авторизацию."""
    if is_message_too_old(update): return WAITING_FOR_LINK
    user_id = update.effective_user.id
    lock = user_locks.setdefault(user_id, asyncio.Lock())
    async with lock:
        if is_token_valid(context):
            await send_animated_message(context.bot, update.effective_chat.id,
                                        "✅ Токен уже активен! Возвращаюсь в главное меню.",
                                        reply_markup=main_markup)
            return WAITING_FOR_LINK

        auth_text = (
            "🔑 Авторизация\n\n"
            "1️⃣ Перейди по [ссылке](https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41195d)\n"
            "2️⃣ Нажми «Войти» или «Разрешить».\n"
            "3️⃣ Страница может стать пустой — это нормально!\n"
            "4️⃣ Скопируй весь адрес из строки браузера и отправь мне."
        )
        await send_animated_message(context.bot, update.effective_chat.id, auth_text,
                                    parse_mode="Markdown", disable_web_page_preview=True)
        return WAITING_FOR_TOKEN

async def save_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимает токен, проверяет его и сохраняет."""
    if is_message_too_old(update): return WAITING_FOR_TOKEN
    user_id = update.effective_user.id
    raw = update.message.text.strip()
    # ищем y0_... или access_token=
    m = re.search(r"(y0_[a-zA-Z0-9_-]+)", raw)
    if m: token = m.group(1)
    else:
        m = re.search(r"access_token=([^&]+)", raw)
        token = m.group(1) if m else None
    if not token:
        await update.message.reply_text("❌ Не удалось найти токен.")
        return WAITING_FOR_TOKEN
    try: await update.message.delete()
    except: pass
    status_msg = await update.message.reply_text("🔍 Проверяю токен…")
    # попытка 1: ClientAsync
    try:
        client = ClientAsync(token)
        await client.init()
        acc = await client.account_status()
        if acc and acc.account:
            login = acc.account.login
            set_user_token(user_id, token)
            context.user_data['yandex_token'] = token
            context.user_data['token_time'] = time.time()
            await status_msg.edit_text(f"✅ Ура! Я узнала тебя, {login}! Теперь всё готово.")
            await show_main_menu(update, context)
            return WAITING_FOR_LINK
    except Exception as e:
        logger.warning(f"ClientAsync не сработал: {e}")
    # попытка 2: прямой HTTP
    try:
        headers = {"Authorization": f"OAuth {token}"}
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.music.yandex.net/account/status", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    login = data.get("result", {}).get("account", {}).get("login")
                    if login:
                        set_user_token(user_id, token)
                        context.user_data['yandex_token'] = token
                        context.user_data['token_time'] = time.time()
                        await status_msg.edit_text(f"✅ Ура! Я узнала тебя, {login}!")
                        await show_main_menu(update, context)
                        return WAITING_FOR_LINK
    except: pass
    await status_msg.edit_text("❌ Токен не подходит… Попробуй ещё раз.")
    return WAITING_FOR_TOKEN

# ======================================================================
# КОМАНДЫ ВЫХОДА И ОТМЕНЫ
# ======================================================================

async def cmd_logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаляет токен пользователя."""
    if is_message_too_old(update): return
    user_id = update.effective_user.id
    delete_user_token(user_id)
    context.user_data.pop('yandex_token', None)
    context.user_data.pop('token_time', None)
    await send_animated_message(context.bot, update.effective_chat.id, "🔓 Токен удалён. Ты вышел из аккаунта.")
    await send_animated_message(
        context.bot, update.effective_chat.id,
        "Чтобы продолжить, авторизуйся заново.",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🎵 Начать работу")]], resize_keyboard=True)
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик /cancel – завершает текущий диалог."""
    await send_animated_message(
        context.bot, update.effective_chat.id,
        "❌ Действие отменено. Напиши /start, если захочешь начать заново."
    )
    return ConversationHandler.END

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик /menu – показывает главное меню."""
    if is_message_too_old(update): return WAITING_FOR_LINK
    if user_processing.get(update.effective_user.id):
        await update.message.reply_text("⏳ Я пока занята загрузкой…")
        return WAITING_FOR_LINK
    await show_main_menu(update, context)
    return WAITING_FOR_LINK


# ======================================================================
# ОТМЕНА ЗАГРУЗКИ
# ======================================================================

async def cancel_download(update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback=False):
    """
    Отменяет все текущие загрузки пользователя в чате.
    Убивает активный процесс, удаляет статусные сообщения, вычищает задачи из очереди.
    """
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Собираем задачи, принадлежащие этому чату
    tasks_to_cancel = [(tid, info) for tid, info in current_task_info.items() if info['chat_id'] == chat_id]

    if not tasks_to_cancel:
        msg = "❌ Нет активных задач для отмены…"
        if is_callback:
            await update.callback_query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return

    cancelled_count = 0
    for task_id, info in tasks_to_cancel:
        proc = info.get('process')
        task = info['task']
        track_name = task.get('track_name', 'Неизвестный трек')
        batch_type = task.get('batch_type', '')
        batch_name = task.get('batch_name', '')
        batch_idx = task.get('batch_index', 0)
        batch_total = task.get('batch_total', 0)

        # Формируем человекочитаемое описание отменяемого контента
        if batch_type == 'album':
            desc = f"альбома «{batch_name}» (трек {batch_idx} из {batch_total})"
        elif batch_type == 'playlist':
            desc = f"плейлиста «{batch_name}» (трек {batch_idx} из {batch_total})"
        else:
            desc = "загрузки"

        cancel_msg = f"🛑 Отменяю загрузку {desc}. Обрабатывается трек: {track_name}..."
        if is_callback:
            await update.callback_query.edit_message_text(cancel_msg)
        else:
            await update.message.reply_text(cancel_msg)

        # Убиваем процесс загрузки, если он ещё жив
        if proc and not proc.returncode:
            try:
                proc.kill()
                await proc.wait()
            except:
                pass

        # Удаляем статусное сообщение задачи
        msg_id = active_status_msgs.pop(task_id, {}).get('message_id')
        if msg_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except:
                pass

        current_task_info.pop(task_id, None)
        cancelled_count += 1

    # Убираем оставшиеся задачи этого пользователя из очереди
    remaining = []
    removed_from_queue = 0
    while not download_queue.empty():
        try:
            t = download_queue.get_nowait()
            if t.get('user_id') != user_id:
                remaining.append(t)
            else:
                removed_from_queue += 1
        except asyncio.QueueEmpty:
            break
    for t in remaining:
        await download_queue.put(t)

    # Обновляем глобальный счётчик активных задач
    global active_tasks_count
    active_tasks_count -= (cancelled_count + removed_from_queue)
    if active_tasks_count < 0:
        active_tasks_count = 0

    save_queue_state()
    total = cancelled_count + removed_from_queue
    msg = f"✅ Загрузка отменена. Отменено задач: {total}."
    if is_callback:
        await update.callback_query.edit_message_text(msg)
    else:
        await update.message.reply_text(msg)

    await show_main_menu_from_chat(context.bot, chat_id)

async def cancel_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline-кнопки отмены загрузки."""
    await cancel_download(update, context, is_callback=True)


# ======================================================================
# ЭКСТРЕННАЯ ОСТАНОВКА И ПЕРЕЗАПУСК ЗАВИСШЕЙ ЗАДАЧИ
# ======================================================================

async def emergency_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принудительно убивает все процессы, очищает очередь и сбрасывает счётчики."""
    chat_id = update.effective_chat.id
    await update.message.reply_text("🛑 Экстренная остановка… Убиваю процессы и чищу очередь.")

    for task_id, info in list(current_task_info.items()):
        proc = info.get('process')
        if proc and not proc.returncode:
            try:
                proc.kill()
                await proc.wait()
            except:
                pass
        msg_id = active_status_msgs.pop(task_id, {}).get('message_id')
        if msg_id:
            try:
                await context.bot.delete_message(chat_id=info['chat_id'], message_id=msg_id)
            except:
                pass
    current_task_info.clear()

    while not download_queue.empty():
        try:
            download_queue.get_nowait()
        except asyncio.QueueEmpty:
            break

    global active_tasks_count
    active_tasks_count = 0
    save_queue_state()
    save_active_msgs()

    await update.message.reply_text("✅ Экстренная остановка выполнена. Используй /start для перезапуска.")
    await show_main_menu_from_chat(context.bot, chat_id)

async def restart_stuck_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перезапускает зависшую задачу по нажатию inline-кнопки."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    for task_id, info in current_task_info.items():
        if info['chat_id'] == chat_id:
            proc = info.get('process')
            if proc and not proc.returncode:
                try:
                    proc.kill()
                    await proc.wait()
                except:
                    pass
            # Удаляем статусное сообщение
            msg_id = active_status_msgs.pop(task_id, {}).get('message_id')
            if msg_id:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                except:
                    pass
            task = info['task']
            current_task_info.pop(task_id)
            await download_queue.put(task)
            global active_tasks_count
            active_tasks_count += 1
            await query.edit_message_text(f"🔄 Задача «{task['track_name']}» перезапущена. Продолжаю загрузку…")
            return

    await query.edit_message_text("❌ Нет зависших задач для этого чата.")


# ======================================================================
# ГЛАВНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ (С ЗАЩИТОЙ ОТ СПАМА КОМАНД)
# ======================================================================

async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Центральный обработчик всех текстовых сообщений.
    Определяет, является ли сообщение командой меню или ссылкой,
    и выполняет соответствующее действие.
    """
    if is_message_too_old(update):
        return WAITING_FOR_LINK

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = update.message.text

    # ---------- ЗАЩИТА ОТ ЧАСТЫХ КОМАНД МЕНЮ ----------
    menu_commands = [
        "🎵 Начать работу", "▶ Начать загрузку", "🔓 Удалить токен",
        "🔄 Обновить токен", "🎵 Качество", "📊 Статус",
        "⏹ Отменить загрузку", "🆘 Экстренная остановка"
    ] + list(QUALITY_BUTTONS.keys())   # кнопки выбора качества тоже считаются командами

    if text in menu_commands:
        now = time.time()
        last_time = last_command_time.get(user_id, 0)
        if now - last_time < COMMAND_COOLDOWN:
            # Команда пришла слишком быстро – удаляем сообщение и молча выходим
            try:
                await update.message.delete()
            except:
                pass
            return WAITING_FOR_LINK
        # Запоминаем время выполнения команды
        last_command_time[user_id] = now

    # Защита от повторной обработки того же сообщения
    msg_id = update.message.message_id
    if last_processed_msg.get(user_id) == msg_id:
        return WAITING_FOR_LINK
    last_processed_msg[user_id] = msg_id

    # ---------- ОБРАБОТКА КОМАНД МЕНЮ ----------
    if text == "🎵 Начать работу":
        return await check_session(update, context)
    if text == "▶ Начать загрузку":
        await send_animated_message(context.bot, chat_id, "🎵 Присылай ссылки на треки, альбомы или плейлисты.")
        return WAITING_FOR_LINK
    if text == "🔓 Удалить токен":
        await cmd_logout(update, context)
        return WAITING_FOR_LINK
    if text == "🔄 Обновить токен":
        await send_animated_message(context.bot, chat_id, "🔑 Пожалуйста, отправь новый токен.")
        return WAITING_FOR_TOKEN
    if text == "🎵 Качество":
        await cmd_quality(update, context)
        return WAITING_FOR_LINK
    if text == "📊 Статус":
        await cmd_status(update, context)
        return WAITING_FOR_LINK
    if text == "⏹ Отменить загрузку":
        await cancel_download(update, context, is_callback=False)
        return WAITING_FOR_LINK
    if text == "🆘 Экстренная остановка":
        await emergency_stop(update, context)
        return WAITING_FOR_LINK
    if text in QUALITY_BUTTONS:
        new_q = QUALITY_BUTTONS[text]
        if set_user_quality(context, new_q):
            await update.message.reply_text(
                f"✅ Качество изменено на *{QUALITY_NAMES[new_q]}*.\n\n"
                "⚠️ Высокое качество нагружает сервер.",
                parse_mode='Markdown', reply_markup=main_markup
            )
        else:
            await update.message.reply_text("❌ Не получилось сменить качество.")
        return WAITING_FOR_LINK

    # ---------- ОБРАБОТКА ПОТЕНЦИАЛЬНЫХ ССЫЛОК ----------
    message = update.message

    # Извлечение ссылки из HTML-кода (например, iframe)
    if 'iframe' in text and 'music.yandex' in text:
        src_match = re.search(r'src="(https?://music\.yandex\.[a-z]{2,3}/[^"]+)"', text, re.IGNORECASE)
        if src_match:
            text = src_match.group(1)
            await context.bot.send_message(chat_id, "🔍 Нашла в коде ссылку на плейлист. Продолжаю…",
                                           reply_to_message_id=message.message_id)
        else:
            await context.bot.send_message(chat_id, "❌ Не удалось найти ссылку в HTML-коде.")
            return WAITING_FOR_LINK

    # Проверяем, есть ли у пользователя действующий токен
    if not is_token_valid(context):
        try:
            await message.delete()
        except:
            pass
        now = time.time()
        last_warn = last_auth_warning.get(user_id, 0)
        if now - last_warn > WARNING_COOLDOWN:
            last_auth_warning[user_id] = now
            await send_animated_message(
                context.bot, chat_id,
                "🔑 Требуется авторизация. Используй /start или кнопку «🎵 Начать работу»."
            )
        return WAITING_FOR_TOKEN

    # Ищем все ссылки в сообщении (включая caption)
    content = text + " " + (update.message.caption or "")
    url_pattern = re.compile(r'https?://(?:[a-z0-9-]+\.)*yandex\.[a-z]{2,3}(?:/music)?(?:/[^\s]+)?', re.IGNORECASE)
    urls = url_pattern.findall(content)
    valid_urls = []
    for u in urls:
        u = u.rstrip('.,!?;:()[]{}"\'')
        if parse_yandex_url(u)[0] is not None:
            valid_urls.append(u)

    if not valid_urls:
        await context.bot.send_message(chat_id, "❌ Я не смогла распознать ссылку…")
        return WAITING_FOR_LINK

    # Добавляем ссылки в накопитель и запускаем отложенную обработку
    link_accumulators.setdefault(user_id, []).extend(valid_urls)
    if user_processing.get(user_id):
        await context.bot.send_message(chat_id, "🔄 Я пока занята предыдущей загрузкой… Подожди немножко.")
        try:
            await message.delete()
        except:
            pass
        return WAITING_FOR_LINK

    async def safe_process():
        await asyncio.sleep(ACCUMULATION_DELAY)
        token = get_user_token(user_id)
        if not token:
            await context.bot.send_message(chat_id, "❌ Токен исчез… Авторизуйся заново.")
            return
        try:
            await process_accumulated_links(user_id, chat_id, context, token)
        except Exception as e:
            logger.error(f"Ошибка обработки ссылок: {e}", exc_info=True)
            await context.bot.send_message(chat_id, f"❌ Ой-ой… Что-то пошло не так: {str(e)[:200]}")
        finally:
            user_processing.pop(user_id, None)
            link_accumulators.pop(user_id, None)

    user_delay_tasks[user_id] = asyncio.create_task(safe_process())

    confirm_msg = await context.bot.send_message(chat_id, "📎 Я приняла ссылки… Сейчас посчитаю и начну готовить.",
                                                 reply_to_message_id=message.message_id)
    try:
        await message.delete()
    except:
        pass

    async def delete_confirm():
        await asyncio.sleep(5)
        try:
            await confirm_msg.delete()
        except:
            pass
    asyncio.create_task(delete_confirm())

    return WAITING_FOR_LINK


# ======================================================================
# ОБРАБОТКА НАКОПЛЕННЫХ ССЫЛОК (ПАКЕТНАЯ)
# ======================================================================

def make_track_dict(track, base_url: str, original_url: str,
                    batch_type=None, batch_name=None, batch_artist=None, batch_owner=None,
                    total=0, cover_bytes=None, album=None, year=None, genre=None):
    """
    Создаёт универсальный словарь с информацией о треке.
    track может быть объектом библиотеки yandex_music или словарём из API плейлиста.
    """
    if isinstance(track, dict):
        # Данные из плейлиста (HTTP API)
        artist = ', '.join(a.get('name', '') for a in track.get('artists', [])) or "Неизвестен"
        title = track.get('title', 'Неизвестный трек')
        version = track.get('version') or track.get('subtitle')
        if version:
            title += f" ({version})"
        tid = track['id']
        duration = track.get('duration_ms', 0) // 1000
    else:
        # Объект из библиотеки yandex_music
        artist = ', '.join(a.name for a in track.artists) if track.artists else "Неизвестен"
        title = track.title
        if track.version:
            title += f" ({track.version})"
        tid = track.id
        duration = track.duration_ms // 1000 if track.duration_ms else 0

    return {
        'url': f"{base_url}/track/{tid}",
        'artist': artist,
        'title': title,
        'duration': duration,
        'track_name': f"{artist} — {title}",
        'cover_bytes': cover_bytes,
        'album': album,
        'year': year,
        'genre': genre,
        'batch_type': batch_type,
        'batch_name': batch_name,
        'batch_artist': batch_artist,
        'batch_owner': batch_owner,
        'batch_total': total
    }


async def process_accumulated_links(user_id, chat_id, context, token):
    """
    Разбирает все накопленные ссылки пользователя, получает список треков,
    формирует задания и добавляет их в общую очередь загрузки.
    """
    user_processing[user_id] = True

    raw_links = list(dict.fromkeys(link_accumulators.pop(user_id, [])))[:MAX_LINKS]
    if not raw_links:
        user_processing.pop(user_id, None)
        return

    logger.info(f"Обработка ссылок от {user_id}: {raw_links}")

    # Инициализация клиента Яндекс.Музыки
    try:
        client = ClientAsync(token)
        await client.init()
    except Exception as e:
        logger.error(f"Ошибка создания клиента: {e}")
        await context.bot.send_message(chat_id, "❌ Ошибка авторизации. Попробуй снова.")
        user_processing.pop(user_id, None)
        return

    all_tracks = []
    for url in raw_links:
        base_url = extract_base_url(url)
        type_, id_, username = parse_yandex_url(url)
        if not type_:
            await context.bot.send_message(chat_id, f"❌ Не удалось распознать ссылку: {url}")
            continue

        try:
            if type_ == 'track':
                tracks_info = await client.tracks([id_])
                if tracks_info and tracks_info[0]:
                    t = tracks_info[0]
                    all_tracks.append(make_track_dict(t, base_url, url))
                else:
                    await context.bot.send_message(chat_id, f"❌ Трек не найден: {url}")
            elif type_ == 'album':
                album = await client.albums_with_tracks(id_)
                if album and album.volumes:
                    album_title = album.title or "Неизвестный альбом"
                    album_artist = ', '.join(a.name for a in album.artists) if album.artists else 'Разные исполнители'
                    track_list = []
                    for volume in album.volumes:
                        for track in volume:
                            if track:
                                track_list.append(make_track_dict(track, base_url, url,
                                                                  batch_type='album',
                                                                  batch_name=album_title,
                                                                  batch_artist=album_artist,
                                                                  total=len(volume)))
                    all_tracks.extend(track_list)
                else:
                    await context.bot.send_message(chat_id, f"❌ Альбом не найден: {url}")
            elif type_ in ('playlist', 'uuid_playlist', 'iframe_playlist'):
                async with aiohttp.ClientSession() as session:
                    headers = {"Authorization": f"OAuth {token}"}
                    api_url = f"https://api.music.yandex.net/playlist/{id_}"
                    async with session.get(api_url, headers=headers) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            playlist = data.get("result")
                            if playlist:
                                playlist_title = playlist.get('title', 'Неизвестный плейлист')
                                owner = playlist.get('owner', {})
                                owner_name = owner.get('name') or owner.get('login') or 'Неизвестный'
                                tracks_data = playlist.get('tracks', [])
                                track_list = []
                                for idx, item in enumerate(tracks_data, 1):
                                    track = item.get('track')
                                    if track and track.get('id'):
                                        track_list.append(make_track_dict(track, base_url, url,
                                                                          batch_type='playlist',
                                                                          batch_name=playlist_title,
                                                                          batch_owner=owner_name,
                                                                          total=len(tracks_data)))
                                all_tracks.extend(track_list)
                            else:
                                await context.bot.send_message(chat_id, f"❌ Плейлист пуст: {url}")
                        else:
                            await context.bot.send_message(chat_id, f"❌ Плейлист недоступен (возможно, приватный).")
        except Exception as e:
            logger.error(f"Ошибка парсинга {url}: {e}")
            await context.bot.send_message(chat_id, f"❌ Ошибка при обработке {url}")

    if not all_tracks:
        await context.bot.send_message(chat_id, "❌ Не удалось найти треки по ссылкам.")
        user_processing.pop(user_id, None)
        return

    total = len(all_tracks)
    batch_id = f"{user_id}_{int(time.time())}_{uuid.uuid4().hex[:8]}"

    queue_pos = download_queue.qsize() + 1
    await context.bot.send_message(
        chat_id,
        f"📥 Я получила {get_plural_tracks(total)}. Твоя очередь — номер {queue_pos}…"
    )

    for idx, track_info in enumerate(all_tracks, 1):
        task_item = {
            'chat_id': chat_id,
            'url': track_info['url'],
            'token': token,
            'artist': track_info['artist'],
            'title': track_info['title'],
            'duration': track_info['duration'],
            'track_name': track_info['track_name'],
            'quality': get_user_quality(context),
            'batch_id': batch_id,
            'batch_index': idx,
            'batch_total': total,
            'batch_type': track_info.get('batch_type'),
            'batch_name': track_info.get('batch_name'),
            'batch_artist': track_info.get('batch_artist'),
            'batch_owner': track_info.get('batch_owner'),
            'user_id': user_id,
            'cover_bytes': track_info.get('cover_bytes'),
            'album': track_info.get('album'),
            'year': track_info.get('year'),
            'genre': track_info.get('genre')
        }
        await download_queue.put(task_item)

    global active_tasks_count
    active_tasks_count += total
    save_queue_state()
    user_processing.pop(user_id, None)


# ======================================================================
# СОХРАНЕНИЕ И ВОССТАНОВЛЕНИЕ ОЧЕРЕДИ ЗАГРУЗОК
# ======================================================================

def save_queue_state():
    """Сохраняет все невыполненные задачи из очереди в JSON."""
    tasks = []
    while not download_queue.empty():
        try:
            tasks.append(download_queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    # Возвращаем задачи обратно в очередь
    for t in tasks:
        download_queue.put_nowait(t)
    # Сериализуем без cover_bytes (они не сохраняются)
    serial = [{k: v for k, v in t.items() if k != 'cover_bytes'} for t in tasks]
    try:
        with open(QUEUE_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(serial, f, ensure_ascii=False, indent=2)
        logger.info(f"Сохранено задач в очереди: {len(tasks)}")
    except Exception as e:
        logger.error(f"Ошибка сохранения очереди: {e}")

def load_queue_state():
    """Загружает сохранённые задачи из файла (если он есть)."""
    if not os.path.exists(QUEUE_STATE_FILE):
        return
    try:
        with open(QUEUE_STATE_FILE, 'r', encoding='utf-8') as f:
            tasks = json.load(f)
        valid_tasks = []
        for task in tasks:
            uid = task.get('user_id')
            if uid:
                token = get_user_token(uid)
                if token:
                    task['token'] = token
                    task['cover_bytes'] = None
                    valid_tasks.append(task)
                else:
                    logger.warning(f"Пропущена задача для {uid}: нет токена")
        for t in valid_tasks:
            download_queue.put_nowait(t)
        os.remove(QUEUE_STATE_FILE)
        logger.info(f"Восстановлено задач из очереди: {len(valid_tasks)}")
    except Exception as e:
        logger.error(f"Ошибка загрузки очереди: {e}")


# ======================================================================
# ВОРКЕР (СКАЧИВАНИЕ, ОБРАБОТКА ТЕГОВ, ОТПРАВКА)
# ======================================================================

async def worker_loop(app):
    """
    Бесконечный цикл, обрабатывающий очередь загрузок.
    Скачивает трек, добавляет теги, обложку, отправляет в чат.
    """
    global worker_busy, active_tasks_count
    chat_temp_msg = {}   # временные сообщения по чатам (чтобы не засорять)

    while True:
        if not shutil.which(DOWNLOADER_PATH):
            logger.error(f"Загрузчик {DOWNLOADER_PATH} не найден!")
            await asyncio.sleep(60)
            continue

        try:
            task = await download_queue.get()
            worker_busy = True
            tmp_dir = Path(f"bocchi_tmp_{uuid.uuid4().hex}")
            current_quality = task.get('quality', DEFAULT_QUALITY)
            task_id = f"{task['batch_id']}_{task['batch_index']}"
            chat_id = task['chat_id']

            async with download_semaphore:
                status_msg = None
                downloader_process = None
                stuck_notified = False
                success = False
                actual_quality_used = current_quality
                try:
                    # Удаляем предыдущие сообщения статуса этого же чата/задачи
                    old = active_status_msgs.pop(task_id, None)
                    if old:
                        try:
                            await app.bot.delete_message(chat_id=old['chat_id'], message_id=old['message_id'])
                        except:
                            pass
                    prev = chat_temp_msg.pop(chat_id, None)
                    if prev:
                        try:
                            await app.bot.delete_message(chat_id=chat_id, message_id=prev)
                        except:
                            pass

                    tmp_dir.mkdir(exist_ok=True)

                    # Кнопка отмены под статусным сообщением
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("⏹ Отменить загрузку", callback_data="cancel_download")]
                    ])

                    batch_type = task.get('batch_type')
                    batch_name = task.get('batch_name')
                    batch_artist = task.get('batch_artist')
                    batch_owner = task.get('batch_owner')
                    batch_index = task.get('batch_index', 1)
                    batch_total = task.get('batch_total', 1)

                    # Формируем заголовок статуса
                    header = ""
                    if batch_type == 'album':
                        header = f"📀 Альбом: {batch_name}\n🎤 {batch_artist}\n"
                    elif batch_type == 'playlist':
                        header = f"📋 Плейлист: {batch_name}\n👤 {batch_owner}\n"
                    elif batch_total > 1:
                        header = f"📦 Пакет треков ({batch_total} шт.)\n"

                    progress = f"({batch_index} из {batch_total})" if batch_total > 1 else ""
                    status_text = (
                        f"🌀 Обрабатываю… {progress}\n"
                        f"{header}"
                        f"🎵 Трек: {task['track_name']}\n"
                        f"⚙️ Качество: {QUALITY_NAMES[current_quality]}"
                    )
                    status_msg = await app.bot.send_message(chat_id, status_text, reply_markup=keyboard)
                    active_status_msgs[task_id] = {"chat_id": chat_id, "message_id": status_msg.message_id}
                    save_active_msgs()

                    await app.bot.send_chat_action(chat_id, ChatAction.TYPING)
                    start_time = time.time()
                    current_task_info[task_id] = {
                        "start_time": start_time,
                        "chat_id": chat_id,
                        "task": task,
                        "process": None,
                        "status_msg_id": status_msg.message_id
                    }

                    # Функция запуска загрузчика
                    async def run_downloader(quality, tmp_path):
                        nonlocal downloader_process
                        cmd = [
                            DOWNLOADER_PATH,
                            "--token", task['token'],
                            "--quality", str(quality),
                            "--embed-cover",
                            "--cover-resolution", "original",
                            "--lyrics-format", "lrc",
                            "--dir", str(tmp_path),
                            "--url", task['url'],
                            "--path-pattern", "#artist - #title",
                            "--delay", "3",
                            "--skip-existing",
                            "--only-music"
                        ]
                        proc = await asyncio.create_subprocess_exec(
                            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                        )
                        downloader_process = proc
                        current_task_info[task_id]['process'] = proc
                        try:
                            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=DOWNLOAD_TIMEOUT)
                            return proc.returncode, stdout, stderr
                        except asyncio.TimeoutError:
                            proc.kill()
                            return -1, b'', b'Timeout'

                    # Попытки скачивания (до 3) с возможным понижением качества
                    for attempt in range(3):
                        if time.time() - start_time > STUCK_TIMEOUT and not stuck_notified:
                            stuck_notified = True
                            new_keyboard = InlineKeyboardMarkup([
                                [InlineKeyboardButton("⏹ Отменить загрузку", callback_data="cancel_download")],
                                [InlineKeyboardButton("🔄 Перезапустить загрузчик", callback_data="restart_stuck_task")]
                            ])
                            try:
                                await app.bot.edit_message_reply_markup(chat_id, status_msg.message_id, reply_markup=new_keyboard)
                            except:
                                pass

                        # Проверка места на диске
                        enough, free_mb = check_disk_space()
                        if not enough:
                            if current_quality > 0:
                                new_q = current_quality - 1
                                await app.bot.send_message(chat_id, f"⚠️ Мало места! Понижаю качество до {QUALITY_NAMES[new_q]}.")
                                current_quality = new_q
                                continue
                            else:
                                await app.bot.send_message(chat_id, "❌ Недостаточно места даже для низкого качества.")
                                break

                        returncode, stdout, stderr = await run_downloader(current_quality, tmp_dir)
                        if returncode == 0:
                            success = True
                            actual_quality_used = current_quality
                            break

                        stderr_text = stderr.decode('utf-8', errors='replace')
                        logger.warning(f"Попытка {attempt+1}: код {returncode}, stderr: {stderr_text[:200]}")

                        shutil.rmtree(tmp_dir, ignore_errors=True)
                        tmp_dir.mkdir(exist_ok=True)

                        if returncode == -9:  # нехватка памяти
                            if current_quality > 0:
                                current_quality -= 1
                                await app.bot.send_message(chat_id, "⚠️ Нехватка памяти. Понижаю качество.")
                                continue
                            else:
                                await app.bot.send_message(chat_id, "❌ Недостаточно памяти даже для низкого качества.")
                                break

                        if any(k in stderr_text.lower() for k in ['forbidden', 'blocked', 'denied', 'регион', 'недоступен', '403']):
                            await app.bot.send_message(chat_id, f"❌ Трек заблокирован Яндексом: {task['track_name']}")
                            break

                        if attempt == 2:
                            await app.bot.send_message(chat_id, f"❌ Не удалось скачать {task['track_name']}.")
                        else:
                            await asyncio.sleep(5)

                    if not success:
                        current_task_info.pop(task_id, None)
                        continue

                    # Уведомление, если качество было снижено
                    if actual_quality_used != task.get('quality', DEFAULT_QUALITY):
                        await app.bot.send_message(chat_id, f"🎵 Трек скачан в качестве: {QUALITY_NAMES[actual_quality_used]}.")

                    # Поиск скачанных файлов
                    files = list(tmp_dir.rglob('*.mp3')) + list(tmp_dir.rglob('*.m4a'))
                    for f_path in files:
                        file_size_mb = f_path.stat().st_size / (1024 * 1024)
                        artist = task.get('artist', 'Неизвестен')
                        title = task.get('title', f_path.stem)
                        album = task.get('album')
                        year = task.get('year')
                        genre = task.get('genre')
                        cover_bytes = task.get('cover_bytes')

                        # Читаем тексты песен из .lrc
                        lyrics = None
                        lrc_file = f_path.with_suffix('.lrc')
                        if lrc_file.exists():
                            try:
                                lyrics = lrc_file.read_text(encoding='utf-8').strip()
                            except:
                                pass

                        # Записываем теги
                        try:
                            if f_path.suffix.lower() == '.m4a':
                                audio = MP4(f_path)
                                audio['\xa9ART'] = [artist]
                                audio['\xa9nam'] = [title]
                                if album: audio['\xa9alb'] = [album]
                                if year: audio['\xa9day'] = [str(year)]
                                if genre: audio['\xa9gen'] = [genre]
                                audio.pop('\xa9cmt', None)
                                if lyrics: audio['\xa9lyr'] = [lyrics]
                                if cover_bytes:
                                    compressed = compress_cover(cover_bytes, 300*1024)
                                    if compressed:
                                        audio['covr'] = [MP4Cover(compressed, imageformat=MP4Cover.FORMAT_JPEG)]
                                audio.save()
                            else:
                                audio = MP3(f_path, ID3=ID3)
                                if audio.tags is None:
                                    audio.add_tags()
                                easy = EasyID3(f_path)
                                easy['artist'] = artist
                                easy['title'] = title
                                if album: easy['album'] = album
                                easy.save()
                                audio.tags.add(TPE2(encoding=3, text=artist))
                                audio.tags.delall('COMM')
                                if year: audio.tags.add(TDRC(encoding=3, text=str(year)))
                                if genre: audio.tags.add(TCON(encoding=3, text=genre))
                                if lyrics: audio.tags.add(USLT(encoding=3, lang='rus', desc='Lyrics', text=lyrics))
                                if cover_bytes:
                                    compressed = compress_cover(cover_bytes, 300*1024)
                                    if compressed:
                                        audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=compressed))
                                audio.save()
                        except Exception as tag_e:
                            logger.error(f"Ошибка записи тегов: {tag_e}")

                        # Определяем финальное имя файла
                        safe_name = re.sub(r'[\\/*?:"<>|]', "", f"{artist} - {title}{f_path.suffix}")
                        final_path = f_path.with_name(safe_name)
                        f_path.rename(final_path)

                        # Извлекаем обложку для миниатюры
                        thumb = None
                        embedded_cover = extract_cover_from_audio(final_path) or cover_bytes
                        if embedded_cover:
                            thumb = compress_cover(embedded_cover, 200*1024) if len(embedded_cover) > 200*1024 else embedded_cover

                        # Отправка в Telegram
                        if file_size_mb > 49.0:
                            uploaded = False
                            try:
                                litterbox = LitterboxClient()
                                url = await asyncio.wait_for(asyncio.to_thread(litterbox.upload_file, str(final_path), expire_time="24h"), timeout=CLOUD_TIMEOUT)
                                if url:
                                    await app.bot.send_message(chat_id, f"🎁 Ссылка (24ч):\n{url}", disable_web_page_preview=True)
                                    uploaded = True
                            except:
                                pass
                            if not uploaded:
                                try:
                                    catbox = AsyncCatboxClient()
                                    url = await asyncio.wait_for(catbox.upload(str(final_path)), timeout=CLOUD_TIMEOUT)
                                    if url:
                                        await app.bot.send_message(chat_id, f"🎁 Постоянная ссылка:\n{url}", disable_web_page_preview=True)
                                        uploaded = True
                                except:
                                    pass
                            if not uploaded:
                                await app.bot.send_message(chat_id, "❌ Не удалось загрузить файл в облако.")
                        else:
                            try:
                                with open(final_path, 'rb') as af:
                                    await app.bot.send_audio(
                                        chat_id=chat_id,
                                        audio=af,
                                        performer=artist,
                                        title=title,
                                        duration=get_audio_duration(final_path),
                                        filename=safe_name,
                                        thumbnail=thumb,
                                        read_timeout=600, write_timeout=600
                                    )
                            except Exception as e:
                                logger.error(f"Ошибка отправки аудио: {e}")
                                await app.bot.send_message(chat_id, f"❌ Не удалось отправить {safe_name}.")

                        add_stats(final_path.stat().st_size)
                        await asyncio.sleep(TRACK_DELAY_SECONDS)
                        gc.collect()

                    # Финальное сообщение после обработки всего пакета
                    if batch_total and batch_index == batch_total:
                        if batch_type == 'album':
                            finish = f"🎸 Альбом «{batch_name}» полностью загружен!"
                        elif batch_type == 'playlist':
                            finish = "🎸 Плейлист полностью загружен!"
                        else:
                            finish = "🎸 Все треки обработаны!"
                        await app.bot.send_message(
                            chat_id,
                            'Загружено при поддержке #BocchiIsAlive <tg-emoji emoji-id="6041593232423391328">💠</tg-emoji>',
                            parse_mode='HTML'
                        )
                        await app.bot.send_message(chat_id, finish, reply_markup=main_markup)

                except Exception as e:
                    logger.error(f"Ошибка воркера: {e}", exc_info=True)
                    await app.bot.send_message(chat_id, f"❌ Ошибка: {str(e)[:200]}")
                finally:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                    worker_busy = False
                    current_task_info.pop(task_id, None)
                    active_status_msgs.pop(task_id, None)
                    if status_msg:
                        try:
                            await status_msg.delete()
                        except:
                            pass
                    save_active_msgs()
                    save_queue_state()
                    active_tasks_count -= 1
        except Exception as e:
            logger.critical(f"Крах воркера: {e}")
            await asyncio.sleep(10)


# ======================================================================
# ФОНОВЫЕ ЗАДАЧИ (ОЧИСТКА ПАМЯТИ, ПРОВЕРКА ТОКЕНОВ)
# ======================================================================

async def memory_cleaner():
    """Периодически вызывает сборщик мусора, если ОЗУ загружена более чем на 50%."""
    while True:
        await asyncio.sleep(300)   # каждые 5 минут
        if psutil.virtual_memory().percent > 50:
            gc.collect()
            logger.info("Принудительная очистка памяти")

async def check_all_tokens(app):
    """Удаляет токены, чей срок жизни истёк."""
    now = time.time()
    changed = False
    for uid, data in list(user_tokens.items()):
        if now - data['timestamp'] > TOKEN_LIFETIME:
            del user_tokens[uid]
            changed = True
    if changed:
        save_user_tokens()


# ======================================================================
# ИНИЦИАЛИЗАЦИЯ И ЗАПУСК БОТА
# ======================================================================

async def post_init(app):
    """Настраивает глобальные объекты и запускает фоновые задачи после старта."""
    global download_semaphore, download_queue, worker_task, token_checker_task, memory_cleaner_task
    download_semaphore = asyncio.Semaphore(1)
    download_queue = asyncio.Queue()
    load_user_tokens()
    load_active_msgs()
    load_pending_tasks()
    load_queue_state()
    await cleanup_orphan_messages(app)
    worker_task = asyncio.create_task(worker_loop(app))
    memory_cleaner_task = asyncio.create_task(memory_cleaner())

    async def periodic_token_check():
        while True:
            await asyncio.sleep(900)
            await check_all_tokens(app)
    token_checker_task = asyncio.create_task(periodic_token_check())


def main():
    """Точка входа: создание приложения, регистрация хендлеров, запуск polling."""
    global worker_task, token_checker_task, memory_cleaner_task
    cleanup_old_tmp_dirs()
    if not os.path.exists(STATS_FILE):
        with open(STATS_FILE, "w") as f:
            f.write("0")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    # Inline-кнопки
    app.add_handler(CallbackQueryHandler(restart_stuck_task_callback, pattern="restart_stuck_task"))
    app.add_handler(CallbackQueryHandler(cancel_download_callback, pattern="cancel_download"))

    # ConversationHandler (состояния авторизации и получения ссылок)
    conv = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            MessageHandler(filters.Regex('^🎵 Начать работу$'), handle_download)
        ],
        states={
            WAITING_FOR_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_token)],
            WAITING_FOR_LINK: [MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_download)],
        },
        fallbacks=[CommandHandler('start', start), CommandHandler('cancel', cancel), CommandHandler('menu', menu)]
    )
    app.add_handler(CommandHandler('logout', cmd_logout))
    app.add_handler(CommandHandler('menu', menu))
    app.add_handler(CommandHandler('cancel', cancel))
    app.add_handler(CommandHandler('quality', cmd_quality))
    app.add_handler(CommandHandler('status', cmd_status))
    app.add_handler(CommandHandler('stop', emergency_stop))
    app.add_handler(conv)

    try:
        app.run_polling()
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
    finally:
        for t in [token_checker_task, worker_task, memory_cleaner_task]:
            if t:
                t.cancel()

if __name__ == "__main__":
    main()
