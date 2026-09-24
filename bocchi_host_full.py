# (c) 2026 Hanako
# Bocchi Downloader (Server Edition)
# Работает с python-telegram-bot 21.6

import asyncio
import contextlib
import gc
import io
import json
import logging
import os
import random
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import aiohttp
import psutil
from PIL import Image
from dotenv import load_dotenv
from mutagen import File
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, USLT, TDRC, TCON, APIC, TPE2
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, ConversationHandler, filters
)
from yandex_music import ClientAsync

# ---------------------- НАСТРОЙКА ЛОГИРОВАНИЯ ----------------------
logging.getLogger("httpx").setLevel(logging.WARNING)
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(message)s')
logger = logging.getLogger("BocchiStation")

# ---------------------- ПАПКА ДЛЯ ДАННЫХ ----------------------
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)


def _resolve_stats_file_path(raw_stats_file: str) -> Path:
    base_dir = DATA_DIR.resolve()
    default_path = (base_dir / "stats.txt").resolve()
    safe_stats_file = raw_stats_file.replace("\r", "").replace("\n", "")

    raw_path = Path(raw_stats_file)
    if raw_path.is_absolute():
        logger.warning("Небезопасный STATS_FILE '%s', используется значение по умолчанию.", safe_stats_file)
        return default_path

    safe_parts = []
    for part in raw_path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            logger.warning("Небезопасный STATS_FILE '%s', используется значение по умолчанию.", safe_stats_file)
            return default_path
        safe_parts.append(part)

    candidate = (base_dir / Path(*safe_parts)).resolve()

    if candidate == base_dir or base_dir in candidate.parents:
        return candidate

    logger.warning("Небезопасный STATS_FILE '%s', используется значение по умолчанию.", safe_stats_file)
    return default_path


# ---------------------- КОНФИГУРАЦИЯ ----------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТОКЕН_ЗДЕСЬ")
DOWNLOADER_PATH = os.getenv("DOWNLOADER_PATH", "yandex-music-downloader")
STATS_FILE = os.getenv("STATS_FILE", "data/stats.txt")
STATS_FILE_PATH = _resolve_stats_file_path(STATS_FILE)
MAX_LINKS = int(os.getenv("MAX_LINKS", "10"))
DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", "600"))
TOKEN_LIFETIME = int(os.getenv("TOKEN_LIFETIME", "86400"))
CLOUD_TIMEOUT = int(os.getenv("CLOUD_TIMEOUT", "120"))
DEFAULT_QUALITY = int(os.getenv("DEFAULT_QUALITY", "2"))
MIN_FREE_DISK_MB = int(os.getenv("MIN_FREE_DISK_MB", "20"))
TRACK_DELAY_SECONDS = float(os.getenv("TRACK_DELAY_SECONDS", "5.0"))
STUCK_TIMEOUT = int(os.getenv("STUCK_TIMEOUT", "120"))
ACCUMULATION_DELAY = float(os.getenv("ACCUMULATION_DELAY", "5.0"))
LINK_SUBMIT_COOLDOWN = float(os.getenv("LINK_SUBMIT_COOLDOWN", "30"))
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "3"))
MAX_TRACKS_PER_USER = int(os.getenv("MAX_TRACKS_PER_USER", "50"))
MONITORING_URL = os.getenv("MONITORING_URL", "http://185.170.153.38:61209")

# ---------------------- ФАЙЛЫ СОСТОЯНИЯ ----------------------
QUEUE_STATE_FILE = "data/download_queue_state.json"
USER_TOKENS_FILE = "data/user_tokens.json"
ACTIVE_MSGS_FILE = "data/active_status_msgs.json"
PENDING_TASKS_FILE = "data/pending_tasks.json"

# ---------------------- ВРЕМЯ ЗАПУСКА И АНТИСПАМ ----------------------
BOT_START_TIME = time.time()
COMMAND_COOLDOWN = 5.0
last_command_time = {}

# ---------------------- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ----------------------
download_semaphore = None
per_user_semaphore = {}
download_queue = None
link_accumulators = {}
user_delay_tasks = {}
user_processing = {}
worker_busy = False
active_tasks_count = 0
last_auth_warning = {}
WARNING_COOLDOWN = 60
worker_task = None
token_checker_task = None
memory_cleaner_task = None
last_processed_msg = {}
user_locks = {}
user_tokens = {}
active_status_msgs = {}
pending_tasks = {}
current_task_info = {}
user_link_last_submit = {}
user_queue_count = {}

# ---------------------- СОСТОЯНИЯ ДИАЛОГА ----------------------
WAITING_FOR_TOKEN, WAITING_FOR_LINK = range(2)

# ---------------------- НАЗВАНИЯ КАЧЕСТВА ----------------------
QUALITY_NAMES = {0: "Низкое", 1: "Среднее", 2: "Высокое"}
QUALITY_NAMES_GENITIVE = {0: "низкого", 1: "среднего", 2: "высокого"}
QUALITY_BUTTONS = {"Низкое": 0, "Среднее": 1, "Высокое": 2}

# ---------------------- КЛАВИАТУРЫ ----------------------
quality_keyboard = [[KeyboardButton("Низкое"), KeyboardButton("Среднее"), KeyboardButton("Высокое")]]
quality_markup = ReplyKeyboardMarkup(quality_keyboard, resize_keyboard=True, one_time_keyboard=True)

main_menu_keyboard = [
    ["▶ Начать загрузку", "⏹ Отменить загрузку"],
    ["🔓 Удалить токен", "🔄 Обновить токен"],
    ["🎵 Качество", "📊 Статус"],
    ["🆘 Экстренная остановка"]
]
main_markup = ReplyKeyboardMarkup(main_menu_keyboard, resize_keyboard=True)


# ======================================================================
# ФУНКЦИЯ ДЛЯ ОТПРАВКИ sendMessageDraft (оставлена для анимации)
# ======================================================================
async def _send_message_draft(bot, chat_id, draft_id, text):
    """Отправляет черновик сообщения с эффектом «печати» (streaming)."""
    try:
        await bot._post(
            "sendMessageDraft",
            {
                "chat_id": chat_id,
                "draft_id": draft_id,
                "text": text
            }
        )
    except Exception as e:
        logger.error(f"Ошибка отправки черновика: {e}")


# ======================================================================
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ АВТОУДАЛЕНИЯ СООБЩЕНИЙ
# ======================================================================
async def delete_message_after(bot, chat_id, message_id, delay):
    """Удаляет сообщение через указанное количество секунд."""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение {message_id}: {e}")


