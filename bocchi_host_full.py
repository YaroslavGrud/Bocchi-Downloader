# (c) 2026 Hanako
# Bocchi Downloader (Server Edition)
# Релиз‑кандидат (исправления: отмена, статус, память, пинг)

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
from urllib.parse import urlparse, parse_qs
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
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, filters
)
from yandex_music import ClientAsync

logging.getLogger("httpx").setLevel(logging.WARNING)
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(message)s')
logger = logging.getLogger("BocchiStation")

# Создаём папку data при импорте
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# --- КОНФИГУРАЦИЯ ---
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
QUEUE_STATE_FILE = "data/download_queue_state.json"
USER_TOKENS_FILE = "data/user_tokens.json"
ACTIVE_MSGS_FILE = "data/active_status_msgs.json"
PENDING_TASKS_FILE = "data/pending_tasks.json"

BOT_START_TIME = time.time()

# --- ГЛОБАЛЬНЫЕ ОБЪЕКТЫ ---
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

WAITING_FOR_TOKEN, WAITING_FOR_LINK = range(2)

QUALITY_NAMES = {0: "Низкое", 1: "Среднее", 2: "Высокое"}
QUALITY_NAMES_GENITIVE = {0: "низкого", 1: "среднего", 2: "высокого"}
QUALITY_BUTTONS = {"Низкое": 0, "Среднее": 1, "Высокое": 2}

quality_keyboard = [[KeyboardButton("Низкое"), KeyboardButton("Среднее"), KeyboardButton("Высокое")]]
quality_markup = ReplyKeyboardMarkup(quality_keyboard, resize_keyboard=True, one_time_keyboard=True)

main_menu_keyboard = [
    ["▶ Начать загрузку", "⏹ Отменить загрузку"],
    ["🔓 Удалить токен", "🔄 Обновить токен"],
    ["🎵 Качество", "📊 Статус"],
    ["🆘 Экстренная остановка"]
]
main_markup = ReplyKeyboardMarkup(main_menu_keyboard, resize_keyboard=True)

# ===================== РАБОТА С ТОКЕНАМИ =====================
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
            content = f.read().strip()
            if not content:
                logger.warning("Файл токенов пуст, создаю новый")
                return
            loaded = json.loads(content)
        now = time.time()
        for uid, data in loaded.items():
            if now - data.get('timestamp', 0) <= TOKEN_LIFETIME:
                user_tokens[uid] = data
        logger.info(f"Загружено {len(user_tokens)} действующих токенов")
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка загрузки токенов (некорректный JSON): {e}")
        corrupted = f"{USER_TOKENS_FILE}.corrupted_{int(time.time())}"
        os.rename(USER_TOKENS_FILE, corrupted)
        logger.warning(f"Повреждённый файл переименован в {corrupted}")
    except Exception as e:
        logger.error(f"Ошибка загрузки токенов: {e}")

def is_token_valid_by_id(user_id: int) -> bool:
    data = user_tokens.get(str(user_id))
    if not data:
        return False
    return (time.time() - data['timestamp']) <= TOKEN_LIFETIME

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

