# (c) 2026 Hanako
# Bocchi Downloader (Server Edition)
# Полная версия со всеми исправлениями (NameError, sendMessageDraft и др.)
# Работает с python-telegram-bot 21.6 и выше.

import asyncio
import aiohttp
import logging
import os
import json
import random
import re
import shutil
import subprocess
import time
import urllib.parse
import uuid
from pathlib import Path
import io
import gc

import psutil
from catboxpy import AsyncCatboxClient, LitterboxClient
from dotenv import load_dotenv
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, USLT, TDRC, TCON, TALB, APIC, TPE2
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from mutagen import File
from PIL import Image
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, ConversationHandler, filters
)
from yandex_music import ClientAsync

# ---------- ИСПРАВЛЕНИЕ NameError: urlparse и parse_qs теперь импортированы ----------
from urllib.parse import urlparse, parse_qs

# ---------------------- НАСТРОЙКА ЛОГИРОВАНИЯ ----------------------
logging.getLogger("httpx").setLevel(logging.WARNING)
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(message)s')
logger = logging.getLogger("BocchiStation")

# ---------------------- ПАПКА ДЛЯ ДАННЫХ ----------------------
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# ---------------------- КОНФИГУРАЦИЯ ----------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТОКЕН_ЗДЕСЬ")
DOWNLOADER_PATH = os.getenv("DOWNLOADER_PATH", "yandex-music-downloader")
STATS_FILE = os.getenv("STATS_FILE", "data/stats.txt")
MAX_LINKS = int(os.getenv("MAX_LINKS", "10"))
DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", "600"))
TOKEN_LIFETIME = int(os.getenv("TOKEN_LIFETIME", "86400"))
CLOUD_TIMEOUT = int(os.getenv("CLOUD_TIMEOUT", "120"))
DEFAULT_QUALITY = int(os.getenv("DEFAULT_QUALITY", "2"))
MIN_FREE_DISK_MB = int(os.getenv("MIN_FREE_DISK_MB", "20"))
TRACK_DELAY_SECONDS = float(os.getenv("TRACK_DELAY_SECONDS", "5.0"))
STUCK_TIMEOUT = int(os.getenv("STUCK_TIMEOUT", "120"))
ACCUMULATION_DELAY = float(os.getenv("ACCUMULATION_DELAY", "5.0"))

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
# ФУНКЦИЯ ДЛЯ ОТПРАВКИ sendMessageDraft (реализована через bot._post)
# ======================================================================
async def _send_message_draft(bot, chat_id, draft_id, text):
    """Отправляет черновик с эффектом «печати» (streaming), используя метод sendMessageDraft."""
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
        except:
            pass
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
    # В версии 21.6 _user_id всё ещё доступен (приватный атрибут, но рабочий)
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
    except:
        pass
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
    except:
        pass
    return None

def get_audio_duration(file_path: Path) -> int:
    try:
        if file_path.suffix.lower() == '.m4a':
            return int(MP4(file_path).info.length)
        return int(MP3(file_path).info.length)
    except:
        return 0

def check_disk_space(min_free_mb: int = MIN_FREE_DISK_MB) -> tuple[bool, float]:
    try:
        stat = shutil.disk_usage(Path.cwd())
        free_mb = stat.free / (1024 * 1024)
        return free_mb >= min_free_mb, free_mb
    except:
        return True, 9999.0

def cleanup_old_tmp_dirs():
    cnt = 0
    for tmp_dir in Path('.').glob('bocchi_tmp_*'):
        if tmp_dir.is_dir():
            shutil.rmtree(tmp_dir, ignore_errors=True)
            cnt += 1
    if cnt:
        logger.info(f"Удалено старых временных папок: {cnt}")

def add_stats(bytes_added: int):
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
    return context.user_data.get('quality', DEFAULT_QUALITY)

def set_user_quality(context: ContextTypes.DEFAULT_TYPE, quality: int) -> bool:
    if quality in QUALITY_NAMES:
        context.user_data['quality'] = quality
        return True
    return False


# ======================================================================
# ПАРСИНГ ССЫЛОК ЯНДЕКС.МУЗЫКИ (urlparse и parse_qs используются смело!)
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
# АНИМИРОВАННАЯ ОТПРАВКА СООБЩЕНИЙ (ВКЛЮЧАЯ send_animated_message)
# ======================================================================

async def send_animated_message(bot, chat_id, text, delay=0.4, max_retries=3, **kwargs):
    draft_id = int(time.time() * 1000) + random.randint(1, 10000)
    for attempt in range(max_retries):
        try:
            await _send_message_draft(bot, chat_id, draft_id, text)
            await asyncio.sleep(delay)
            msg = await bot.send_message(chat_id=chat_id, text=text, **kwargs)
            await _send_message_draft(bot, chat_id, draft_id, "⏳ Ожидаю новое сообщение")
            return msg
        except Exception as e:
            logger.warning(f"Анимация {attempt+1}: {e}")
            if attempt == max_retries - 1:
                return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
            await asyncio.sleep(0.5 * (attempt + 1))
    return await bot.send_message(chat_id=chat_id, text=text, **kwargs)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_animated_message(context.bot, update.effective_chat.id,
                                "🎸 Главное меню:", reply_markup=main_markup)

async def show_main_menu_from_chat(bot, chat_id):
    await send_animated_message(bot, chat_id, "🎸 Главное меню:", reply_markup=main_markup)


# ======================================================================
# КОМАНДА /quality
# ======================================================================