# ======================================================================
# ОТПРАВКА СООБЩЕНИЙ С АНИМАЦИЕЙ (ЗАМЕНЁН ЧЕРНОВИК "ОЖИДАЮ НОВОЕ")
# ======================================================================
async def send_animated_message(bot, chat_id, text, delay=0.4, max_retries=3, **kwargs):
    """
    Отправляет сообщение с анимацией (черновик для эффекта печати),
    после чего отправляет обычное сообщение «⏳ Ожидаю новое сообщение» и удаляет его через 5 секунд.
    """
    draft_id = int(time.time() * 1000) + random.randint(1, 10000)
    for attempt in range(max_retries):
        try:
            await _send_message_draft(bot, chat_id, draft_id, text)
            await asyncio.sleep(delay)
            msg = await bot.send_message(chat_id=chat_id, text=text, **kwargs)
            wait_msg = await bot.send_message(chat_id=chat_id, text="⏳ Ожидаю новое сообщение")
            asyncio.create_task(delete_message_after(bot, chat_id, wait_msg.message_id, 5))
            return msg
        except Exception as e:
            logger.warning(f"Анимация {attempt+1}: {e}")
            if attempt == max_retries - 1:
                return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
            await asyncio.sleep(0.5 * (attempt + 1))
    return await bot.send_message(chat_id=chat_id, text=text, **kwargs)


# ======================================================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С ТОКЕНАМИ
# ======================================================================