# ===================== АКТИВНЫЕ СООБЩЕНИЯ =====================
def save_active_msgs():
    try:
        with open(ACTIVE_MSGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(active_status_msgs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения активных сообщений: {e}")

def load_active_msgs():
    global active_status_msgs
    if not os.path.exists(ACTIVE_MSGS_FILE):
        return
    try:
        with open(ACTIVE_MSGS_FILE, 'r', encoding='utf-8') as f:
            active_status_msgs = json.load(f)
        logger.info(f"Загружено {len(active_status_msgs)} активных сообщений")
    except Exception as e:
        logger.error(f"Ошибка загрузки активных сообщений: {e}")

async def cleanup_orphan_messages(app):
    for task_id, info in list(active_status_msgs.items()):
        try:
            await app.bot.delete_message(chat_id=info['chat_id'], message_id=info['message_id'])
            logger.info(f"Удалено висящее сообщение {info['message_id']} для задачи {task_id}")
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение {info['message_id']}: {e}")
        active_status_msgs.pop(task_id, None)
    save_active_msgs()

# ===================== ОТЛОЖЕННЫЕ ЗАДАЧИ =====================
def save_pending_tasks():
    try:
        with open(PENDING_TASKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(pending_tasks, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения отложенных задач: {e}")

def load_pending_tasks():
    global pending_tasks
    if not os.path.exists(PENDING_TASKS_FILE):
        return
    try:
        with open(PENDING_TASKS_FILE, 'r', encoding='utf-8') as f:
            pending_tasks = json.load(f)
        logger.info(f"Загружено {len(pending_tasks)} чатов с отложенными задачами")
    except Exception as e:
        logger.error(f"Ошибка загрузки отложенных задач: {e}")

def add_pending_task(chat_id: int, task):
    chat_id_str = str(chat_id)
    if chat_id_str not in pending_tasks:
        pending_tasks[chat_id_str] = []
    pending_tasks[chat_id_str].append(task)
    save_pending_tasks()

def get_pending_tasks(chat_id: int) -> list:
    return pending_tasks.get(str(chat_id), [])

def clear_pending_tasks(chat_id: int):
    pending_tasks.pop(str(chat_id), None)
    save_pending_tasks()

# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================
def is_message_too_old(update: Update) -> bool:
    return update.message.date.timestamp() < BOT_START_TIME if update.message else False

def is_token_valid(context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = context._user_id
    return is_token_valid_by_id(user_id)

def get_plural_tracks(n):
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} трек"
    elif 2 <= n % 10 <= 4 and (n % 100 < 10 or n % 100 >= 20):
        return f"{n} трека"
    else:
        return f"{n} треков"

# ===================== РАБОТА С ОБЛОЖКАМИ =====================
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
        logger.warning(f"Не удалось загрузить обложку из Яндекса: {e}")
    return None

def compress_cover(cover_bytes: bytes, max_size_bytes: int = 200 * 1024) -> bytes | None:
    if not cover_bytes or len(cover_bytes) <= max_size_bytes:
        return cover_bytes
    try:
        img = Image.open(io.BytesIO(cover_bytes))
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        for quality in [85, 75, 65, 55, 45, 35, 25]:
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=quality, optimize=True)
            if output.tell() <= max_size_bytes:
                return output.getvalue()
        for scale in [0.75, 0.5, 0.3, 0.2, 0.15]:
            new_size = (int(img.width * scale), int(img.height * scale))
            if new_size[0] < 10 or new_size[1] < 10:
                continue
            resized = img.resize(new_size, Image.Resampling.LANCZOS)
            output = io.BytesIO()
            resized.save(output, format='JPEG', quality=75, optimize=True)
            if output.tell() <= max_size_bytes:
                return output.getvalue()
        for scale in [0.1, 0.08]:
            new_size = (int(img.width * scale), int(img.height * scale))
            if new_size[0] < 8 or new_size[1] < 8:
                continue
            resized = img.resize(new_size, Image.Resampling.LANCZOS)
            output = io.BytesIO()
            resized.save(output, format='JPEG', quality=30, optimize=True)
            if output.tell() <= max_size_bytes:
                return output.getvalue()
        logger.error(f"Не удалось сжать обложку: исходный размер {len(cover_bytes)} байт")
        return None
    except Exception as e:
        logger.error(f"Ошибка сжатия обложки: {e}")
        return None

def extract_cover_from_audio(file_path: Path) -> bytes | None:
    try:
        audio = File(file_path)
        if audio is None:
            return None
        cover_data = None
        if hasattr(audio, 'tags') and 'APIC:' in audio.tags:
            for tag in audio.tags.values():
                if isinstance(tag, APIC):
                    cover_data = tag.data
                    break
        elif hasattr(audio, 'tags') and 'covr' in audio.tags:
            cover_data = audio.tags['covr'][0]
            if isinstance(cover_data, MP4Cover):
                cover_data = bytes(cover_data)
        return cover_data
    except Exception as e:
        logger.warning(f"Не удалось извлечь обложку из аудио: {e}")
        return None

def get_audio_duration(file_path: Path) -> int:
    try:
        if file_path.suffix.lower() == '.m4a':
            audio = MP4(file_path)
            return int(audio.info.length)
        else:
            audio = MP3(file_path)
            return int(audio.info.length)
    except Exception as e:
        logger.warning(f"Не удалось получить длительность из файла: {e}")
        return 0

def check_disk_space(min_free_mb: int = MIN_FREE_DISK_MB) -> tuple[bool, float]:
    try:
        stat = shutil.disk_usage(Path.cwd())
        free_mb = stat.free / (1024 * 1024)
        if free_mb < min_free_mb:
            logger.warning(f"Мало места на диске: {free_mb:.1f} МБ свободно (нужно {min_free_mb} МБ)")
            return False, free_mb
        return True, free_mb
    except Exception as e:
        logger.error(f"Ошибка проверки диска: {e}")
        return True, 9999

def cleanup_old_tmp_dirs():
    count = 0
    for tmp_dir in Path('.').glob('bocchi_tmp_*'):
        if tmp_dir.is_dir():
            shutil.rmtree(tmp_dir, ignore_errors=True)
            count += 1
    if count:
        logger.info(f"Удалено временных папок: {count}")

def add_stats(bytes_added):
    try:
        current = 0.0
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, "r") as f:
                current = float(f.read())
        with open(STATS_FILE, "w") as f:
            f.write(str(current + bytes_added))
    except:
        pass

def get_formatted_stats():
    try:
        if not os.path.exists(STATS_FILE):
            return "0 Б"
        with open(STATS_FILE, "r") as f:
            bytes_val = float(f.read())
        for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.2f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.2f} ТБ"
    except:
        return "0 Б"

def get_ping():
    """Пинг до ya.ru (ICMP, при неудаче – HTTP HEAD)"""
    try:
        output = subprocess.check_output(["ping", "-c", "1", "-W", "1", "ya.ru"], stderr=subprocess.STDOUT, text=True)
        match = re.search(r'time=([\d\.]+)', output)
        if match:
            return float(match.group(1))
    except:
        pass
    try:
        import requests
        resp = requests.head("https://ya.ru", timeout=2)
        if resp.status_code:
            return 1.0  # символическое значение
    except:
        pass
    return 0.0

def get_user_quality(context: ContextTypes.DEFAULT_TYPE) -> int:
    return context.user_data.get('quality', DEFAULT_QUALITY)

def set_user_quality(context: ContextTypes.DEFAULT_TYPE, quality: int):
    if quality in QUALITY_NAMES:
        context.user_data['quality'] = quality
        return True
    return False

def extract_base_url(url: str) -> str:
    match = re.match(r'(https?://(?:[a-z0-9-]+\.)*yandex\.[a-z]{2,3})(?:/music)?', url, re.IGNORECASE)
    if match:
        base_domain = match.group(1)
        if '/music' in url or re.search(r'//music\.', url, re.IGNORECASE):
            return base_domain
        return f"{base_domain}/music"
    return "https://music.yandex.ru"

def parse_yandex_url(url: str):
    """Улучшенный парсинг ссылок Яндекс.Музыки, включая iframe и UUID плейлистов."""
    parsed = urlparse(url)
    path = parsed.path
    query = parse_qs(parsed.query)

    iframe_match = re.search(r'/iframe/playlist/([^/]+)/(\d+)', path)
    if iframe_match:
        return ('iframe_playlist', iframe_match.group(2), iframe_match.group(1))

    track_match = re.search(r'/track/(\d+)', path)
    if track_match:
        return ('track', track_match.group(1), None)

    album_match = re.search(r'/album/(\d+)', path)
    if album_match:
        return ('album', album_match.group(1), None)

    playlist_match = re.search(r'/users/([^/]+)/playlists/(\d+)', path)
    if playlist_match:
        return ('playlist', playlist_match.group(2), playlist_match.group(1))

    playlist_match2 = re.search(r'/playlist/(\d+)', path)
    if playlist_match2:
        return ('playlist', playlist_match2.group(1), None)

    playlist_uuid_match = re.search(r'/playlists/([a-z0-9\-\.]+)', path)
    if playlist_uuid_match:
        return ('uuid_playlist', playlist_uuid_match.group(1), None)

    if 'handlers/playlist.jsx' in path:
        owner = query.get('owner', [None])[0]
        kinds = query.get('kinds', [None])[0]
        if owner and kinds:
            return ('playlist', kinds, owner)

    return (None, None, None)

async def send_animated_message(bot, chat_id, text, delay=0.4, max_retries=3, **kwargs):
    draft_id = int(time.time() * 1000) + random.randint(1, 10000)
    for attempt in range(max_retries):
        try:
            await bot.send_message_draft(chat_id=chat_id, draft_id=draft_id, text=text)
            await asyncio.sleep(delay)
            msg = await bot.send_message(chat_id=chat_id, text=text, **kwargs)
            # Очищаем черновик пустым сообщением
            try:
                await bot.send_message_draft(chat_id=chat_id, draft_id=draft_id, text=" ")
            except Exception:
                pass
            return msg
        except Exception as e:
            logger.warning(f"Анимация {attempt+1}: {e}")
            if attempt == max_retries - 1:
                return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
            await asyncio.sleep(0.5 * (attempt + 1))
    return await bot.send_message(chat_id=chat_id, text=text, **kwargs)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_animated_message(
        context.bot, update.effective_chat.id,
        "🎸 Главное меню:",
        reply_markup=main_markup
    )

async def show_main_menu_from_chat(bot, chat_id):
    await send_animated_message(
        bot, chat_id,
        "🎸 Главное меню:",
        reply_markup=main_markup
    )

async def cmd_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update):
        return
    current = get_user_quality(context)
    await update.message.reply_text(
        f"🎵 Текущее качество: *{QUALITY_NAMES[current]}*\n\n"
        f"Выберите новое качество кнопками ниже:",
        parse_mode='Markdown',
        reply_markup=quality_markup
    )