async def cmd_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update): return
    current = get_user_quality(context)
    await update.message.reply_text(
        f"🎵 Текущее качество: *{QUALITY_NAMES[current]}*\n\n"
        "Выберите новое качество кнопками ниже:",
        parse_mode='Markdown', reply_markup=quality_markup
    )


# ======================================================================
# КОМАНДА /status
# ======================================================================

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update): return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    old = context.user_data.get('status_draft')
    if old:
        try:
            await _send_message_draft(context.bot, old['chat_id'], old['draft_id'], "⏹️ Статус прерван")
        except: pass
        context.user_data.pop('status_draft', None)

    draft_id = int(time.time() * 1000) + user_id
    try:
        await _send_message_draft(context.bot, chat_id, draft_id,
                                             "🌸 Секретный блокнот Хитори 🎸\n\nПодожди, собираю данные...")
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

            if cpu < 15: c_status = "тихим ожиданием новых задач"
            elif cpu < 45: c_status = "активной проверкой твоих ссылок"
            elif cpu < 80: c_status = "сложными расчетами и очередью"
            else: c_status = "попытками не сломаться от нагрузки"

            if mem.percent < 30: m_status = "приятной пустотой, мне дышится легко"
            elif mem.percent < 70: m_status = "самыми важными вещами, всё под рукой"
            else: m_status = "почти целиком, мне становится тесно"

            res_block = (f"Моё самочувствие 🌸\n"
                         f"• Мысли заняты {c_status} ({cpu}%)\n"
                         f"• Память заполнена {m_status} ({mem.percent}%)\n\n")

            ping_val = get_ping()
            if ping_val > 0:
                if ping_val < 20: n_lvl = "сейчас просто идеальная"
                elif ping_val < 60: n_lvl = "вполне стабильная"
                elif ping_val < 100: n_lvl = "стала какой-то слабой"
                else: n_lvl = "почти совсем пропала..."
                net_text = f"• Сеть: {n_lvl} ({ping_val} мс до Яндекса)\n\n"
            else:
                net_text = "• Сеть: не могу достучаться до Яндекса...\n\n"

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
                    await _send_message_draft(context.bot, chat_id, draft_id, status_text)
                    break
                except Exception as e:
                    logger.warning(f"Ошибка обновления черновика (шаг {step}, попытка {retry+1}): {e}")
                    if retry == 1:
                        await context.bot.send_message(chat_id, "❌ Ошибка при обновлении статуса.")
                        await _send_message_draft(context.bot, chat_id, draft_id, "📊 Статус завершён")
                        context.user_data.pop('status_draft', None)
                        await show_main_menu(update, context)
                        return
                    await asyncio.sleep(0.5)
            await asyncio.sleep(2)
    finally:
        try:
            await _send_message_draft(context.bot, chat_id, draft_id, "📊 Статус завершён")
        except: pass
        context.user_data.pop('status_draft', None)

    await show_main_menu(update, context)


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
    if is_message_too_old(update): return WAITING_FOR_TOKEN
    user_id = update.effective_user.id
    raw = update.message.text.strip()
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

async def cmd_logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await send_animated_message(
        context.bot, update.effective_chat.id,
        "❌ Действие отменено. Напиши /start, если захочешь начать заново."
    )
    return ConversationHandler.END

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

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

        if proc and not proc.returncode:
            try:
                proc.kill()
                await proc.wait()
            except:
                pass

        msg_id = active_status_msgs.pop(task_id, {}).get('message_id')
        if msg_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except:
                pass

        current_task_info.pop(task_id, None)
        cancelled_count += 1

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
    await cancel_download(update, context, is_callback=True)


# ======================================================================
# ЭКСТРЕННАЯ ОСТАНОВКА И ПЕРЕЗАПУСК ЗАВИСШЕЙ ЗАДАЧИ
# ======================================================================

async def emergency_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            except:
                pass
            return WAITING_FOR_LINK
        last_command_time[user_id] = now

    msg_id = update.message.message_id
    if last_processed_msg.get(user_id) == msg_id:
        return WAITING_FOR_LINK
    last_processed_msg[user_id] = msg_id

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

    message = update.message

    if 'iframe' in text and 'music.yandex' in text:
        src_match = re.search(r'src="(https?://music\.yandex\.[a-z]{2,3}/[^"]+)"', text, re.IGNORECASE)
        if src_match:
            text = src_match.group(1)
            await context.bot.send_message(chat_id, "🔍 Нашла в коде ссылку на плейлист. Продолжаю…",
                                           reply_to_message_id=message.message_id)
        else:
            await context.bot.send_message(chat_id, "❌ Не удалось найти ссылку в HTML-коде.")
            return WAITING_FOR_LINK

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
    global worker_busy, active_tasks_count
    chat_temp_msg = {}

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

                        if returncode == -9:
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

                    if actual_quality_used != task.get('quality', DEFAULT_QUALITY):
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
                            except:
                                pass

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


# ======================================================================
# ИНИЦИАЛИЗАЦИЯ И ЗАПУСК БОТА
# ======================================================================

async def post_init(app):
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
    global worker_task, token_checker_task, memory_cleaner_task
    cleanup_old_tmp_dirs()
    if not os.path.exists(STATS_FILE):
        with open(STATS_FILE, "w") as f:
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
        for t in [token_checker_task, worker_task, memory_cleaner_task]:
            if t:
                t.cancel()

if __name__ == "__main__":
    main()