def save_user_tokens():
    try:
        with open(USER_TOKENS_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_tokens, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения токенов: {e}")

def load_user_tokens():
    global user_tokens
    if not os.path.exists(USER_TOKENS_FILE):
        return
    try:
        with open(USER_TOKENS_FILE, 'r', encoding='utf-8') as f:
            loaded = json.loads(f.read().strip())
        now = time.time()
        user_tokens = {
            uid: data for uid, data in loaded.items()
            if now - data.get('timestamp', 0) <= TOKEN_LIFETIME
        }
        logger.info(f"Загружено {len(user_tokens)} действующих токенов")
    except Exception as e:
        logger.error(f"Ошибка загрузки токенов: {e}")

def is_token_valid_by_id(user_id: int) -> bool:
    data = user_tokens.get(str(user_id))
    return data is not None and (time.time() - data['timestamp']) <= TOKEN_LIFETIME

def get_user_token(user_id: int) -> str | None:
    data = user_tokens.get(str(user_id))
    if data and is_token_valid_by_id(user_id):
        return data['token']
    return None

def set_user_token(user_id: int, token: str):
    user_tokens[str(user_id)] = {"token": token, "timestamp": time.time()}
    save_user_tokens()

def delete_user_token(user_id: int):
    user_tokens.pop(str(user_id), None)
    save_user_tokens()


# ======================================================================
# ФУНКЦИИ ДЛЯ СТАТУСНЫХ СООБЩЕНИЙ
# ======================================================================

def save_active_msgs():
    try:
        with open(ACTIVE_MSGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(active_status_msgs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения активных сообщений: {e}")

def load_active_msgs():
    global active_status_msgs
    if os.path.exists(ACTIVE_MSGS_FILE):
        try:
            with open(ACTIVE_MSGS_FILE, 'r', encoding='utf-8') as f:
                active_status_msgs = json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки активных сообщений: {e}")

async def cleanup_orphan_messages(app):
    for task_id, info in list(active_status_msgs.items()):
        try:
            await app.bot.delete_message(chat_id=info['chat_id'], message_id=info['message_id'])
        except Exception as e:
            logger.debug(f"Не удалось удалить orphan сообщение {task_id}: {e}")
        active_status_msgs.pop(task_id, None)
    save_active_msgs()


# ======================================================================
# ФУНКЦИИ ДЛЯ ОТЛОЖЕННЫХ ЗАДАЧ
# ======================================================================

def save_pending_tasks():
    try:
        with open(PENDING_TASKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(pending_tasks, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения отложенных задач: {e}")

def load_pending_tasks():
    global pending_tasks
    if os.path.exists(PENDING_TASKS_FILE):
        try:
            with open(PENDING_TASKS_FILE, 'r', encoding='utf-8') as f:
                pending_tasks = json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки отложенных задач: {e}")

def add_pending_task(chat_id: int, task: dict):
    pending_tasks.setdefault(str(chat_id), []).append(task)
    save_pending_tasks()

def get_pending_tasks(chat_id: int) -> list:
    return pending_tasks.get(str(chat_id), [])

def clear_pending_tasks(chat_id: int):
    pending_tasks.pop(str(chat_id), None)
    save_pending_tasks()


# ======================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ======================================================================

def is_message_too_old(update: Update) -> bool:
    return update.message and update.message.date.timestamp() < BOT_START_TIME

def is_token_valid(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return is_token_valid_by_id(context._user_id)

def get_plural_tracks(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} трек"
    elif 2 <= n % 10 <= 4 and (n % 100 < 10 or n % 100 >= 20):
        return f"{n} трека"
    return f"{n} треков"

async def fetch_cover_from_yandex(cover_uri: str) -> bytes | None:
    if not cover_uri:
        return None
    try:
        cover_url = f"https://{cover_uri.replace('%%', '1000x1000')}"
        async with aiohttp.ClientSession() as session:
            async with session.get(cover_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception as e:
        logger.debug(f"Не удалось получить обложку: {e}")
    return None

def compress_cover(cover_bytes: bytes, max_size_bytes: int = 200 * 1024) -> bytes | None:
    if not cover_bytes or len(cover_bytes) <= max_size_bytes:
        return cover_bytes
    try:
        img = Image.open(io.BytesIO(cover_bytes)).convert('RGB')
        for quality in [85, 75, 65, 55, 45, 35, 25]:
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=quality, optimize=True)
            if buf.tell() <= max_size_bytes:
                return buf.getvalue()
        for scale in [0.75, 0.5, 0.3, 0.2, 0.15]:
            w, h = int(img.width * scale), int(img.height * scale)
            if w < 10 or h < 10: continue
            resized = img.resize((w, h), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            resized.save(buf, format='JPEG', quality=75, optimize=True)
            if buf.tell() <= max_size_bytes:
                return buf.getvalue()
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
    try:
        audio = File(file_path)
        if audio is None: return None
        if hasattr(audio, 'tags') and audio.tags:
            if 'APIC:' in audio.tags:
                for tag in audio.tags.values():
                    if isinstance(tag, APIC):
                        return tag.data
            if 'covr' in audio.tags and audio.tags['covr']:
                if isinstance(audio.tags['covr'][0], MP4Cover):
                    return bytes(audio.tags['covr'][0])
    except Exception as e:
        logger.debug(f"Не удалось извлечь обложку из аудио: {e}")
    return None

def get_audio_duration(file_path: Path) -> int:
    try:
        if file_path.suffix.lower() == '.m4a':
            return int(MP4(file_path).info.length)
        return int(MP3(file_path).info.length)
    except Exception:
        return 0

def check_disk_space(min_free_mb: int = MIN_FREE_DISK_MB) -> tuple[bool, float]:
    try:
        stat = shutil.disk_usage(Path.cwd())
        free_mb = stat.free / (1024 * 1024)
        return free_mb >= min_free_mb, free_mb
    except Exception:
        return True, 9999.0

def cleanup_old_tmp_dirs():
    cnt = 0
    for tmp_dir in Path('/tmp').glob('bocchi_tmp_*'):
        if tmp_dir.is_dir():
            shutil.rmtree(tmp_dir, ignore_errors=True)
            cnt += 1
    if cnt:
        logger.info(f"Удалено старых временных папок: {cnt}")

def add_stats(bytes_added: int):
    try:
        current = 0.0
        if STATS_FILE_PATH.exists():
            with open(STATS_FILE_PATH, "r") as f:
                current = float(f.read())
        with open(STATS_FILE_PATH, "w") as f:
            f.write(str(current + bytes_added))
    except Exception as e:
        logger.debug(f"Не удалось обновить статистику: {e}")

def get_formatted_stats() -> str:
    try:
        if not STATS_FILE_PATH.exists():
            return "0 Б"
        with open(STATS_FILE_PATH, "r") as f:
            val = float(f.read())
        for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
            if val < 1024.0:
                return f"{val:.2f} {unit}"
            val /= 1024.0
        return f"{val:.2f} ТБ"
    except Exception:
        return "0 Б"

def get_ping() -> float:
    try:
        out = subprocess.check_output(["ping", "-c", "1", "-W", "1", "ya.ru"],
                                      stderr=subprocess.DEVNULL, text=True)
        match = re.search(r'time=([\d\.]+)', out)
        if match:
            return float(match.group(1))
    except Exception as e:
        logger.debug(f"Ошибка при проверке ping: {e}")
    return 0.0

def get_user_quality(context: ContextTypes.DEFAULT_TYPE) -> int:
    return context.user_data.get('quality', DEFAULT_QUALITY)

def set_user_quality(context: ContextTypes.DEFAULT_TYPE, quality: int) -> bool:
    if quality in QUALITY_NAMES:
        context.user_data['quality'] = quality
        return True
    return False


# ======================================================================
# ПАРСИНГ ССЫЛОК ЯНДЕКС.МУЗЫКИ
# ======================================================================

def extract_base_url(url: str) -> str:
    m = re.match(r'(https?://(?:[a-z0-9-]+\.)*yandex\.[a-z]{2,3})(?:/music)?', url, re.IGNORECASE)
    if m:
        base = m.group(1)
        return base if '/music' in url else f"{base}/music"
    return "https://music.yandex.ru"

def parse_yandex_url(url: str):
    parsed = urlparse(url)
    path = parsed.path
    query = parse_qs(parsed.query)

    m = re.search(r'/iframe/playlist/([^/]+)/(\d+)', path)
    if m: return ('iframe_playlist', m.group(2), m.group(1))
    m = re.search(r'/track/(\d+)', path)
    if m: return ('track', m.group(1), None)
    m = re.search(r'/album/(\d+)', path)
    if m: return ('album', m.group(1), None)
    m = re.search(r'/users/([^/]+)/playlists/(\d+)', path)
    if m: return ('playlist', m.group(2), m.group(1))
    m = re.search(r'/playlist/(\d+)', path)
    if m: return ('playlist', m.group(1), None)
    m = re.search(r'/playlists/([a-z0-9\-\.]+)', path)
    if m: return ('uuid_playlist', m.group(1), None)
    if 'handlers/playlist.jsx' in path:
        owner = query.get('owner', [None])[0]
        kinds = query.get('kinds', [None])[0]
        if owner and kinds: return ('playlist', kinds, owner)
    return (None, None, None)


# ======================================================================
# КОМАНДА /quality
# ======================================================================

async def cmd_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update): return
    current = get_user_quality(context)
    await update.message.reply_text(
        f"🎵 Т-текущее качество: *{QUALITY_NAMES[current]}*\n\n"
        "В-выбери новое качество кнопками ниже... п-пожалуйста:",
        parse_mode='Markdown', reply_markup=quality_markup
    )


# ======================================================================
# КОМАНДА /status (пасхалка — дашборд для сисадминов)
# ======================================================================

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update): return
    chat_id = update.effective_chat.id

    text = (
        "🌸 *Секретный блокнот Хитори* 🎸\n\n"
        "Э-эй... т-ты нажал сюда случайно, да?\n"
        "Это... это не для обычных пользователей, п-понимаешь?\n"
        "Здесь только для сисадминов. Т-тех, кто понимает в графиках и...\n"
        "в каких-то страшных циферках, от которых мне становится не по себе...\n\n"
        "Н-но если ты действительно хочешь посмотреть —\n"
        "только никому не говори, ладно?..\n\n"
        f"🌐 [Дашборд для сисадминов]({MONITORING_URL})\n\n"
        "_...я н-не знаю, что там значит 'Load Average',\n"
        "но если цифра большая — мне, наверное, плохо..._"
    )

    await send_animated_message(
        context.bot, chat_id, text,
        parse_mode='Markdown',
        disable_web_page_preview=False,
        reply_markup=main_markup
    )


# ======================================================================
# ХЕНДЛЕРЫ АВТОРИЗАЦИИ
# ======================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update): return WAITING_FOR_LINK
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    lock = user_locks.setdefault(user_id, asyncio.Lock())
    async with lock:
        text = (
            "🌸 П-привет... я Боччи... т-то есть Bocchi Downloader 🎸\n\n"
            "Я ж-живу на этом сервере и... э-э... попробую помочь тебе скачать музыку из Яндекс.Музыки.\n\n"
            "✨ К-как это работает:\n"
            f"• М-можно прислать до {MAX_LINKS} ссылок за раз.\n"
            "• Я б-буду скачивать всё по очереди, аккуратно...\n\n"
            "⚠️ В-высокое качество нагружает сервер. Если я зависну... п-прости, попробуй понизить качество.\n\n"
            "Н-нажми кнопку внизу, чтобы войти в аккаунт и начать!"
        )
        await send_animated_message(
            context.bot, chat_id, text,
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🎵 Начать работу")]], resize_keyboard=True)
        )
        return WAITING_FOR_LINK

async def check_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update): return WAITING_FOR_LINK
    user_id = update.effective_user.id
    lock = user_locks.setdefault(user_id, asyncio.Lock())
    async with lock:
        if is_token_valid(context):
            await send_animated_message(context.bot, update.effective_chat.id,
                                        "✅ Т-токен уже активен! В-возвращаюсь в главное меню.",
                                        reply_markup=main_markup)
            return WAITING_FOR_LINK

        auth_text = (
            "🔑 А-авторизация\n\n"
            "1️⃣ Перейди по [ссылке](https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41195d)\n"
            "2️⃣ Нажми «Войти» или «Разрешить».\n"
            "3️⃣ Страница может стать пустой — э-это нормально!\n"
            "4️⃣ Скопируй весь адрес из строки браузера и отправь мне."
        )
        await send_animated_message(context.bot, update.effective_chat.id, auth_text,
                                    parse_mode="Markdown", disable_web_page_preview=True)
        return WAITING_FOR_TOKEN

async def save_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update): return WAITING_FOR_TOKEN
    user_id = update.effective_user.id
    raw = update.message.text.strip()
    m = re.search(r"(y0_[a-zA-Z0-9_-]+)", raw)
    if m: token = m.group(1)
    else:
        m = re.search(r"access_token=([^&]+)", raw)
        token = m.group(1) if m else None
    if not token:
        await update.message.reply_text("Э-эй... я н-не смогла найти токен. П-попробуй ещё раз?")
        return WAITING_FOR_TOKEN
    try:
        await update.message.delete()
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение при сохранении токена: {e}")
    status_msg = await update.message.reply_text("🔍 П-проверяю токен…")
    try:
        client = ClientAsync(token)
        await client.init()
        acc = await client.account_status()
        if acc and acc.account:
            login = acc.account.login
            set_user_token(user_id, token)
            context.user_data['yandex_token'] = token
            context.user_data['token_time'] = time.time()
            await status_msg.edit_text(f"✅ У-ура! Я узнала тебя, {login}! Я... я н-не ожидала, что получится!")
            await show_main_menu(update, context)
            return WAITING_FOR_LINK
    except Exception as e:
        logger.warning(f"ClientAsync не сработал: {e}")
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
                        await status_msg.edit_text(f"✅ У-ура! Я узнала тебя, {login}!")
                        await show_main_menu(update, context)
                        return WAITING_FOR_LINK
    except Exception as e:
        logger.debug(f"Ошибка при проверке токена через aiohttp: {e}")
    await status_msg.edit_text("❌ Т-токен не подходит... П-попробуй ещё раз?")
    return WAITING_FOR_TOKEN

async def cmd_logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update): return
    user_id = update.effective_user.id
    delete_user_token(user_id)
    context.user_data.pop('yandex_token', None)
    context.user_data.pop('token_time', None)
    await send_animated_message(context.bot, update.effective_chat.id,
                                "🔓 Т-токен удалён. Ты... ты вышел из аккаунта.")
    await send_animated_message(
        context.bot, update.effective_chat.id,
        "Ч-чтобы продолжить, авторизуйся заново.",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🎵 Начать работу")]], resize_keyboard=True)
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_animated_message(
        context.bot, update.effective_chat.id,
        "❌ Д-действие отменено. Напиши /start, если захочешь н-начать заново."
    )
    return ConversationHandler.END

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update): return WAITING_FOR_LINK
    if user_processing.get(update.effective_user.id):
        await update.message.reply_text("⏳ Я п-пока занята загрузкой...")
        return WAITING_FOR_LINK
    await show_main_menu(update, context)
    return WAITING_FOR_LINK


# ======================================================================
# БЕЗОПАСНОЕ РЕДАКТИРОВАНИЕ CALLBACK-СООБЩЕНИЙ
# ======================================================================
async def _safe_edit_callback(update, text):
    try:
        await update.callback_query.edit_message_text(text)
    except Exception as e:
        logger.info(f"Не удалось отредактировать сообщение (вероятно, уже удалено): {e}")


# ======================================================================
# ОБЛАЧНЫЕ ХРАНИЛИЩА С ФОЛБЭКОМ
# ======================================================================

async def _upload_to_0x0(file_path: str, timeout: int = CLOUD_TIMEOUT) -> str | None:
    try:
        with open(file_path, 'rb') as f:
            data = aiohttp.FormData()
            data.add_field('file', f, filename=os.path.basename(file_path))
            async with aiohttp.ClientSession() as session:
                async with session.post("https://0x0.st", data=data,
                                        timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status == 200:
                        url = (await resp.text()).strip()
                        if url.startswith("http"):
                            return url
                    else:
                        logger.warning(f"0x0.st: статус {resp.status}")
    except Exception as e:
        logger.warning(f"0x0.st: {e}")
    return None


async def _upload_to_gofile(file_path: str, timeout: int = CLOUD_TIMEOUT) -> str | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.gofile.io/getServer",
                                   timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json()
                if data.get("status") != "ok":
                    return None
                server = data["data"]["server"]

            with open(file_path, 'rb') as f:
                data = aiohttp.FormData()
                data.add_field('file', f, filename=os.path.basename(file_path))
                async with session.post(f"https://{server}.gofile.io/contents/uploadfile",
                                        data=data,
                                        timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    result = await resp.json()
                    if result.get("status") == "ok":
                        return result["data"].get("downloadPage")
    except Exception as e:
        logger.warning(f"gofile.io: {e}")
    return None


async def _upload_to_tmpfiles(file_path: str, timeout: int = CLOUD_TIMEOUT) -> str | None:
    try:
        with open(file_path, 'rb') as f:
            data = aiohttp.FormData()
            data.add_field('file', f, filename=os.path.basename(file_path))
            async with aiohttp.ClientSession() as session:
                async with session.post("https://tmpfiles.org/api/v1/upload", data=data,
                                        timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        url = result.get("data", {}).get("url")
                        if url:
                            return url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
    except Exception as e:
        logger.warning(f"tmpfiles.org: {e}")
    return None


async def _upload_to_catbox(file_path: str, timeout: int = CLOUD_TIMEOUT) -> str | None:
    try:
        with open(file_path, 'rb') as f:
            data = aiohttp.FormData()
            data.add_field('reqtype', 'fileupload')
            data.add_field('fileToUpload', f, filename=os.path.basename(file_path))
            async with aiohttp.ClientSession() as session:
                async with session.post("https://catbox.moe/user/api.php", data=data,
                                        timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status == 200:
                        url = (await resp.text()).strip()
                        if url.startswith("http"):
                            return url
                    else:
                        logger.warning(f"catbox.moe: статус {resp.status}")
    except Exception as e:
        logger.warning(f"catbox.moe: {e}")
    return None


_CLOUD_CHAIN = [
    ("0x0.st",       _upload_to_0x0),
    ("gofile.io",    _upload_to_gofile),
    ("tmpfiles.org", _upload_to_tmpfiles),
    ("catbox.moe",   _upload_to_catbox),
]


async def upload_to_cloud(file_path: str, timeout: int = CLOUD_TIMEOUT) -> tuple[str | None, str | None]:
    """Пробует облака по цепочке. Возвращает (url, service_name) или (None, None)."""
    file_name = os.path.basename(file_path)
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    logger.info(f"Облачная загрузка {file_name} ({file_size_mb:.1f} МБ)")

    for name, uploader in _CLOUD_CHAIN:
        logger.info(f"Пробую {name}...")
        start = time.time()
        try:
            url = await asyncio.wait_for(uploader(file_path, timeout), timeout=timeout + 10)
        except asyncio.TimeoutError:
            logger.warning(f"{name}: таймаут")
            url = None
        except Exception as e:
            logger.warning(f"{name}: {e}")
            url = None

        elapsed = time.time() - start
        if url:
            logger.info(f"✅ {name}: за {elapsed:.1f}с → {url}")
            return url, name
        logger.warning(f"❌ {name}: провал за {elapsed:.1f}с")

    logger.error(f"Все облака недоступны для {file_name}")
    return None, None


# ======================================================================
# ОТМЕНА ЗАГРУЗКИ (МЯГКАЯ)
# ======================================================================

async def cancel_download(update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback=False):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Ищем активную задачу (которая качается прямо сейчас) для этого чата
    active_task_id = None
    for tid, info in current_task_info.items():
        if info.get('chat_id') == chat_id:
            active_task_id = tid
            break

    # Убираем все задачи этого пользователя из очереди (но не трогаем чужие)
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

    # Уменьшаем счётчик треков пользователя
    user_queue_count[str(user_id)] = max(0, user_queue_count.get(str(user_id), 0) - removed_from_queue)

    global active_tasks_count
    active_tasks_count -= removed_from_queue
    if active_tasks_count < 0:
        active_tasks_count = 0
    save_queue_state()

    if active_task_id:
        # Активная задача — даём ей доделаться, помечаем отмену после
        current_task_info[active_task_id]['cancel_after_current'] = True
        notify = (
            f"🛑 О-ой, останавливаю... Убрано из очереди: {removed_from_queue}.\n"
            f"Т-текущий трек доделаю и отправлю, ладно? Затем з-загрузка прекратится."
        )
    else:
        notify = f"✅ З-загрузка отменена. Убрано из очереди: {removed_from_queue}."

    if is_callback:
        await update.callback_query.answer()
        await context.bot.send_message(chat_id, notify)
    else:
        with contextlib.suppress(Exception):
            await update.message.reply_text(notify)

    logger.info(
        f"Мягкая отмена в чате {chat_id}: убрано из очереди {removed_from_queue}, "
        f"активная задача {'доделается' if active_task_id else 'нет'}"
    )

    if not active_task_id:
        await show_main_menu_from_chat(context.bot, chat_id)


async def cancel_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cancel_download(update, context, is_callback=True)


# ======================================================================
# ЭКСТРЕННАЯ ОСТАНОВКА (ЖЁСТКАЯ)
# ======================================================================

async def emergency_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    await update.message.reply_text("🛑 Э-экстренная остановка! С-сейчас всё выключу... п-прости!")

    # Убиваем только задачи этого чата
    killed = 0
    for task_id, info in list(current_task_info.items()):
        if info.get('chat_id') != chat_id:
            continue
        proc = info.get('process')
        if proc and not proc.returncode:
            try:
                proc.kill()
                await proc.wait()
            except Exception as e:
                logger.debug(f"Ошибка при kill в emergency_stop: {e}")
        killed += 1

        msg_id = active_status_msgs.pop(task_id, {}).get('message_id')
        if msg_id:
            with contextlib.suppress(Exception):
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)

        tmp_dir = info.get('tmp_dir')
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)

        current_task_info.pop(task_id, None)

    # Чистим очередь только для этого пользователя
    removed = 0
    remaining = []
    while not download_queue.empty():
        try:
            t = download_queue.get_nowait()
            if t.get('user_id') != user_id:
                remaining.append(t)
            else:
                removed += 1
        except asyncio.QueueEmpty:
            break
    for t in remaining:
        await download_queue.put(t)

    # Сбрасываем счётчик треков пользователя
    user_queue_count[str(user_id)] = 0

    global active_tasks_count
    active_tasks_count -= (killed + removed)
    if active_tasks_count < 0:
        active_tasks_count = 0

    save_queue_state()
    save_active_msgs()

    await update.message.reply_text(
        f"✅ Э-экстренная остановка выполнена.\n"
        f"Убито активных: {killed}, очищено из очереди: {removed}.\n"
        f"Н-ничего не будет отправлено. Я... я с-старалась не сломать ничего лишнего."
    )
    logger.info(f"Экстренная остановка в чате {chat_id}: убито {killed}, очищено {removed}")
    await show_main_menu_from_chat(context.bot, chat_id)


# ======================================================================
# ПЕРЕЗАПУСК ЗАВИСШЕЙ ЗАДАЧИ
# ======================================================================

async def restart_stuck_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
                except Exception as e:
                    logger.debug(f"Ошибка при kill процесса в restart_stuck_task: {e}")
            msg_id = active_status_msgs.pop(task_id, {}).get('message_id')
            if msg_id:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                except Exception as e:
                    logger.debug(f"Не удалось удалить сообщение при перезапуске задачи: {e}")
            task = info['task']
            current_task_info.pop(task_id)
            await download_queue.put(task)
            global active_tasks_count
            active_tasks_count += 1
            await query.edit_message_text(f"🔄 З-задача «{task['track_name']}» перезапущена. П-продолжаю загрузку...")
            return

    await query.edit_message_text("❌ Н-нет зависших задач для этого чата.")


# ======================================================================
# ГЛАВНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ
# ======================================================================

async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update):
        return WAITING_FOR_LINK

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = update.message.text

    menu_commands = [
        "🎵 Начать работу", "▶ Начать загрузку", "🔓 Удалить токен",
        "🔄 Обновить токен", "🎵 Качество", "📊 Статус",
        "⏹ Отменить загрузку", "🆘 Экстренная остановка"
    ] + list(QUALITY_BUTTONS.keys())

    if text in menu_commands:
        now = time.time()
        last_time = last_command_time.get(user_id, 0)
        if now - last_time < COMMAND_COOLDOWN:
            try:
                await update.message.delete()
            except Exception as e:
                logger.debug(f"Не удалось удалить сообщение при проверке cooldown: {e}")
            return WAITING_FOR_LINK
        last_command_time[user_id] = now

    msg_id = update.message.message_id
    if last_processed_msg.get(user_id) == msg_id:
        return WAITING_FOR_LINK
    last_processed_msg[user_id] = msg_id

    if text == "🎵 Начать работу":
        return await check_session(update, context)
    if text == "▶ Начать загрузку":
        await send_animated_message(context.bot, chat_id,
                                    "🎵 П-присылай ссылки на треки, альбомы или плейлисты...")
        return WAITING_FOR_LINK
    if text == "🔓 Удалить токен":
        await cmd_logout(update, context)
        return WAITING_FOR_LINK
    if text == "🔄 Обновить токен":
        await send_animated_message(context.bot, chat_id, "🔑 П-пожалуйста, отправь новый токен...")
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
                f"✅ К-качество изменено на *{QUALITY_NAMES[new_q]}*.\n\n"
                "⚠️ В-высокое качество нагружает сервер...",
                parse_mode='Markdown', reply_markup=main_markup
            )
        else:
            await update.message.reply_text("❌ Н-не получилось сменить качество...")
        return WAITING_FOR_LINK

    message = update.message

    if 'iframe' in text and 'music.yandex' in text:
        src_match = re.search(r'src="(https?://music\.yandex\.[a-z]{2,3}/[^"]+)"', text, re.IGNORECASE)
        if src_match:
            text = src_match.group(1)
            await context.bot.send_message(chat_id, "🔍 О-ой, нашла в коде ссылку на плейлист. П-продолжаю...",
                                           reply_to_message_id=message.message_id)
        else:
            await context.bot.send_message(chat_id, "❌ Н-не удалось найти ссылку в HTML-коде...")
            return WAITING_FOR_LINK

    if not is_token_valid(context):
        try:
            await message.delete()
        except Exception as e:
            logger.debug(f"Не удалось удалить сообщение при невалидном токене: {e}")
        now = time.time()
        last_warn = last_auth_warning.get(user_id, 0)
        if now - last_warn > WARNING_COOLDOWN:
            last_auth_warning[user_id] = now
            await send_animated_message(
                context.bot, chat_id,
                "🔑 Т-требуется авторизация. Используй /start или кнопку «🎵 Начать работу»."
            )
        return WAITING_FOR_TOKEN

    # Per-user cooldown на отправку ссылок
    now = time.time()
    last_submit = user_link_last_submit.get(user_id, 0)
    if now - last_submit < LINK_SUBMIT_COOLDOWN:
        remaining_sec = int(LINK_SUBMIT_COOLDOWN - (now - last_submit))
        await context.bot.send_message(
            chat_id,
            f"⏳ П-подожди {remaining_sec} сек. перед отправкой новых ссылок... п-пожалуйста."
        )
        try:
            await message.delete()
        except Exception:
            pass
        return WAITING_FOR_LINK
    user_link_last_submit[user_id] = now

    content = text + " " + (update.message.caption or "")
    url_pattern = re.compile(r'https?://(?:[a-z0-9-]+\.)*yandex\.[a-z]{2,3}(?:/music)?(?:/[^\s]+)?', re.IGNORECASE)
    urls = url_pattern.findall(content)
    valid_urls = []
    for u in urls:
        u = u.rstrip('.,!?;:()[]{}"\'')
        if parse_yandex_url(u)[0] is not None:
            valid_urls.append(u)

    if not valid_urls:
        await context.bot.send_message(chat_id, "❌ Я н-не смогла распознать ссылку...")
        return WAITING_FOR_LINK

    # Проверка лимита треков на пользователя
    current_count = user_queue_count.get(str(user_id), 0)
    if current_count >= MAX_TRACKS_PER_USER:
        await context.bot.send_message(
            chat_id,
            f"😱 У т-тебя уже {current_count} треков в очереди! Э-это максимум!\n"
            f"Д-дождись завершения или отмени загрузку."
        )
        try:
            await message.delete()
        except Exception:
            pass
        return WAITING_FOR_LINK

    link_accumulators.setdefault(user_id, []).extend(valid_urls)
    if user_processing.get(user_id):
        await context.bot.send_message(chat_id, "🔄 Я п-пока занята предыдущей загрузкой... П-подожди немножко.")
        try:
            await message.delete()
        except Exception as e:
            logger.debug(f"Не удалось удалить исходное сообщение: {e}")
        return WAITING_FOR_LINK

    async def safe_process():
        await asyncio.sleep(ACCUMULATION_DELAY)
        token = get_user_token(user_id)
        if not token:
            await context.bot.send_message(chat_id, "❌ Т-токен исчез... Авторизуйся заново.")
            return
        try:
            await process_accumulated_links(user_id, chat_id, context, token)
        except Exception as e:
            logger.error(f"Ошибка обработки ссылок: {e}", exc_info=True)
            await context.bot.send_message(chat_id, f"❌ О-ой... Ч-что-то пошло не так: {str(e)[:200]}")
        finally:
            user_processing.pop(user_id, None)
            link_accumulators.pop(user_id, None)

    user_delay_tasks[user_id] = asyncio.create_task(safe_process())

    confirm_msg = await context.bot.send_message(chat_id, "📎 Я п-приняла ссылки... С-сейчас посчитаю и начну готовить.",
                                                 reply_to_message_id=message.message_id)
    try:
        await message.delete()
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение после подтверждения: {e}")

    async def delete_confirm():
        await asyncio.sleep(5)
        try:
            await confirm_msg.delete()
        except Exception as e:
            logger.debug(f"Не удалось удалить подтверждающее сообщение: {e}")
    asyncio.create_task(delete_confirm())

    return WAITING_FOR_LINK


# ======================================================================
# ОБРАБОТКА НАКОПЛЕННЫХ ССЫЛОК (ПАКЕТНАЯ)
# ======================================================================

def make_track_dict(track, base_url: str, original_url: str,
                    batch_type=None, batch_name=None, batch_artist=None, batch_owner=None,
                    total=0, cover_bytes=None, album=None, year=None, genre=None):
    if isinstance(track, dict):
        artist = ', '.join(a.get('name', '') for a in track.get('artists', [])) or "Неизвестен"
        title = track.get('title', 'Неизвестный трек')
        version = track.get('version') or track.get('subtitle')
        if version:
            title += f" ({version})"
        tid = track['id']
        duration = track.get('duration_ms', 0) // 1000
    else:
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
    user_processing[user_id] = True

    raw_links = list(dict.fromkeys(link_accumulators.pop(user_id, [])))[:MAX_LINKS]
    if not raw_links:
        user_processing.pop(user_id, None)
        return

    logger.info(f"Обработка ссылок от {user_id}: {raw_links}")

    try:
        client = ClientAsync(token)
        await client.init()
    except Exception as e:
        logger.error(f"Ошибка создания клиента: {e}")
        await context.bot.send_message(chat_id, "❌ О-ошибка авторизации. П-попробуй снова.")
        user_processing.pop(user_id, None)
        return

    all_tracks = []
    for url in raw_links:
        base_url = extract_base_url(url)
        type_, id_, username = parse_yandex_url(url)
        if not type_:
            await context.bot.send_message(chat_id, f"❌ Н-не удалось распознать ссылку: {url}")
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
                            await context.bot.send_message(chat_id, "❌ Плейлист недоступен (возможно, приватный).")
        except Exception as e:
            logger.error(f"Ошибка парсинга {url}: {e}")
            await context.bot.send_message(chat_id, f"❌ О-ошибка при обработке {url}")

    if not all_tracks:
        await context.bot.send_message(chat_id, "❌ Н-не удалось найти треки по ссылкам.")
        user_processing.pop(user_id, None)
        return

    # Проверяем лимит треков на пользователя
    current_count = user_queue_count.get(str(user_id), 0)
    available = MAX_TRACKS_PER_USER - current_count
    if available <= 0:
        await context.bot.send_message(
            chat_id,
            f"😱 У т-тебя уже {current_count} треков в очереди! Э-это максимум!"
        )
        user_processing.pop(user_id, None)
        return

    if len(all_tracks) > available:
        all_tracks = all_tracks[:available]
        await context.bot.send_message(
            chat_id,
            f"⚠️ Я м-могу добавить только {available} треков — у тебя уже {current_count} в очереди.\n"
            f"Остальные придётся пропустить..."
        )

    total = len(all_tracks)
    batch_id = f"{user_id}_{int(time.time())}_{uuid.uuid4().hex[:8]}"

    queue_pos = download_queue.qsize() + 1
    await context.bot.send_message(
        chat_id,
        f"📥 Я п-получила {get_plural_tracks(total)}. Т-твоя очередь — номер {queue_pos}..."
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

    user_queue_count[str(user_id)] = current_count + total

    global active_tasks_count
    active_tasks_count += total
    save_queue_state()
    user_processing.pop(user_id, None)


# ======================================================================
# СОХРАНЕНИЕ И ВОССТАНОВЛЕНИЕ ОЧЕРЕДИ ЗАГРУЗОК
# ======================================================================

def save_queue_state():
    tasks = []
    while not download_queue.empty():
        try:
            tasks.append(download_queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    for t in tasks:
        download_queue.put_nowait(t)
    serial = [{k: v for k, v in t.items() if k != 'cover_bytes'} for t in tasks]
    try:
        with open(QUEUE_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(serial, f, ensure_ascii=False, indent=2)
        logger.info(f"Сохранено задач в очереди: {len(tasks)}")
    except Exception as e:
        logger.error(f"Ошибка сохранения очереди: {e}")

def load_queue_state():
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
                    user_queue_count[str(uid)] = user_queue_count.get(str(uid), 0) + 1
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

async def worker_loop(app, worker_id):
    global worker_busy, active_tasks_count
    chat_temp_msg = {}

    while True:
        if not shutil.which(DOWNLOADER_PATH):
            safe_downloader_path = str(DOWNLOADER_PATH).replace("\r", "").replace("\n", "")
            logger.error(f"[Worker {worker_id}] Загрузчик {safe_downloader_path} не найден!")
            await asyncio.sleep(60)
            continue

        try:
            task = await download_queue.get()
            worker_busy = True
            tmp_dir = Path(f"/tmp/bocchi_tmp_{uuid.uuid4().hex}")
            current_quality = task.get('quality', DEFAULT_QUALITY)
            task_id = f"{task['batch_id']}_{task['batch_index']}"
            chat_id = task['chat_id']
            user_id = task.get('user_id')

            # Per-user semaphore — один пользователь не занимает два слота
            if user_id is not None:
                sem = per_user_semaphore.setdefault(str(user_id), asyncio.Semaphore(1))
            else:
                sem = asyncio.Semaphore(1)

            async with download_semaphore:
                async with sem:
                    status_msg = None
                    downloader_process = None
                    stuck_notified = False
                    success = False
                    actual_quality_used = current_quality
                    try:
                        old = active_status_msgs.pop(task_id, None)
                        if old:
                            try:
                                await app.bot.delete_message(chat_id=old['chat_id'], message_id=old['message_id'])
                            except Exception as e:
                                logger.debug(f"Не удалось удалить старое статусное сообщение {old.get('message_id')}: {e}")
                        prev = chat_temp_msg.pop(chat_id, None)
                        if prev:
                            try:
                                await app.bot.delete_message(chat_id=chat_id, message_id=prev)
                            except Exception as e:
                                logger.debug(f"Не удалось удалить предыдущее сообщение чата {chat_id}: {e}")

                        tmp_dir.mkdir(exist_ok=True)

                        keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton("⏹ Отменить загрузку", callback_data="cancel_download")]
                        ])

                        batch_type = task.get('batch_type')
                        batch_name = task.get('batch_name')
                        batch_artist = task.get('batch_artist')
                        batch_owner = task.get('batch_owner')
                        batch_index = task.get('batch_index', 1)
                        batch_total = task.get('batch_total', 1)

                        header = ""
                        if batch_type == 'album':
                            header = f"📀 Альбом: {batch_name}\n🎤 {batch_artist}\n"
                        elif batch_type == 'playlist':
                            header = f"📋 Плейлист: {batch_name}\n👤 {batch_owner}\n"
                        elif batch_total > 1:
                            header = f"📦 Пакет треков ({batch_total} шт.)\n"

                        progress = f"({batch_index} из {batch_total})" if batch_total > 1 else ""
                        status_text = (
                            f"🌀 О-обрабатываю… {progress}\n"
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
                            "status_msg_id": status_msg.message_id,
                            "tmp_dir": tmp_dir
                        }

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
                            if task_id in current_task_info:
                                current_task_info[task_id]['process'] = proc
                            else:
                                proc.kill()
                                await proc.wait()
                                return -1, b'', b'Cancelled'
                            try:
                                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=DOWNLOAD_TIMEOUT)
                                return proc.returncode, stdout, stderr
                            except asyncio.TimeoutError:
                                proc.kill()
                                return -1, b'', b'Timeout'

                        for attempt in range(3):
                            if time.time() - start_time > STUCK_TIMEOUT and not stuck_notified:
                                stuck_notified = True
                                new_keyboard = InlineKeyboardMarkup([
                                    [InlineKeyboardButton("⏹ Отменить загрузку", callback_data="cancel_download")],
                                    [InlineKeyboardButton("🔄 Перезапустить загрузчик", callback_data="restart_stuck_task")]
                                ])
                                try:
                                    await app.bot.edit_message_reply_markup(chat_id, status_msg.message_id, reply_markup=new_keyboard)
                                except Exception as e:
                                    logger.debug(f"Не удалось обновить клавиатуру статусного сообщения: {e}")

                            enough, free_mb = check_disk_space()
                            if not enough:
                                if current_quality > 0:
                                    new_q = current_quality - 1
                                    if task_id in current_task_info:
                                        await app.bot.send_message(chat_id, f"⚠️ М-мало места! Понижаю качество до {QUALITY_NAMES[new_q]}.")
                                    current_quality = new_q
                                    continue
                                else:
                                    if task_id in current_task_info:
                                        await app.bot.send_message(chat_id, "❌ Н-недостаточно места даже для низкого качества...")
                                    break

                            returncode, stdout, stderr = await run_downloader(current_quality, tmp_dir)
                            if returncode == 0:
                                success = True
                                actual_quality_used = current_quality
                                break

                            stderr_text = stderr.decode('utf-8', errors='replace')
                            logger.warning(f"[Worker {worker_id}] Попытка {attempt+1}: код {returncode}, stderr: {stderr_text[:200]}")

                            shutil.rmtree(tmp_dir, ignore_errors=True)
                            tmp_dir.mkdir(exist_ok=True)

                            if returncode == -9:
                                if current_quality > 0:
                                    current_quality -= 1
                                    if task_id in current_task_info:
                                        await app.bot.send_message(chat_id, "⚠️ Н-нехватка памяти. Понижаю качество...")
                                    continue
                                else:
                                    if task_id in current_task_info:
                                        await app.bot.send_message(chat_id, "❌ Н-недостаточно памяти даже для низкого качества...")
                                    break

                            if any(k in stderr_text.lower() for k in ['forbidden', 'blocked', 'denied', 'регион', 'недоступен', '403']):
                                if task_id in current_task_info:
                                    await app.bot.send_message(chat_id, f"❌ Трек заблокирован Яндексом: {task['track_name']}")
                                break

                            if attempt == 2:
                                if task_id in current_task_info:
                                    await app.bot.send_message(chat_id, f"❌ Н-не удалось скачать {task['track_name']}... Я п-пробовала три раза, честно!")
                            else:
                                await asyncio.sleep(5)

                        if not success:
                            current_task_info.pop(task_id, None)
                            continue

                        if actual_quality_used != task.get('quality', DEFAULT_QUALITY):
                            if task_id in current_task_info:
                                await app.bot.send_message(chat_id, f"🎵 Трек скачан в качестве: {QUALITY_NAMES[actual_quality_used]}.")

                        files = list(tmp_dir.rglob('*.mp3')) + list(tmp_dir.rglob('*.m4a'))
                        for f_path in files:
                            file_size_mb = f_path.stat().st_size / (1024 * 1024)
                            artist = task.get('artist', 'Неизвестен')
                            title = task.get('title', f_path.stem)
                            album = task.get('album')
                            year = task.get('year')
                            genre = task.get('genre')
                            cover_bytes = task.get('cover_bytes')

                            lyrics = None
                            lrc_file = f_path.with_suffix('.lrc')
                            if lrc_file.exists():
                                try:
                                    lyrics = lrc_file.read_text(encoding='utf-8').strip()
                                except (OSError, UnicodeDecodeError) as lrc_err:
                                    logging.warning("Не удалось прочитать LRC файл %s: %s", lrc_file, lrc_err)

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

                            safe_name = re.sub(r'[\\/*?:"<>|]', "", f"{artist} - {title}{f_path.suffix}")
                            final_path = f_path.with_name(safe_name)
                            f_path.rename(final_path)

                            thumb = None
                            embedded_cover = extract_cover_from_audio(final_path) or cover_bytes
                            if embedded_cover:
                                thumb = compress_cover(embedded_cover, 200*1024) if len(embedded_cover) > 200*1024 else embedded_cover

                            if file_size_mb > 49.0:
                                url, cloud_name = await upload_to_cloud(str(final_path), CLOUD_TIMEOUT)
                                if url:
                                    await app.bot.send_message(
                                        chat_id,
                                        f"🔗 Трек превышает 50 МБ, загружен в облако ({cloud_name}).\n{url}",
                                        disable_web_page_preview=True
                                    )
                                else:
                                    await app.bot.send_message(
                                        chat_id, "❌ Н-не удалось загрузить файл ни в одно облако. П-попробуй позже."
                                    )
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
                                    await app.bot.send_message(chat_id, f"❌ Н-не удалось отправить {safe_name}...")

                            add_stats(final_path.stat().st_size)

                            # Уменьшаем счётчик треков пользователя
                            if user_id is not None:
                                user_queue_count[str(user_id)] = max(0, user_queue_count.get(str(user_id), 0) - 1)

                            await asyncio.sleep(TRACK_DELAY_SECONDS)
                            gc.collect()

                            # Проверка мягкой отмены — после отправки текущего трека
                            if current_task_info.get(task_id, {}).get('cancel_after_current'):
                                await app.bot.send_message(
                                    chat_id,
                                    "✅ Т-текущий трек отправлен. Дальше я н-не буду качать, как ты и просил.",
                                    reply_markup=main_markup
                                )
                                break  # выходим из цикла for f_path

                        if batch_total and batch_index == batch_total:
                            # Не показываем финал, если была отмена
                            if not current_task_info.get(task_id, {}).get('cancel_after_current'):
                                if batch_type == 'album':
                                    finish = f"🎸 Альбом «{batch_name}» полностью загружен! Я... я с-справилась!"
                                elif batch_type == 'playlist':
                                    finish = "🎸 Плейлист полностью загружен! У-ура!"
                                else:
                                    finish = "🎸 Все треки обработаны! К-кажется, я молодец..."
                                await app.bot.send_message(
                                    chat_id,
                                    'Загружено при поддержке #BocchiIsAlive <tg-emoji emoji-id="6041593232423391328">💠</tg-emoji>',
                                    parse_mode='HTML'
                                )
                                await app.bot.send_message(chat_id, finish, reply_markup=main_markup)

                    except Exception as e:
                        logger.info(f"[Worker {worker_id}] Задача прервана (отмена или ошибка): {task.get('track_name', '')} | {e}")
                    finally:
                        shutil.rmtree(tmp_dir, ignore_errors=True)
                        worker_busy = False
                        current_task_info.pop(task_id, None)
                        active_status_msgs.pop(task_id, None)
                        if status_msg:
                            try:
                                await status_msg.delete()
                            except Exception as e:
                                logger.debug(f"Не удалось удалить статусное сообщение {status_msg.message_id}: {e}")
                        save_active_msgs()
                        save_queue_state()
                        active_tasks_count -= 1
        except Exception as e:
            logger.critical(f"[Worker {worker_id}] Крах воркера: {e}")
            await asyncio.sleep(10)


# ======================================================================
# ФОНОВЫЕ ЗАДАЧИ
# ======================================================================

async def memory_cleaner():
    while True:
        await asyncio.sleep(300)
        if psutil.virtual_memory().percent > 50:
            gc.collect()
            logger.info("Принудительная очистка памяти")

async def check_all_tokens(app):
    now = time.time()
    changed = False
    for uid, data in list(user_tokens.items()):
        if now - data['timestamp'] > TOKEN_LIFETIME:
            del user_tokens[uid]
            changed = True
    if changed:
        save_user_tokens()

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_animated_message(context.bot, update.effective_chat.id,
                                "🎸 Г-главное меню:", reply_markup=main_markup)

async def show_main_menu_from_chat(bot, chat_id):
    await send_animated_message(bot, chat_id, "🎸 Г-главное меню:", reply_markup=main_markup)


# ======================================================================
# ИНИЦИАЛИЗАЦИЯ И ЗАПУСК БОТА
# ======================================================================

async def post_init(app):
    global download_semaphore, download_queue, worker_task, token_checker_task, memory_cleaner_task
    download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
    download_queue = asyncio.Queue()
    load_user_tokens()
    load_active_msgs()
    load_pending_tasks()
    load_queue_state()
    await cleanup_orphan_messages(app)

    # Запускаем несколько воркеров
    worker_tasks = []
    for i in range(MAX_CONCURRENT_DOWNLOADS):
        wt = asyncio.create_task(worker_loop(app, i))
        worker_tasks.append(wt)

    memory_cleaner_task = asyncio.create_task(memory_cleaner())

    async def periodic_token_check():
        while True:
            await asyncio.sleep(900)
            await check_all_tokens(app)
    token_checker_task = asyncio.create_task(periodic_token_check())

    # Сохраняем воркеры для корректной остановки
    app.bot_data['worker_tasks'] = worker_tasks


def main():
    cleanup_old_tmp_dirs()
    if not STATS_FILE_PATH.exists():
        STATS_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(STATS_FILE_PATH, "w") as f:
            f.write("0")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    app.add_handler(CallbackQueryHandler(restart_stuck_task_callback, pattern="restart_stuck_task"))
    app.add_handler(CallbackQueryHandler(cancel_download_callback, pattern="cancel_download"))

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
        for t in [token_checker_task, memory_cleaner_task]:
            if t:
                t.cancel()
        for wt in app.bot_data.get('worker_tasks', []):
            if wt:
                wt.cancel()

if __name__ == "__main__":
    main()