# ===================== СТАТУС С АНИМАЦИЕЙ (без температуры и маскировки) =====================
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update):
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # Закрываем предыдущий черновик, если был
    old_draft = context.user_data.get('status_draft')
    if old_draft:
        try:
            await context.bot.send_message(chat_id=old_draft['chat_id'], text="⏹️ Предыдущий запрос статуса прерван новым.")
            await context.bot.send_message_draft(chat_id=old_draft['chat_id'], draft_id=old_draft['draft_id'], text=" ")
        except Exception as e:
            logger.warning(f"Не удалось закрыть старый черновик: {e}")
        context.user_data.pop('status_draft', None)

    draft_id = int(time.time() * 1000) + user_id

    try:
        await context.bot.send_message_draft(chat_id=chat_id, draft_id=draft_id, text="🌸 Секретный блокнот Хитори 🎸\n\nПодожди, собираю данные...")
        context.user_data['status_draft'] = {'draft_id': draft_id, 'chat_id': chat_id}
    except Exception as e:
        logger.error(f"Ошибка запуска черновика: {e}")
        await send_animated_message(context.bot, chat_id, "❌ Не удалось отобразить анимацию статуса. Попробуй позже.")
        await show_main_menu(update, context)
        return

    try:
        steps = 8
        anim_frames = ["🎸", "🎧", "🌸", "🎵"]   # или пустые строки, если убираем эмодзи
        for step in range(1, steps + 1):
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory()

            if cpu < 15:
                c_status = "тихим ожиданием новых задач"
            elif cpu < 45:
                c_status = "активной проверкой твоих ссылок"
            elif cpu < 80:
                c_status = "сложными расчетами и очередью"
            else:
                c_status = "попытками не сломаться от нагрузки"

            if mem.percent < 30:
                m_status = "приятной пустотой, мне дышится легко"
            elif mem.percent < 70:
                m_status = "самыми важными вещами, всё под рукой"
            else:
                m_status = "почти целиком, мне становится тесно"

            res_block = (
                "Моё самочувствие 🌸\n"
                f"• Мысли заняты {c_status} ({cpu}%)\n"
                f"• Память заполнена {m_status} ({mem.percent}%)\n\n"
            )

            ping_val = get_ping()
            if ping_val > 0:
                if ping_val < 20:
                    n_lvl = "сейчас просто идеальная"
                elif ping_val < 60:
                    n_lvl = "вполне стабильная"
                elif ping_val < 100:
                    n_lvl = "стала какой-то слабой"
                else:
                    n_lvl = "почти совсем пропала..."
                net_text = f"• Сеть: {n_lvl} ({ping_val} мс до Яндекса)\n\n"
            else:
                net_text = "• Сеть: не могу достучаться до Яндекса...\n\n"

            queue_size = active_tasks_count
            if queue_size == 0:
                queue_text = "• Сейчас я свободна, жду новых ссылок 🎸"
            elif queue_size == 1:
                queue_text = f"• Сейчас меня ждёт {get_plural_tracks(queue_size)}"
            else:
                queue_text = f"• Сейчас меня ждут {get_plural_tracks(queue_size)}"
            work_block = (
                "Очередь и загрузки 📥\n"
                f"{queue_text}\n"
                f"• Всего с запуска я нашла треков на целых {get_formatted_stats()}\n\n"
            )

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
                        await context.bot.send_message(chat_id=chat_id, text="❌ Ошибка при обновлении статуса. Попробуй позже.")
                        # Очищаем черновик при ошибке
                        try:
                            await context.bot.send_message_draft(chat_id=chat_id, draft_id=draft_id, text=" ")
                        except:
                            pass
                        context.user_data.pop('status_draft', None)
                        await show_main_menu(update, context)
                        return
                    await asyncio.sleep(0.5)
            await asyncio.sleep(2)
    finally:
        # Вместо удаления отправляем пустой черновик (очистка)
        try:
            await context.bot.send_message_draft(chat_id=chat_id, draft_id=draft_id, text=" ")
        except Exception as e:
            logger.warning(f"Не удалось очистить черновик статуса: {e}")
        context.user_data.pop('status_draft', None)

    await show_main_menu(update, context)
# ===================== ХЕНДЛЕРЫ АВТОРИЗАЦИИ =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update):
        return WAITING_FOR_LINK
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    lock = user_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        user_locks[user_id] = lock
    async with lock:
        kb = [[KeyboardButton("🎵 Начать работу")]]
        welcome = (
            "🌸 Привет! Я Боччи… То есть Bocchi Downloader 🎸\n\n"
            "Я живу на сервере и попробую помочь скачать музыку из Яндекс.Музыки.\n\n"
            "✨ Как это работает:\n"
            f"• Можно прислать до {MAX_LINKS} ссылок за раз.\n"
            "• Я буду скачивать всё по очереди, аккуратно…\n\n"
            "⚠️ Высокое качество нагружает сервер. Если я зависну, попробуй понизить качество.\n\n"
            "Нажми кнопку внизу, чтобы войти в аккаунт и начать!"
        )
        await send_animated_message(
            context.bot, chat_id,
            welcome,
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
        return WAITING_FOR_LINK

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update):
        return WAITING_FOR_LINK
    if user_processing.get(update.effective_user.id):
        await update.message.reply_text(
            "⏳ Я пока занята загрузкой… Дождись завершения или нажми «⏹ Отменить загрузку»."
        )
        return WAITING_FOR_LINK
    await show_main_menu(update, context)
    return WAITING_FOR_LINK

async def check_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update):
        return WAITING_FOR_LINK
    user_id = update.effective_user.id
    lock = user_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        user_locks[user_id] = lock
    async with lock:
        if is_token_valid(context):
            await send_animated_message(
                context.bot, update.effective_chat.id,
                "✅ Токен уже активен! Возвращаюсь в главное меню.",
                reply_markup=main_markup
            )
            return WAITING_FOR_LINK
        last_request = context.user_data.get('last_auth_request_time', 0)
        if time.time() - last_request < 5:
            logger.info(f"Игнорируем частый запрос токена от {user_id}")
            return WAITING_FOR_TOKEN
        context.user_data['last_auth_request_time'] = time.time()
        auth_text = (
            "🔑 Авторизация\n\n"
            "1️⃣ Перейди по [ссылке](https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41195d)\n"
            "2️⃣ Нажми «Войти» или «Разрешить».\n"
            "3️⃣ Страница может стать пустой — это нормально!\n"
            "4️⃣ Скопируй весь адрес из строки браузера и отправь мне."
        )
        await send_animated_message(
            context.bot, update.effective_chat.id,
            auth_text,
            parse_mode="Markdown", disable_web_page_preview=True
        )
        return WAITING_FOR_TOKEN

async def save_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update):
        return WAITING_FOR_TOKEN
    user_id = update.effective_user.id
    msg_id = update.message.message_id
    if last_processed_msg.get(user_id) == msg_id:
        return WAITING_FOR_TOKEN
    last_processed_msg[user_id] = msg_id
    raw_text = update.message.text.strip()
    token_match = re.search(r"(y0_[a-zA-Z0-9_-]+)", raw_text)
    if token_match:
        token = token_match.group(1)
    else:
        access_match = re.search(r"access_token=([^&]+)", raw_text)
        token = access_match.group(1) if access_match else None
    if token is None:
        await send_animated_message(
            context.bot, update.effective_chat.id,
            "❌ Я не смогла найти токен… Попробуй ещё раз, пожалуйста."
        )
        return WAITING_FOR_TOKEN
    try:
        await update.message.delete()
    except:
        pass
    status_msg = await update.message.reply_text("🔍 Проверяю токен…")

    # Попытка 1: через ClientAsync
    try:
        client = ClientAsync(token)
        await client.init()
        account_status = await client.account_status()
        if not account_status or not account_status.account:
            raise Exception("Не удалось получить данные аккаунта через ClientAsync")
        login = account_status.account.login
        set_user_token(user_id, token)
        context.user_data['yandex_token'] = token
        context.user_data['token_time'] = time.time()
        last_auth_warning.pop(user_id, None)
        await status_msg.edit_text(f"✅ Ура! Я узнала тебя, {login}! Теперь всё готово.")
        await show_main_menu(update, context)
        return WAITING_FOR_LINK
    except Exception as e:
        logger.warning(f"ClientAsync не сработал: {type(e).__name__}: {e}")

    # Попытка 2: прямой HTTP-запрос
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
                        last_auth_warning.pop(user_id, None)
                        await status_msg.edit_text(f"✅ Ура! Я узнала тебя, {login}! Теперь всё готово.")
                        await show_main_menu(update, context)
                        return WAITING_FOR_LINK
                logger.warning(f"HTTP-проверка вернула статус {resp.status}")
    except Exception as e2:
        logger.error(f"Ошибка HTTP-проверки: {type(e2).__name__}: {e2}")

    await status_msg.edit_text("❌ Токен не подходит… Попробуй ещё раз.")
    return WAITING_FOR_TOKEN

async def cmd_logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update):
        return
    user_id = update.effective_user.id
    delete_user_token(user_id)
    context.user_data.pop('yandex_token', None)
    context.user_data.pop('token_time', None)
    await send_animated_message(
        context.bot, update.effective_chat.id,
        "🔓 Токен удалён. Ты вышел из аккаунта."
    )
    kb = [[KeyboardButton("🎵 Начать работу")]]
    await send_animated_message(
        context.bot, update.effective_chat.id,
        "Чтобы продолжить, авторизуйся заново.",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_animated_message(
        context.bot, update.effective_chat.id,
        "❌ Действие отменено. Напиши /start, если захочешь начать заново."
    )
    return ConversationHandler.END

# ===================== ОТМЕНА ЗАГРУЗКИ С ПОЛНЫМ ОПИСАНИЕМ =====================
async def cancel_download(update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback=False):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Собираем задачи текущего пользователя
    tasks_to_cancel = []
    for task_id, info in list(current_task_info.items()):
        if info['chat_id'] == chat_id:
            tasks_to_cancel.append((task_id, info))

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
        batch_index = task.get('batch_index', 0)
        batch_total = task.get('batch_total', 0)

        # Формируем полное описание
        if batch_type == 'album':
            desc = f"альбома «{batch_name}» (трек {batch_index} из {batch_total})"
        elif batch_type == 'playlist':
            desc = f"плейлиста «{batch_name}» (трек {batch_index} из {batch_total})"
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
        # Удаляем статусное сообщение
        msg_id = active_status_msgs.pop(task_id, {}).get('message_id')
        if msg_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except:
                pass
        current_task_info.pop(task_id, None)
        cancelled_count += 1

    # Удаляем задачи этого пользователя из очереди и обновляем счётчик
    remaining_tasks = []
    removed_from_queue = 0
    while not download_queue.empty():
        try:
            t = download_queue.get_nowait()
            if t.get('user_id') != user_id:
                remaining_tasks.append(t)
            else:
                removed_from_queue += 1
        except asyncio.QueueEmpty:
            break
    for t in remaining_tasks:
        await download_queue.put(t)

    # Корректируем глобальный счётчик активных задач
    global active_tasks_count
    active_tasks_count -= (cancelled_count + removed_from_queue)
    if active_tasks_count < 0:
        active_tasks_count = 0

    save_queue_state()
    total_cancelled = cancelled_count + removed_from_queue
    msg = f"✅ Загрузка отменена. Отменено задач: {total_cancelled}."
    if is_callback:
        await update.callback_query.edit_message_text(msg)
    else:
        await update.message.reply_text(msg)
    await show_main_menu_from_chat(context.bot, chat_id)

async def cancel_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cancel_download(update, context, is_callback=True)

# ===================== ЭКСТРЕННАЯ ОСТАНОВКА (KILLSWITCH) =====================
async def emergency_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text("🛑 Экстренная остановка… Убиваю процессы и чищу очередь.")

    # Убиваем все текущие процессы
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

    # Очищаем очередь
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

# ===================== ПЕРЕЗАПУСК ЗАВИСШЕЙ ЗАДАЧИ =====================
async def restart_stuck_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    stuck_task_id = None
    stuck_info = None
    for task_id, info in current_task_info.items():
        if info['chat_id'] == chat_id:
            stuck_task_id = task_id
            stuck_info = info
            break
    if not stuck_info:
        await query.edit_message_text("❌ Нет зависших задач для этого чата.")
        return
    proc = stuck_info.get('process')
    if proc and not proc.returncode:
        try:
            proc.kill()
            await proc.wait()
            logger.info(f"Убит зависший процесс для задачи {stuck_task_id}")
        except Exception as e:
            logger.error(f"Ошибка при убийстве процесса: {e}")
    msg_id = active_status_msgs.pop(stuck_task_id, {}).get('message_id')
    if msg_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except:
            pass
    current_task_info.pop(stuck_task_id, None)
    task = stuck_info['task']
    await download_queue.put(task)
    global active_tasks_count
    active_tasks_count += 1  # вернули задачу в очередь
    await query.edit_message_text(f"🔄 Задача «{task['track_name']}» перезапущена. Продолжаю загрузку…")
    logger.info(f"Задача {stuck_task_id} перезапущена пользователем")

# ===================== ОБРАБОТЧИК СООБЩЕНИЙ =====================
async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update):
        return WAITING_FOR_LINK
    user_id = update.effective_user.id
    msg_id = update.message.message_id
    if last_processed_msg.get(user_id) == msg_id:
        return WAITING_FOR_LINK
    last_processed_msg[user_id] = msg_id
    text = update.message.text

    if text == "🎵 Начать работу":
        return await check_session(update, context)
    if text == "▶ Начать загрузку":
        await send_animated_message(
            context.bot, update.effective_chat.id,
            "🎵 Присылай ссылки на треки, альбомы или плейлисты. Я постараюсь всё скачать…"
        )
        return WAITING_FOR_LINK
    if text == "🔓 Удалить токен":
        await cmd_logout(update, context)
        return WAITING_FOR_LINK
    if text == "🔄 Обновить токен":
        await send_animated_message(
            context.bot, update.effective_chat.id,
            "🔑 Пожалуйста, отправь новый токен."
        )
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
                f"⚠️ Высокое качество нагружает сервер. Если я зависну, попробуй понизить.",
                parse_mode='Markdown',
                reply_markup=main_markup
            )
        else:
            await update.message.reply_text("❌ Не получилось сменить качество…")
        return WAITING_FOR_LINK

    chat_id = update.effective_chat.id
    message = update.message

    # Попытка извлечь ссылку из HTML-кода
    if 'iframe' in text and 'music.yandex' in text:
        src_match = re.search(r'src="(https?://music\.yandex\.[a-z]{2,3}/[^"]+)"', text, re.IGNORECASE)
        if src_match:
            src_url = src_match.group(1)
            logger.info(f"Извлечена ссылка из HTML: {src_url}")
            text = src_url
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🔍 Нашла в коде ссылку на плейлист. Продолжаю обработку...",
                reply_to_message_id=message.message_id
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Не удалось найти ссылку в HTML-коде. Убедитесь, что вы скопировали код полностью."
            )
            return WAITING_FOR_LINK

    pending = get_pending_tasks(chat_id)
    if pending:
        await context.bot.send_message(chat_id, f"🔄 Нашла отложенные задачи ({len(pending)} треков). Продолжаю загрузку…")
        for task in pending:
            await download_queue.put(task)
        clear_pending_tasks(chat_id)

    if not is_token_valid(context):
        try:
            await message.delete()
        except:
            pass
        now = time.time()
        last = last_auth_warning.get(user_id, 0)
        if now - last > WARNING_COOLDOWN:
            last_auth_warning[user_id] = now
            auth_text = (
                "🔑 Авторизация\n\n"
                "1️⃣ Перейди по [ссылке](https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41195d)\n"
                "2️⃣ Нажми «Войти» или «Разрешить».\n"
                "3️⃣ Страница может стать пустой — это нормально!\n"
                "4️⃣ Скопируй весь адрес из строки браузера и отправь мне."
            )
            await send_animated_message(
                context.bot, chat_id,
                auth_text,
                parse_mode="Markdown", disable_web_page_preview=True
            )
        return WAITING_FOR_TOKEN

    content = text + " " + (update.message.caption or "")
    url_pattern = re.compile(r'https?://(?:[a-z0-9-]+\.)*yandex\.[a-z]{2,3}(?:/music)?(?:/[^\s]+)?', re.IGNORECASE)
    urls = url_pattern.findall(content)
    valid_urls = []
    for u in urls:
        u = u.rstrip('.,!?;:()[]{}"\'')
        parsed = parse_yandex_url(u)
        if parsed[0] is not None:
            valid_urls.append(u)

    if not valid_urls:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Я не смогла распознать ссылку… Может, попробуешь ещё раз?"
        )
        return WAITING_FOR_LINK

    if user_id in user_delay_tasks:
        user_delay_tasks[user_id].cancel()
    if user_id not in link_accumulators:
        link_accumulators[user_id] = []
    link_accumulators[user_id].extend(valid_urls)

    if user_processing.get(user_id):
        await context.bot.send_message(
            chat_id=chat_id,
            text="🔄 Я пока занята предыдущей загрузкой… Подожди немножко, хорошо?",
            reply_to_message_id=update.message.message_id
        )
        try:
            await message.delete()
        except:
            pass
        return WAITING_FOR_LINK

    async def safe_process():
        await asyncio.sleep(ACCUMULATION_DELAY)
        token = get_user_token(user_id)
        if not token:
            await context.bot.send_message(chat_id, "❌ Токен куда-то пропал… Может, войдёшь заново?")
            return
        try:
            await process_accumulated_links(user_id, chat_id, context, token)
        except Exception as e:
            logger.error(f"Ошибка обработки: {e}", exc_info=True)
            try:
                await context.bot.send_message(chat_id, f"❌ Ой-ой… Что-то пошло не так: {str(e)[:200]}")
            except:
                pass
        finally:
            user_processing.pop(user_id, None)
            link_accumulators.pop(user_id, None)

    task = asyncio.create_task(safe_process())
    user_delay_tasks[user_id] = task

    confirm_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"📎 Я приняла ссылки… Сейчас посчитаю, сколько треков, и начну готовить. Немного терпения, ладно?",
        reply_to_message_id=update.message.message_id
    )

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

# ===================== ОСНОВНАЯ ЛОГИКА ОБРАБОТКИ ССЫЛОК (ПАКЕТНАЯ) =====================
async def process_accumulated_links(user_id, chat_id, context, token):
    user_processing[user_id] = True
    user_delay_tasks.pop(user_id, None)
    await asyncio.sleep(ACCUMULATION_DELAY)

    if user_id not in link_accumulators or not link_accumulators[user_id]:
        user_processing.pop(user_id, None)
        return

    raw_links = list(dict.fromkeys(link_accumulators.pop(user_id)))[:MAX_LINKS]
    if not raw_links:
        return

    logger.info(f"Ссылки от {user_id}: {raw_links}")

    try:
        client = ClientAsync(token)
        await client.init()
    except Exception as e:
        logger.error(f"Ошибка создания клиента: {e}")
        await context.bot.send_message(chat_id, "❌ Ошибка авторизации. Попробуй снова.")
        return

    all_tracks = []
    first_type = None
    batch_info = {}

    for url in raw_links:
        base_url = extract_base_url(url)
        content_type, content_id, username = parse_yandex_url(url)

        if not content_type:
            await context.bot.send_message(chat_id, f"❌ Не удалось распознать ссылку: {url}")
            continue

        try:
            if content_type == 'track':
                tracks_info = await client.tracks([content_id])
                if tracks_info and len(tracks_info) > 0:
                    t = tracks_info[0]
                    artist = ', '.join([a.name for a in t.artists]) if t.artists else "Неизвестен"
                    title = t.title
                    version_info = t.version
                    if version_info:
                        title = f"{title} ({version_info})"
                    track_name = f"{artist} — {title}"
                    cover_uri = t.cover_uri
                    cover_bytes = await fetch_cover_from_yandex(cover_uri) if cover_uri else None
                    album_name = t.albums[0].title if t.albums else None
                    year = t.albums[0].year if t.albums and t.albums[0].year else None
                    genre = t.albums[0].genre if t.albums and t.albums[0].genre else None
                    all_tracks.append({
                        'url': url,
                        'artist': artist,
                        'title': title,
                        'duration': t.duration_ms // 1000 if t.duration_ms else 0,
                        'track_name': track_name,
                        'cover_bytes': cover_bytes,
                        'album': album_name,
                        'year': year,
                        'genre': genre,
                        'batch_type': None,
                        'batch_name': None,
                        'batch_artist': None,
                        'batch_owner': None,
                        'batch_total': 1,
                        'batch_index': 1
                    })
                else:
                    await context.bot.send_message(chat_id, f"❌ Трек не найден: {url}")

            elif content_type == 'album':
                album = await client.albums_with_tracks(content_id)
                if not album or not album.volumes:
                    await context.bot.send_message(chat_id, f"❌ Альбом не найден: {url}")
                    continue
                album_title = album.title or "Неизвестный альбом"
                album_artist = ', '.join([a.name for a in album.artists]) if album.artists else 'Разные исполнители'
                cover_uri = album.cover_uri
                album_cover_bytes = await fetch_cover_from_yandex(cover_uri) if cover_uri else None
                year = album.year
                genre = album.genre
                track_list = []
                for volume in album.volumes:
                    for track in volume:
                        if not track:
                            continue
                        artist = ', '.join([a.name for a in track.artists]) if track.artists else "Неизвестен"
                        title = track.title
                        version_info = track.version
                        if version_info:
                            title = f"{title} ({version_info})"
                        track_cover_uri = track.cover_uri
                        cover_bytes = await fetch_cover_from_yandex(track_cover_uri) if track_cover_uri else album_cover_bytes
                        track_list.append({
                            'url': f"{base_url}/track/{track.id}",
                            'artist': artist,
                            'title': title,
                            'duration': track.duration_ms // 1000 if track.duration_ms else 0,
                            'track_name': f"{artist} — {title}",
                            'cover_bytes': cover_bytes,
                            'album': album_title,
                            'year': year,
                            'genre': genre
                        })
                if not track_list:
                    await context.bot.send_message(chat_id, f"❌ Альбом пуст: {url}")
                    continue
                for idx, t in enumerate(track_list, 1):
                    t.update({
                        'batch_type': 'album',
                        'batch_name': album_title,
                        'batch_artist': album_artist,
                        'batch_total': len(track_list),
                        'batch_index': idx
                    })
                all_tracks.extend(track_list)
                first_type = 'album'
                batch_info = {'name': album_title, 'artist': album_artist}

            elif content_type in ('playlist', 'uuid_playlist', 'iframe_playlist'):
                headers = {"Authorization": f"OAuth {token}"}
                api_url = f"https://api.music.yandex.net/playlist/{content_id}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(api_url, headers=headers) as resp:
                        if resp.status != 200:
                            await context.bot.send_message(chat_id, f"❌ Не удалось загрузить плейлист. Возможно, он приватный или удалён.")
                            continue
                        data = await resp.json()
                        playlist_data = data.get("result")
                        if not playlist_data:
                            await context.bot.send_message(chat_id, f"❌ Плейлист пуст или недоступен: {url}")
                            continue

                playlist_title = playlist_data.get('title', 'Неизвестный плейлист')
                owner = playlist_data.get('owner', {})
                owner_name = owner.get('name') or owner.get('login') or 'Неизвестный пользователь'

                track_list = []
                for item in playlist_data.get('tracks', []):
                    track = item.get('track')
                    if not track:
                        continue
                    track_id = track.get('id')
                    if not track_id:
                        continue

                    artist = ', '.join([a.get('name', 'Неизвестен') for a in track.get('artists', [])]) or "Неизвестен"
                    title = track.get('title', 'Неизвестный трек')
                    version_info = track.get('version') or track.get('subtitle')
                    if version_info:
                        title = f"{title} ({version_info})"

                    cover_uri = track.get('cover_uri')
                    cover_bytes = await fetch_cover_from_yandex(cover_uri) if cover_uri else None

                    album_info = track.get('albums', [{}])[0] if track.get('albums') else {}
                    album_name = album_info.get('title')
                    year = album_info.get('year')
                    genre = album_info.get('genre')

                    track_list.append({
                        'url': f"{base_url}/track/{track_id}",
                        'artist': artist,
                        'title': title,
                        'duration': track.get('duration_ms', 0) // 1000,
                        'track_name': f"{artist} — {title}",
                        'cover_bytes': cover_bytes,
                        'album': album_name,
                        'year': year,
                        'genre': genre
                    })

                if not track_list:
                    await context.bot.send_message(chat_id, f"❌ Не удалось загрузить ни одного трека из плейлиста: {url}")
                    continue

                for idx, t in enumerate(track_list, 1):
                    t.update({
                        'batch_type': 'playlist',
                        'batch_name': playlist_title,
                        'batch_owner': owner_name,
                        'batch_total': len(track_list),
                        'batch_index': idx
                    })
                all_tracks.extend(track_list)
                first_type = 'playlist'
                batch_info = {'name': playlist_title, 'owner': owner_name}

        except Exception as e:
            logger.error(f"Ошибка парсинга {url}: {e}")
            await context.bot.send_message(chat_id, f"❌ Ошибка при обработке ссылки {url}: {str(e)[:100]}")

    if not all_tracks:
        await context.bot.send_message(chat_id, "❌ Не удалось найти треки по ссылкам.")
        return

    batch_types = set(t.get('batch_type') for t in all_tracks)
    if len(batch_types) == 1 and None not in batch_types:
        first_type = next(iter(batch_types))

    total_tracks = len(all_tracks)
    current_queue_size = download_queue.qsize()
    batch_id = f"{user_id}_{int(time.time())}_{uuid.uuid4().hex[:8]}"

    if first_type == 'album':
        content_desc = f"альбом «{batch_info.get('name', 'Неизвестный альбом')}»"
    elif first_type == 'playlist':
        content_desc = f"плейлист «{batch_info.get('name', 'Неизвестный плейлист')}»"
    else:
        content_desc = "треки"

    queue_pos = current_queue_size + 1
    await context.bot.send_message(
        chat_id,
        f"📥 Я получила {get_plural_tracks(total_tracks)} из {content_desc}. "
        f"Твоя очередь — номер {queue_pos}… Я постараюсь всё скачать аккуратно, "
        f"пожалуйста, не сердись, если что-то пойдёт не так…"
    )

    for idx, track_info in enumerate(all_tracks):
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
            'batch_index': track_info.get('batch_index', idx+1),
            'batch_total': track_info.get('batch_total', total_tracks),
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
    active_tasks_count += total_tracks
    save_queue_state()

# ===================== СОХРАНЕНИЕ И ВОССТАНОВЛЕНИЕ ОЧЕРЕДИ =====================
def save_queue_state():
    try:
        tasks = []
        while not download_queue.empty():
            try:
                task = download_queue.get_nowait()
                tasks.append(task)
            except asyncio.QueueEmpty:
                break
        for task in tasks:
            download_queue.put_nowait(task)
        with open(QUEUE_STATE_FILE, 'w', encoding='utf-8') as f:
            serializable = []
            for t in tasks:
                t_copy = t.copy()
                t_copy.pop('cover_bytes', None)
                serializable.append(t_copy)
            json.dump(serializable, f, ensure_ascii=False, indent=2)
        logger.info(f"Сохранено {len(tasks)} задач в очередь")
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
            user_id = task.get('user_id')
            if user_id:
                token = get_user_token(user_id)
                if token:
                    task['token'] = token
                    task['cover_bytes'] = None
                    valid_tasks.append(task)
                else:
                    logger.warning(f"Задача для пользователя {user_id} пропущена: нет валидного токена")
            else:
                logger.warning(f"Задача без user_id пропущена: {task.get('track_name')}")
        for task in valid_tasks:
            download_queue.put_nowait(task)
        logger.info(f"Восстановлено {len(valid_tasks)} задач из очереди")
        os.remove(QUEUE_STATE_FILE)
    except Exception as e:
        logger.error(f"Ошибка загрузки очереди: {e}")

# ===================== ВОРКЕР =====================
async def worker_loop(app):
    global worker_busy, active_tasks_count
    chat_temp_msg = {}

    while True:
        try:
            if not shutil.which(DOWNLOADER_PATH):
                logger.error(f"Загрузчик {DOWNLOADER_PATH} не найден")
                await asyncio.sleep(60)
                continue
            logger.info("Воркер запущен")
            while True:
                task = await download_queue.get()
                worker_busy = True
                tmp_dir = Path(f"bocchi_tmp_{uuid.uuid4().hex}")
                current_quality = task.get('quality', DEFAULT_QUALITY)
                actual_quality_used = None
                task_id = f"{task.get('batch_id')}_{task.get('batch_index')}"
                chat_id = task['chat_id']

                async with download_semaphore:
                    status_msg = None
                    stuck_notification_sent = False
                    downloader_process = None
                    try:
                        old_info = active_status_msgs.pop(task_id, None)
                        if old_info:
                            try:
                                await app.bot.delete_message(chat_id=old_info['chat_id'], message_id=old_info['message_id'])
                            except:
                                pass
                        prev = chat_temp_msg.pop(chat_id, None)
                        if prev:
                            try:
                                await app.bot.delete_message(chat_id=chat_id, message_id=prev)
                            except:
                                pass

                        tmp_dir.mkdir(parents=True, exist_ok=True)
                        keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton("⏹ Отменить загрузку", callback_data="cancel_download")]
                        ])

                        batch_type = task.get('batch_type')
                        batch_name = task.get('batch_name')
                        batch_artist = task.get('batch_artist')
                        batch_owner = task.get('batch_owner')
                        batch_index = task.get('batch_index', 1)
                        batch_total = task.get('batch_total', 1)

                        if batch_type == 'album':
                            header = f"📀 Альбом: {batch_name}\n🎤 {batch_artist}\n"
                        elif batch_type == 'playlist':
                            header = f"📋 Плейлист: {batch_name}\n👤 {batch_owner}\n"
                        elif batch_total > 1:
                            header = f"📦 Пакет треков ({batch_total} шт.)\n"
                        else:
                            header = ""

                        progress = f"({batch_index} из {batch_total})" if batch_total > 1 else ""
                        status_text = (
                            f"🌀 Обрабатываю… {progress}\n"
                            f"{header}"
                            f"🎵 Трек: {task['track_name']}\n"
                            f"⚙️ Качество: {QUALITY_NAMES[current_quality]}"
                        )
                        status_msg = await app.bot.send_message(
                            chat_id=chat_id,
                            text=status_text,
                            reply_markup=keyboard
                        )
                        active_status_msgs[task_id] = {"chat_id": chat_id, "message_id": status_msg.message_id}
                        save_active_msgs()

                        await app.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

                        start_time = time.time()
                        current_task_info[task_id] = {
                            "start_time": start_time,
                            "chat_id": chat_id,
                            "task": task,
                            "process": None,
                            "status_msg_id": status_msg.message_id
                        }

                        async def run_downloader(quality, tmp_dir_path):
                            nonlocal downloader_process
                            cmd = [
                                DOWNLOADER_PATH,
                                "--token", task['token'],
                                "--quality", str(quality),
                                "--embed-cover",
                                "--cover-resolution", "original",
                                "--lyrics-format", "lrc",
                                "--dir", str(tmp_dir_path),
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
                            try:
                                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=DOWNLOAD_TIMEOUT)
                                return proc.returncode, stdout, stderr
                            except asyncio.TimeoutError:
                                proc.kill()
                                return -1, b'', b'Timeout'

                        success = False
                        attempt = 0
                        max_attempts = 3
                        quality_to_try = current_quality

                        while attempt < max_attempts and not success:
                            if time.time() - start_time > STUCK_TIMEOUT and not stuck_notification_sent:
                                stuck_notification_sent = True
                                new_keyboard = InlineKeyboardMarkup([
                                    [InlineKeyboardButton("⏹ Отменить загрузку", callback_data="cancel_download")],
                                    [InlineKeyboardButton("🔄 Перезапустить загрузчик", callback_data="restart_stuck_task")]
                                ])
                                try:
                                    await app.bot.edit_message_reply_markup(
                                        chat_id=chat_id,
                                        message_id=status_msg.message_id,
                                        reply_markup=new_keyboard
                                    )
                                    logger.warning(f"Задача {task_id} зависла, добавлена кнопка перезапуска")
                                except Exception as e:
                                    logger.error(f"Не удалось обновить клавиатуру: {e}")

                            enough_space, free_mb = check_disk_space(MIN_FREE_DISK_MB)
                            if not enough_space:
                                if quality_to_try > 0:
                                    new_q = quality_to_try - 1
                                    quality_gen = QUALITY_NAMES_GENITIVE[new_q]
                                    prev = chat_temp_msg.pop(chat_id, None)
                                    if prev:
                                        try:
                                            await app.bot.delete_message(chat_id=chat_id, message_id=prev)
                                        except:
                                            pass
                                    msg = await app.bot.send_message(
                                        chat_id=chat_id,
                                        text=f"⚠️ На диске осталось всего {free_mb:.1f} МБ свободного места.\n"
                                             f"Для загрузки **{task['track_name']}** в качестве *{QUALITY_NAMES[quality_to_try]}* места не хватит.\n"
                                             f"Автоматически понижаю качество до *{quality_gen}* и пробую снова.\n\n"
                                             f"Если хочешь выбрать качество вручную, нажми «Качество» в меню.",
                                        parse_mode='Markdown'
                                    )
                                    chat_temp_msg[chat_id] = msg.message_id
                                    quality_to_try = new_q
                                    attempt += 1
                                    continue
                                else:
                                    await app.bot.send_message(
                                        chat_id=chat_id,
                                        text=f"❌ На диске осталось всего {free_mb:.1f} МБ свободного места.\n"
                                             f"Даже на низком качестве недостаточно места для **{task['track_name']}**.\n"
                                             f"Пожалуйста, освободи место на сервере или попробуй позже.",
                                        parse_mode='Markdown'
                                    )
                                    break

                            returncode, stdout, stderr = await run_downloader(quality_to_try, tmp_dir)
                            if returncode == 0:
                                success = True
                                actual_quality_used = quality_to_try
                                break

                            stderr_text = stderr.decode('utf-8', errors='replace')
                            logger.warning(f"Код {returncode}, stderr: {stderr_text[:200]}")

                            shutil.rmtree(tmp_dir, ignore_errors=True)
                            tmp_dir.mkdir(parents=True, exist_ok=True)

                            if returncode == -9:
                                if quality_to_try > 0:
                                    new_q = quality_to_try - 1
                                    quality_gen = QUALITY_NAMES_GENITIVE[new_q]
                                    prev = chat_temp_msg.pop(chat_id, None)
                                    if prev:
                                        try:
                                            await app.bot.delete_message(chat_id=chat_id, message_id=prev)
                                        except:
                                            pass
                                    msg = await app.bot.send_message(
                                        chat_id=chat_id,
                                        text=f"⚠️ Серверу не хватило памяти для скачивания **{task['track_name']}**.\n"
                                             f"Автоматически понижаю качество до *{quality_gen}* и пробую снова.\n\n"
                                             f"Если хочешь выбрать качество вручную, нажми «Качество» в меню.",
                                        parse_mode='Markdown'
                                    )
                                    chat_temp_msg[chat_id] = msg.message_id
                                    quality_to_try = new_q
                                    attempt += 1
                                    continue
                                else:
                                    await app.bot.send_message(
                                        chat_id=chat_id,
                                        text=f"❌ Даже на низком качестве не хватает памяти для **{task['track_name']}**.\n"
                                             f"Попробуй позже или скачай трек в приложении.",
                                        parse_mode='Markdown'
                                    )
                                    break

                            if any(k in stderr_text.lower() for k in ['forbidden', 'blocked', 'denied', 'регион', 'недоступен', 'restricted', '403', 'доступ запрещён']):
                                await app.bot.send_message(
                                    chat_id=chat_id,
                                    text=f"❌ Яндекс заблокировал трек **{task['track_name']}**.\nВозможно, он удалён или недоступен в твоём регионе.",
                                    parse_mode='Markdown'
                                )
                                break

                            if attempt == max_attempts - 1:
                                error_msg = stderr_text[:150] if stderr_text else f"Код ошибки {returncode}"
                                await app.bot.send_message(
                                    chat_id=chat_id,
                                    text=f"❌ Не удалось скачать **{task['track_name']}**.\nОшибка: {error_msg}",
                                    parse_mode='Markdown'
                                )
                            else:
                                await asyncio.sleep(5)
                            attempt += 1

                        if not success:
                            current_task_info.pop(task_id, None)
                            save_queue_state()
                            continue

                        if actual_quality_used != current_quality:
                            prev = chat_temp_msg.pop(chat_id, None)
                            if prev:
                                try:
                                    await app.bot.delete_message(chat_id=chat_id, message_id=prev)
                                except:
                                    pass
                            msg = await app.bot.send_message(
                                chat_id=chat_id,
                                text=f"🎵 Трек **{task['track_name']}** скачан в качестве *{QUALITY_NAMES[actual_quality_used]}*.",
                                parse_mode='Markdown'
                            )
                            chat_temp_msg[chat_id] = msg.message_id

                        files = [f for f in tmp_dir.rglob('*') if f.suffix.lower() in ['.mp3', '.m4a']]
                        for f_path in files:
                            file_size_mb = f_path.stat().st_size / (1024 * 1024)

                            artist_ym = task.get('artist', 'Неизвестен')
                            title_ym = task.get('title', f_path.stem)
                            album_ym = task.get('album')
                            year_ym = task.get('year')
                            genre_ym = task.get('genre')
                            cover_bytes_ym = task.get('cover_bytes')

                            lyrics_text = None
                            lrc_files = list(tmp_dir.glob(f"{f_path.stem}.lrc"))
                            if lrc_files:
                                try:
                                    with open(lrc_files[0], 'r', encoding='utf-8') as lf:
                                        lyrics_text = lf.read().strip()
                                except Exception as e:
                                    logger.warning(f"Не удалось прочитать LRC: {e}")

                            cover_for_tags = cover_bytes_ym
                            if cover_for_tags and len(cover_for_tags) > 300 * 1024:
                                compressed = compress_cover(cover_for_tags, max_size_bytes=300*1024)
                                if compressed:
                                    cover_for_tags = compressed
                                else:
                                    cover_for_tags = None

                            try:
                                if f_path.suffix.lower() == '.m4a':
                                    audio = MP4(f_path)
                                    audio['\xa9ART'] = [artist_ym]
                                    audio['\xa9nam'] = [title_ym]
                                    if album_ym:
                                        audio['\xa9alb'] = [album_ym]
                                    if year_ym:
                                        audio['\xa9day'] = [str(year_ym)]
                                    if genre_ym:
                                        audio['\xa9gen'] = [genre_ym]
                                    if '\xa9cmt' in audio:
                                        del audio['\xa9cmt']
                                    if lyrics_text:
                                        audio['\xa9lyr'] = [lyrics_text]
                                    if cover_for_tags:
                                        audio['covr'] = [MP4Cover(cover_for_tags, imageformat=MP4Cover.FORMAT_JPEG)]
                                    audio.save()
                                else:
                                    audio = MP3(f_path, ID3=ID3)
                                    if audio.tags is None:
                                        audio.add_tags()
                                    easy = EasyID3(f_path)
                                    easy['artist'] = [artist_ym]
                                    easy['title'] = [title_ym]
                                    if album_ym:
                                        easy['album'] = [album_ym]
                                    easy.save()
                                    if audio.tags is None:
                                        audio.add_tags()
                                    audio.tags.add(TPE2(encoding=3, text=artist_ym))
                                    audio.tags.delall('COMM')
                                    if year_ym:
                                        audio.tags.add(TDRC(encoding=3, text=str(year_ym)))
                                    if genre_ym:
                                        audio.tags.add(TCON(encoding=3, text=genre_ym))
                                    if lyrics_text:
                                        audio.tags.add(USLT(encoding=3, lang='rus', desc='Lyrics', text=lyrics_text))
                                    if cover_for_tags:
                                        audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover',
                                                            data=cover_for_tags))
                                    audio.save()
                            except Exception as tag_e:
                                logger.error(f"Ошибка записи тегов в {f_path}: {tag_e}")

                            audio_tags = None
                            try:
                                if f_path.suffix.lower() == '.m4a':
                                    audio_tags = MP4(f_path)
                                else:
                                    audio_tags = MP3(f_path, ID3=ID3)
                            except Exception as e:
                                logger.warning(f"Не удалось прочитать теги из файла {f_path}: {e}")

                            artist = None
                            title = None
                            duration = get_audio_duration(f_path)

                            if audio_tags:
                                try:
                                    if f_path.suffix.lower() == '.m4a':
                                        artist = audio_tags.get('\xa9ART', [None])[0]
                                        title = audio_tags.get('\xa9nam', [None])[0]
                                    else:
                                        easy = EasyID3(f_path)
                                        artist = easy.get('artist', [None])[0]
                                        title = easy.get('title', [None])[0]
                                except Exception as e:
                                    logger.warning(f"Ошибка извлечения тегов из {f_path}: {e}")

                            if not artist:
                                artist = artist_ym
                            if not title:
                                title = title_ym

                            artist = artist.replace("#artist", "").strip()
                            title = title.replace("#artist", "").replace("#title", "").strip(" -")
                            if not artist:
                                artist = "Неизвестен"
                            if not title:
                                title = "Неизвестный трек"

                            artist = artist.replace(';', ', ')

                            display_name = f"{artist} — {title}"
                            safe_filename = re.sub(r'[\\/*?:"<>|]', "", f"{artist} - {title}{f_path.suffix}")

                            cover_bytes = extract_cover_from_audio(f_path)
                            if not cover_bytes:
                                cover_bytes = cover_bytes_ym

                            thumbnail = None
                            if cover_bytes:
                                if len(cover_bytes) > 200 * 1024:
                                    thumbnail = compress_cover(cover_bytes, max_size_bytes=200*1024)
                                else:
                                    thumbnail = cover_bytes

                            if file_size_mb > 49.0:
                                uploaded = False
                                if status_msg:
                                    try:
                                        await status_msg.edit_text(f"📦 Файл {display_name} весит {file_size_mb:.1f} МБ. Загружаю на облако...")
                                    except:
                                        pass
                                try:
                                    litterbox = LitterboxClient()
                                    url = await asyncio.wait_for(asyncio.to_thread(litterbox.upload_file, str(f_path), expire_time="24h"), timeout=CLOUD_TIMEOUT)
                                    if url:
                                        await app.bot.send_message(chat_id=chat_id, text=f"🎁 {display_name} слишком велик для Telegram.\nВременная ссылка (24ч):\n{url}", disable_web_page_preview=True)
                                        uploaded = True
                                except:
                                    pass
                                if not uploaded:
                                    try:
                                        catbox = AsyncCatboxClient()
                                        url = await asyncio.wait_for(catbox.upload(str(f_path)), timeout=CLOUD_TIMEOUT)
                                        if url:
                                            await app.bot.send_message(chat_id=chat_id, text=f"🎁 {display_name} слишком велик для Telegram.\nПостоянная ссылка:\n{url}", disable_web_page_preview=True)
                                            uploaded = True
                                    except:
                                        pass
                                if not uploaded:
                                    await app.bot.send_message(chat_id=chat_id, text=f"❌ Не удалось загрузить {display_name}.")
                            else:
                                try:
                                    with open(f_path, 'rb') as af:
                                        await app.bot.send_audio(
                                            chat_id=chat_id,
                                            audio=af,
                                            performer=artist,
                                            title=title,
                                            duration=duration,
                                            filename=safe_filename,
                                            thumbnail=thumbnail,
                                            read_timeout=600, write_timeout=600
                                        )
                                    logger.info(f"Отправлен трек: {display_name}, длительность={duration}")
                                except Exception as e:
                                    logger.error(f"Ошибка отправки аудио: {e}")
                                    try:
                                        with open(f_path, 'rb') as af:
                                            await app.bot.send_document(
                                                chat_id=chat_id,
                                                document=af,
                                                filename=safe_filename,
                                                caption=f"🎵 {display_name}\nНе удалось отправить как аудио, файл во вложении."
                                            )
                                    except Exception as e2:
                                        await app.bot.send_message(chat_id=chat_id, text=f"❌ Не удалось отправить {display_name}: {e2}")

                            add_stats(f_path.stat().st_size)
                            await asyncio.sleep(TRACK_DELAY_SECONDS)
                            gc.collect()

                            batch_total = task.get('batch_total')
                            batch_index = task.get('batch_index')
                            if batch_total and batch_index == batch_total:
                                batch_type = task.get('batch_type')
                                batch_name = task.get('batch_name')
                                if batch_type == 'album':
                                    finish_text = f"🎸 Альбом «{batch_name}» полностью загружен!"
                                elif batch_type == 'playlist':
                                    finish_text = "🎸 Плейлист полностью загружен!"
                                else:
                                    finish_text = "🎸 Всё! Я смогла обработать все треки."
                                try:
                                    await app.bot.send_message(
                                        chat_id=chat_id,
                                        text='Загружено при поддержке #BocchiIsAlive <tg-emoji emoji-id="6041593232423391328">💠</tg-emoji>',
                                        parse_mode='HTML'
                                    )
                                    await app.bot.send_message(
                                        chat_id=chat_id,
                                        text=f"{finish_text}\nВыбери, что делать дальше:",
                                        reply_markup=main_markup
                                    )
                                except Exception as e:
                                    logger.error(f"Ошибка финального сообщения: {e}")

                            if status_msg:
                                try:
                                    await asyncio.sleep(1)
                                    await status_msg.delete()
                                except:
                                    pass
                            prev = chat_temp_msg.pop(chat_id, None)
                            if prev:
                                try:
                                    await app.bot.delete_message(chat_id=chat_id, message_id=prev)
                                except:
                                    pass

                    except Exception as e:
                        logger.error(f"Ошибка воркера: {e}", exc_info=True)
                        if status_msg:
                            try:
                                await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
                            except:
                                await app.bot.send_message(chat_id=chat_id, text=f"❌ Ошибка: {str(e)[:200]}")
                        if "Forbidden" in str(e) or "Chat not found" in str(e):
                            add_pending_task(chat_id, task)
                    finally:
                        shutil.rmtree(tmp_dir, ignore_errors=True)
                        download_queue.task_done()
                        active_tasks_count -= 1
                        worker_busy = False
                        current_task_info.pop(task_id, None)
                        active_status_msgs.pop(task_id, None)
                        save_active_msgs()
                        save_queue_state()
        except Exception as e:
            logger.critical(f"Воркер упал: {e}", exc_info=True)
            await asyncio.sleep(10)

# --- ФОНОВАЯ ОЧИСТКА ПАМЯТИ ---
async def memory_cleaner():
    while True:
        await asyncio.sleep(300)  # каждые 5 минут
        mem = psutil.virtual_memory()
        if mem.percent > 50:
            gc.collect()
            logger.info(f"Принудительная очистка памяти (использование: {mem.percent}%)")

# --- ПЕРИОДИЧЕСКАЯ ПРОВЕРКА ТОКЕНОВ ---
async def check_all_tokens(app):
    now = time.time()
    changed = False
    for uid, data in list(user_tokens.items()):
        if now - data['timestamp'] > TOKEN_LIFETIME:
            user_tokens.pop(uid, None)
            changed = True
    if changed:
        save_user_tokens()

# --- ЗАПУСК ---
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
    try:
        cleanup_old_tmp_dirs()
        if not os.path.exists(STATS_FILE):
            with open(STATS_FILE, "w") as f:
                f.write("0")
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
        app.add_handler(CallbackQueryHandler(restart_stuck_task_callback, pattern="restart_stuck_task"))
        app.add_handler(CallbackQueryHandler(cancel_download_callback, pattern="cancel_download"))
        conv = ConversationHandler(
            entry_points=[CommandHandler('start', start), MessageHandler(filters.Regex('^🎵 Начать работу$'), handle_download)],
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
        app.run_polling()
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
    finally:
        for task_obj in [token_checker_task, worker_task, memory_cleaner_task]:
            if task_obj:
                task_obj.cancel()

if __name__ == "__main__":
    main()
