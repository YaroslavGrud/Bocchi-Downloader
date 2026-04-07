# (c) 2026 Hanako
# Проект "Bocchi Downloader" (Server Edition)
# ИСПРАВЛЕННАЯ ВЕРСИЯ:
# - Обработка альбомов с несколькими томами (volumes)
# - Универсальный парсинг ссылок (track/album/playlist, включая handlers/playlist.jsx)
# - Корректное извлечение базового URL с сохранением регионального домена
# - Защита от потери ссылок из-за параметров
# - Падение качества при нехватке памяти
# - Отправка аудио с fallback на документ

import asyncio
import logging
import os
import random
import re
import shutil
import time
import urllib.parse
import uuid
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests
import psutil
from catboxpy import AsyncCatboxClient, LitterboxClient
from dotenv import load_dotenv
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, USLT, TDRC, TCON, TALB, APIC, TPE2
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from mutagen import File
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
)
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters
)
from yandex_music import Client

load_dotenv()

# --- НАСТРОЙКА ЛОГИРОВАНИЯ ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(message)s')
logger = logging.getLogger("BocchiStation")

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТОКЕН_ЗДЕСЬ")
DOWNLOADER_PATH = os.getenv("DOWNLOADER_PATH", "yandex-music-downloader")
STATS_FILE = os.getenv("STATS_FILE", "../stats.txt")
MAX_LINKS = int(os.getenv("MAX_LINKS", "10"))
DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", "600"))
TOKEN_LIFETIME = int(os.getenv("TOKEN_LIFETIME", "86400"))
CLOUD_TIMEOUT = int(os.getenv("CLOUD_TIMEOUT", "120"))
DEFAULT_QUALITY = int(os.getenv("DEFAULT_QUALITY", "2"))

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

# --- ДЕДУПЛИКАЦИЯ И БЛОКИРОВКИ ---
last_processed_msg = {}
user_locks = {}

WAITING_FOR_TOKEN, WAITING_FOR_LINK = range(2)

# --- КАЧЕСТВО (текстовые кнопки) ---
QUALITY_NAMES = {
    0: "Низкое",
    1: "Среднее",
    2: "Высокое"
}
QUALITY_NAMES_GENITIVE = {
    0: "низкого",
    1: "среднего",
    2: "высокого"
}
QUALITY_BUTTONS = {
    "Низкое": 0,
    "Среднее": 1,
    "Высокое": 2
}

quality_keyboard = [
    [KeyboardButton("Низкое"), KeyboardButton("Среднее"), KeyboardButton("Высокое")]
]
quality_markup = ReplyKeyboardMarkup(quality_keyboard, resize_keyboard=True, one_time_keyboard=True)

# --- ГЛАВНОЕ МЕНЮ ---
main_menu_keyboard = [
    ["🎵 Начать загрузку", "❌ Удалить токен"],
    ["🔄 Обновить токен", "⚙️ Качество"]
]
main_markup = ReplyKeyboardMarkup(main_menu_keyboard, resize_keyboard=True)

# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================

def is_message_too_old(update: Update) -> bool:
    if update.message:
        return update.message.date.timestamp() < BOT_START_TIME
    return False

def is_token_valid(context: ContextTypes.DEFAULT_TYPE) -> bool:
    if 'yandex_token' not in context.user_data:
        return False
    token_time = context.user_data.get('token_time')
    if token_time is None:
        context.user_data['token_time'] = time.time()
        return True
    return (time.time() - token_time) <= TOKEN_LIFETIME

def get_plural_tracks(n):
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} трек"
    elif 2 <= n % 10 <= 4 and (n % 100 < 10 or n % 100 >= 20):
        return f"{n} трека"
    else:
        return f"{n} треков"

def fetch_metadata_from_itunes(artist, title):
    try:
        query = urllib.parse.quote(f"{artist} {title}")
        url = f"https://itunes.apple.com/search?term={query}&entity=song&limit=1"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data['resultCount'] > 0:
                track = data['results'][0]
                cover_url = track.get('artworkUrl100', '').replace('100x100bb.jpg', '1000x1000bb.jpg')
                cover_bytes = None
                if cover_url:
                    cover_resp = requests.get(cover_url, timeout=10)
                    if cover_resp.status_code == 200:
                        cover_bytes = cover_resp.content
                return {
                    'album': track.get('collectionName'),
                    'year': track.get('releaseDate', '')[:4],
                    'genre': track.get('primaryGenreName'),
                    'cover_bytes': cover_bytes
                }
    except Exception as e:
        logger.error(f"Ошибка iTunes: {e}")
    return {}

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

def check_memory():
    try:
        mem = psutil.virtual_memory()
        if mem.available < 150 * 1024 * 1024:
            logger.warning(f"Мало памяти: {mem.available / 1024 / 1024:.0f} МБ")
            return False
        return True
    except:
        return True

def get_user_quality(context: ContextTypes.DEFAULT_TYPE) -> int:
    return context.user_data.get('quality', DEFAULT_QUALITY)

def set_user_quality(context: ContextTypes.DEFAULT_TYPE, quality: int):
    if quality in QUALITY_NAMES:
        context.user_data['quality'] = quality
        return True
    return False

def extract_base_url(url: str) -> str:
    """
    Извлекает базовый URL для Яндекс.Музыки, сохраняя оригинальный домен.
    Возвращает строку вида: https://music.yandex.ru  или https://yandex.ru/music
    """
    match = re.match(r'(https?://(?:[a-z0-9-]+\.)*yandex\.[a-z]{2,3})(?:/music)?', url, re.IGNORECASE)
    if match:
        base_domain = match.group(1)
        if '/music' in url or re.search(r'//music\.', url, re.IGNORECASE):
            return base_domain
        return f"{base_domain}/music"
    logger.warning(f"Не удалось извлечь домен из URL: {url}, использую fallback")
    return "https://music.yandex.ru"

def parse_yandex_url(url: str):
    """
    Определяет тип контента и извлекает ID.
    Возвращает (type, id, username) где type: 'track', 'album', 'playlist'
    """
    parsed = urlparse(url)
    path = parsed.path
    query = parse_qs(parsed.query)

    # Трек
    track_match = re.search(r'/track/(\d+)', path)
    if track_match:
        return ('track', track_match.group(1), None)

    # Альбом (без track в пути)
    if '/album/' in path and '/track/' not in path:
        album_match = re.search(r'/album/(\d+)', path)
        if album_match:
            return ('album', album_match.group(1), None)

    # Плейлист: /users/username/playlists/123
    playlist_match = re.search(r'/users/([^/]+)/playlists/(\d+)', path)
    if playlist_match:
        return ('playlist', playlist_match.group(2), playlist_match.group(1))

    # Плейлист: /playlist/123
    playlist_match2 = re.search(r'/playlist/(\d+)', path)
    if playlist_match2:
        return ('playlist', playlist_match2.group(1), None)

    # Плейлист: handlers/playlist.jsx?owner=xxx&kinds=yyy
    if 'handlers/playlist.jsx' in path:
        owner = query.get('owner', [None])[0]
        kinds = query.get('kinds', [None])[0]
        if owner and kinds:
            return ('playlist', kinds, owner)

    return (None, None, None)

def extract_cover_from_audio(file_path: Path) -> bytes:
    """Извлекает обложку, но если она больше 200KB, возвращает None."""
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
        if cover_data and len(cover_data) > 200 * 1024:
            logger.warning(f"Обложка слишком большая ({len(cover_data)} байт), пропускаем.")
            return None
        return cover_data
    except Exception as e:
        logger.warning(f"Не удалось извлечь обложку: {e}")
        return None

# --- АНИМИРОВАННАЯ ОТПРАВКА ---
async def send_animated_message(bot, chat_id, text, delay=0.4, max_retries=3, **kwargs):
    draft_id = int(time.time() * 1000) + random.randint(1, 10000)
    for attempt in range(max_retries):
        try:
            await bot.send_message_draft(chat_id=chat_id, draft_id=draft_id, text=text)
            await asyncio.sleep(delay)
            msg = await bot.send_message(chat_id=chat_id, text=text, **kwargs)
            try:
                await bot.delete_draft(chat_id=chat_id, draft_id=draft_id)
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

# --- КОМАНДА /quality ---
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

# --- ХЕНДЛЕРЫ АВТОРИЗАЦИИ ---
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
        if is_token_valid(context):
            await show_main_menu(update, context)
            return WAITING_FOR_LINK

        last_welcome = context.user_data.get('last_welcome_time', 0)
        if time.time() - last_welcome < 5:
            logger.info(f"Игнорируем частый /start от {user_id}")
            return WAITING_FOR_LINK
        context.user_data['last_welcome_time'] = time.time()

        last_auth_warning.pop(user_id, None)
        kb = [[KeyboardButton("🎵 Начать работу")]]
        welcome = (
            "🌸 Привет! Это Bocchi Downloader 🎸\n\n"
            "Теперь я живу на специальном хостинг сервере и "
            "буду помогать тебе скачать любимые треки из Яндекс Музыки.\n\n"
            "✨ Как мы будем работать:\n"
            f"• Можешь присылать до {MAX_LINKS} ссылок за один раз.\n"
            "• Я буду скачивать всё аккуратно и строго по очереди.\n\n"
            "Жми кнопку ниже, чтобы войти в аккаунт и начать!"
        )
        await send_animated_message(
            context.bot, chat_id,
            welcome,
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
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
            await show_main_menu(update, context)
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
            "3️⃣ После входа страница может стать первоначальной или полностью пустой — не пугайся, так и должно быть!\n"
            "4️⃣ Скопируй весь адрес из строки браузера и отправь его мне."
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
            "❌ Не удалось распознать токен. Попробуйте ещё раз."
        )
        return WAITING_FOR_TOKEN
    try:
        await update.message.delete()
    except:
        pass
    status_msg = await update.message.reply_text("🔍 Проверяю токен...")
    try:
        client = await asyncio.to_thread(Client(token).init)
        context.user_data['yandex_token'] = token
        context.user_data['token_time'] = time.time()
        last_auth_warning.pop(user_id, None)
        login = client.account_status().account.login
        await status_msg.edit_text(f"✅ Ура! Я узнала тебя, {login}! Теперь всё готово.")
        await show_main_menu(update, context)
        return WAITING_FOR_LINK
    except Exception as e:
        logger.error(f"Ошибка токена: {e}")
        await status_msg.edit_text("❌ Токен не подходит. Попробуйте ещё раз.")
        return WAITING_FOR_TOKEN

async def cmd_logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update):
        return
    context.user_data.pop('yandex_token', None)
    context.user_data.pop('token_time', None)
    await send_animated_message(
        context.bot, update.effective_chat.id,
        "🔓 Токен удалён. Вы вышли из аккаунта."
    )
    kb = [[KeyboardButton("🎵 Начать работу")]]
    await send_animated_message(
        context.bot, update.effective_chat.id,
        "Для продолжения авторизуйтесь заново.",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_animated_message(
        context.bot, update.effective_chat.id,
        "❌ Действие отменено. Используйте /start для начала."
    )
    return ConversationHandler.END

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(update, context)

# --- ОБРАБОТЧИК ССЫЛОК И КНОПОК ---
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
    if text == "🎵 Начать загрузку":
        await send_animated_message(
            context.bot, update.effective_chat.id,
            "🎵 Отправьте ссылки на треки, альбомы или плейлисты."
        )
        return WAITING_FOR_LINK
    if text == "❌ Удалить токен":
        await cmd_logout(update, context)
        return WAITING_FOR_LINK
    if text == "🔄 Обновить токен":
        await send_animated_message(
            context.bot, update.effective_chat.id,
            "🔑 Пожалуйста, отправьте новый токен."
        )
        return WAITING_FOR_TOKEN
    if text == "⚙️ Качество":
        await cmd_quality(update, context)
        return WAITING_FOR_LINK

    if text in QUALITY_BUTTONS:
        new_q = QUALITY_BUTTONS[text]
        if set_user_quality(context, new_q):
            await update.message.reply_text(
                f"✅ Качество изменено на *{QUALITY_NAMES[new_q]}*.\n\n"
                f"💡 *Важно:* Высокое качество требует больше ресурсов сервера.\n"
                f"Если заметите зависания, попробуйте понизить качество.",
                parse_mode='Markdown',
                reply_markup=main_markup
            )
        else:
            await update.message.reply_text("❌ Ошибка при смене качества.")
        return WAITING_FOR_LINK

    chat_id = update.effective_chat.id
    message = update.message

    if not is_token_valid(context):
        try:
            await message.delete()
        except:
            pass
        now = time.time()
        last = last_auth_warning.get(user_id, 0)
        if now - last > WARNING_COOLDOWN:
            last_auth_warning[user_id] = now
            await context.bot.send_message(
                chat_id=chat_id,
                text="🔑 Токен не активен. Используйте /start или кнопку «Начать работу»."
            )
        return WAITING_FOR_TOKEN

    content = (update.message.text or "") + " " + (update.message.caption or "")
    urls = re.findall(r'(https?://(?:[a-z0-9-]+\.)*yandex\.[a-z]{2,3}(?:/music)?/(?:track|album|playlist|handlers/playlist\.jsx)[^\s]*)', content)
    if not urls:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Не удалось распознать ссылку. Убедитесь, что вы отправляете ссылку на трек, альбом или плейлист Яндекс.Музыки."
        )
        return WAITING_FOR_LINK

    if user_id in user_delay_tasks:
        user_delay_tasks[user_id].cancel()
    if user_id not in link_accumulators:
        link_accumulators[user_id] = []
    link_accumulators[user_id].extend(urls)

    if user_processing.get(user_id):
        try:
            await message.delete()
        except:
            pass
        return WAITING_FOR_LINK

    async def safe_process():
        try:
            await process_accumulated_links(user_id, chat_id, context, context.user_data['yandex_token'])
        except Exception as e:
            logger.error(f"Ошибка обработки: {e}", exc_info=True)
            try:
                await context.bot.send_message(chat_id, f"❌ Внутренняя ошибка: {str(e)[:200]}")
            except:
                pass
        finally:
            user_processing.pop(user_id, None)

    task = asyncio.create_task(safe_process())
    user_delay_tasks[user_id] = task
    try:
        await message.delete()
    except:
        pass
    return WAITING_FOR_LINK

# --- ПРОЦЕССОР ССЫЛОК (с исправлениями) ---
async def process_accumulated_links(user_id, chat_id, context, token):
    user_processing[user_id] = True
    user_delay_tasks.pop(user_id, None)
    await asyncio.sleep(0.5)

    if user_id not in link_accumulators or not link_accumulators[user_id]:
        user_processing.pop(user_id, None)
        return

    raw_links = list(dict.fromkeys(link_accumulators.pop(user_id)))[:MAX_LINKS]
    if not raw_links:
        return

    logger.info(f"Ссылки от {user_id}: {raw_links}")

    try:
        client = await asyncio.to_thread(Client(token).init)
    except Exception as e:
        logger.error(f"Ошибка клиента: {e}")
        await context.bot.send_message(chat_id, "❌ Ошибка авторизации. Попробуйте снова.")
        return

    all_tasks = []
    for url in raw_links:
        base_url = extract_base_url(url)
        content_type, content_id, username = parse_yandex_url(url)

        if not content_type:
            await context.bot.send_message(chat_id, f"❌ Не удалось распознать ссылку: {url}")
            continue

        try:
            if content_type == 'track':
                tracks_info = await asyncio.to_thread(client.tracks, [content_id])
                if tracks_info and len(tracks_info) > 0:
                    t = tracks_info[0]
                    artist = t.artists[0].name if t.artists else "Неизвестен"
                    title = t.title
                    duration = t.duration_ms // 1000 if t.duration_ms else 0
                    all_tasks.append({
                        'chat_id': chat_id,
                        'url': url,
                        'token': token,
                        'artist': artist,
                        'title': title,
                        'duration': duration,
                        'track_name': f"{artist} — {title}",
                        'quality': get_user_quality(context)
                    })
                else:
                    await context.bot.send_message(chat_id, f"❌ Трек не найден: {url}")

            elif content_type == 'album':
                albums_data = await asyncio.to_thread(client.albums, [content_id])
                if not albums_data or len(albums_data) == 0:
                    await context.bot.send_message(chat_id, f"❌ Альбом не найден: {url}")
                    continue
                album = albums_data[0]
                tracks_found = False
                if album and hasattr(album, 'volumes') and album.volumes:
                    for volume in album.volumes:
                        if not volume:
                            continue
                        for track in volume:
                            tracks_found = True
                            artist = track.artists[0].name if track.artists else "Неизвестен"
                            title = track.title
                            duration = track.duration_ms // 1000 if track.duration_ms else 0
                            track_url = f"{base_url}/track/{track.id}"
                            all_tasks.append({
                                'chat_id': chat_id,
                                'url': track_url,
                                'token': token,
                                'artist': artist,
                                'title': title,
                                'duration': duration,
                                'track_name': f"{artist} — {title}",
                                'quality': get_user_quality(context)
                            })
                if not tracks_found:
                    await context.bot.send_message(chat_id, f"❌ Альбом пуст или не содержит треков: {url}")

            elif content_type == 'playlist':
                if username:
                    playlist_data = await asyncio.to_thread(client.users_playlists, content_id, username)
                else:
                    playlist_data = await asyncio.to_thread(client.playlist, content_id)
                if isinstance(playlist_data, list) and len(playlist_data) > 0:
                    playlist = playlist_data[0]
                else:
                    playlist = playlist_data
                if playlist and hasattr(playlist, 'tracks') and playlist.tracks:
                    for track_data in playlist.tracks:
                        track = track_data.track
                        if track:
                            artist = track.artists[0].name if track.artists else "Неизвестен"
                            title = track.title
                            duration = track.duration_ms // 1000 if track.duration_ms else 0
                            track_url = f"{base_url}/track/{track.id}"
                            all_tasks.append({
                                'chat_id': chat_id,
                                'url': track_url,
                                'token': token,
                                'artist': artist,
                                'title': title,
                                'duration': duration,
                                'track_name': f"{artist} — {title}",
                                'quality': get_user_quality(context)
                            })
                else:
                    await context.bot.send_message(chat_id, f"❌ Плейлист не найден или пуст: {url}")

        except Exception as e:
            logger.error(f"Ошибка парсинга {url}: {e}")
            await context.bot.send_message(chat_id, f"❌ Ошибка при обработке ссылки {url}: {str(e)[:100]}")

    if not all_tasks:
        await context.bot.send_message(chat_id, "❌ Не удалось найти треки по ссылкам.")
        return

    total = len(all_tasks)
    queue_pos = download_queue.qsize() + 1
    msg = f"📥 Приняла запрос на {get_plural_tracks(total)}. Ваша очередь: {queue_pos}"
    if worker_busy:
        msg += "\n🎸 Сейчас немного занята, но скоро начну."
    await context.bot.send_message(chat_id, msg)

    for idx, task in enumerate(all_tasks):
        task['index'] = idx + 1
        task['total'] = total
        await download_queue.put(task)

    global active_tasks_count
    active_tasks_count += len(all_tasks)

# --- ВОРКЕР (с fallback отправки) ---
async def worker_loop(app):
    global worker_busy, active_tasks_count
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

                async with download_semaphore:
                    status_msg = None
                    try:
                        if not check_memory():
                            await app.bot.send_message(
                                chat_id=task['chat_id'],
                                text="⚠️ На сервере заканчивается память. Попробуйте позже."
                            )
                            continue

                        tmp_dir.mkdir(parents=True, exist_ok=True)
                        status_msg = await app.bot.send_message(
                            chat_id=task['chat_id'],
                            text=f"🌀 Обработка...\n{task['track_name']}\nКачество: {QUALITY_NAMES[current_quality]}"
                        )
                        await app.bot.send_chat_action(chat_id=task['chat_id'], action=ChatAction.TYPING)

                        async def run_downloader(quality):
                            cmd = [
                                DOWNLOADER_PATH, "--token", task['token'], "--quality", str(quality),
                                "--embed-cover", "--cover-resolution", "original",
                                "--dir", str(tmp_dir), "--url", task['url'],
                                "--path-pattern", "#artist - #title", "--lyrics-format", "lrc"
                            ]
                            proc = await asyncio.create_subprocess_exec(
                                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                            )
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
                            returncode, stdout, stderr = await run_downloader(quality_to_try)
                            if returncode == 0:
                                success = True
                                actual_quality_used = quality_to_try
                                break

                            stderr_text = stderr.decode('utf-8', errors='replace')
                            logger.warning(f"Код {returncode}, stderr: {stderr_text[:200]}")

                            if any(k in stderr_text.lower() for k in ['forbidden', 'blocked', 'denied', 'регион', 'недоступен', 'restricted', '403', 'доступ запрещён']):
                                await app.bot.send_message(
                                    chat_id=task['chat_id'],
                                    text=f"❌ Яндекс заблокировал трек **{task['track_name']}**.\nВозможно, он удалён или недоступен в вашем регионе.",
                                    parse_mode='Markdown'
                                )
                                break

                            if returncode == -9:
                                if quality_to_try > 0:
                                    new_q = quality_to_try - 1
                                    quality_gen = QUALITY_NAMES_GENITIVE[new_q]
                                    await app.bot.send_message(
                                        chat_id=task['chat_id'],
                                        text=f"⚠️ Серверу не хватило памяти для скачивания **{task['track_name']}**.\n"
                                             f"Автоматически понижаю качество до *{quality_gen}* и пробую снова.\n\n"
                                             f"Если хотите выбрать качество вручную, используйте кнопку «Качество» в меню.",
                                        parse_mode='Markdown'
                                    )
                                    quality_to_try = new_q
                                    attempt += 1
                                    continue
                                else:
                                    await app.bot.send_message(
                                        chat_id=task['chat_id'],
                                        text=f"❌ Даже на низком качестве не хватает памяти для **{task['track_name']}**.\n"
                                             f"Попробуйте позже или скачайте трек в приложении.",
                                        parse_mode='Markdown'
                                    )
                                    break

                            if attempt == max_attempts - 1:
                                error_msg = stderr_text[:150] if stderr_text else f"Код ошибки {returncode}"
                                await app.bot.send_message(
                                    chat_id=task['chat_id'],
                                    text=f"❌ Не удалось скачать **{task['track_name']}**.\nОшибка: {error_msg}",
                                    parse_mode='Markdown'
                                )
                            else:
                                await asyncio.sleep(5)
                            attempt += 1

                        if not success:
                            continue

                        if actual_quality_used != current_quality:
                            await app.bot.send_message(
                                chat_id=task['chat_id'],
                                text=f"🎵 Трек **{task['track_name']}** скачан в качестве *{QUALITY_NAMES[actual_quality_used]}*.",
                                parse_mode='Markdown'
                            )

                        # --- Обработка скачанных файлов ---
                        files = [f for f in tmp_dir.rglob('*') if f.suffix.lower() in ['.mp3', '.m4a']]
                        for f_path in files:
                            file_size_mb = f_path.stat().st_size / (1024 * 1024)

                            artist = task.get('artist')
                            title = task.get('title')
                            duration = task.get('duration', 0)

                            if not artist or not title:
                                try:
                                    if f_path.suffix == '.m4a':
                                        audio_read = MP4(f_path)
                                        artist = audio_read.get('\xa9ART', ['Неизвестен'])[0]
                                        title = audio_read.get('\xa9nam', [f_path.stem])[0]
                                        if not duration:
                                            duration = int(audio_read.info.length)
                                    else:
                                        audio_t, audio_i = EasyID3(f_path), MP3(f_path)
                                        artist = audio_t.get('artist', ['Неизвестен'])[0]
                                        title = audio_t.get('title', [f_path.stem])[0]
                                        if not duration:
                                            duration = int(audio_i.info.length)
                                except Exception as e:
                                    logger.warning(f"Ошибка чтения данных: {e}")
                                    artist = "Неизвестен"
                                    title = f_path.stem

                            if not task.get('artist'):
                                artist = artist.replace("#artist", "Неизвестен").strip()
                                title = title.replace("#artist", "").replace("#title", "").strip(" -")
                                if not artist:
                                    artist = "Неизвестен"
                                if not title:
                                    title = "Неизвестный трек"

                            display_name = f"{artist} — {title}"

                            # LRC-текст
                            lyrics = None
                            base_name = f_path.stem
                            lrc_files = list(tmp_dir.glob(f"{base_name}.lrc"))
                            if lrc_files:
                                lrc_file = lrc_files[0]
                                try:
                                    with open(lrc_file, 'r', encoding='utf-8') as f:
                                        lyrics = f.read().strip()
                                except Exception as e:
                                    logger.warning(f"Ошибка чтения LRC: {e}")

                            itunes_data = await asyncio.to_thread(fetch_metadata_from_itunes, artist, title)

                            # Запись дополнительных тегов
                            try:
                                if f_path.suffix.lower() == '.m4a':
                                    audio = MP4(f_path)
                                    audio['aART'] = [artist]
                                    audio.pop('\xa9cmt', None)
                                    if itunes_data.get('album'): audio['\xa9alb'] = [itunes_data['album']]
                                    if itunes_data.get('year'): audio['\xa9day'] = [str(itunes_data['year'])]
                                    if itunes_data.get('genre'): audio['\xa9gen'] = [itunes_data['genre']]
                                    if lyrics: audio['\xa9lyr'] = [lyrics]
                                    if itunes_data.get('cover_bytes'):
                                        audio['covr'] = [MP4Cover(itunes_data['cover_bytes'], imageformat=MP4Cover.FORMAT_JPEG)]
                                    audio.save()
                                else:
                                    audio = MP3(f_path, ID3=ID3)
                                    if audio.tags is None:
                                        audio.add_tags()
                                    audio.tags.add(TPE2(encoding=3, text=artist))
                                    audio.tags.delall('COMM')
                                    if itunes_data.get('album'): audio.tags.add(TALB(encoding=3, text=itunes_data['album']))
                                    if itunes_data.get('year'): audio.tags.add(TDRC(encoding=3, text=str(itunes_data['year'])))
                                    if itunes_data.get('genre'): audio.tags.add(TCON(encoding=3, text=itunes_data['genre']))
                                    if lyrics:
                                        audio.tags.add(USLT(encoding=3, lang='rus', desc='Lyrics', text=lyrics))
                                    if itunes_data.get('cover_bytes'):
                                        audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover',
                                                            data=itunes_data['cover_bytes']))
                                    audio.save()
                            except Exception as tag_e:
                                logger.error(f"Ошибка записи тегов: {tag_e}")

                            # Переименование
                            safe_filename = re.sub(r'[\\/*?:"<>|]', "", f"{artist} - {title}{f_path.suffix}")
                            new_f_path = f_path.with_name(safe_filename)
                            try:
                                f_path.rename(new_f_path)
                                f_path = new_f_path
                            except Exception:
                                try:
                                    shutil.move(str(f_path), str(new_f_path))
                                    f_path = new_f_path
                                except Exception as move_e:
                                    logger.error(f"Не удалось переименовать: {move_e}")
                                    await app.bot.send_message(chat_id=task['chat_id'],
                                                               text=f"❌ Не удалось переименовать {display_name}.")
                                    continue

                            if not f_path.exists():
                                await app.bot.send_message(chat_id=task['chat_id'],
                                                           text=f"❌ Не найден файл {display_name}.")
                                continue

                            cover_bytes = extract_cover_from_audio(f_path)

                            # --- ОТПРАВКА С FALLBACK ---
                            sent = False
                            last_error = None

                            # Попытка 1: отправить как аудио
                            try:
                                with open(f_path, 'rb') as f:
                                    await app.bot.send_audio(
                                        chat_id=task['chat_id'],
                                        audio=f,
                                        performer=artist,
                                        title=title,
                                        duration=duration if duration > 0 else None,
                                        filename=safe_filename,
                                        thumbnail=cover_bytes,
                                        read_timeout=600, write_timeout=600,
                                        connect_timeout=600, pool_timeout=600
                                    )
                                sent = True
                                logger.info(f"Отправлен трек как аудио: {display_name}")
                            except Exception as e:
                                last_error = e
                                logger.error(f"Ошибка send_audio: {e}, пробую отправить как документ")

                            # Попытка 2: отправить как документ (если аудио не удалось)
                            if not sent:
                                try:
                                    with open(f_path, 'rb') as f:
                                        await app.bot.send_document(
                                            chat_id=task['chat_id'],
                                            document=f,
                                            filename=safe_filename,
                                            caption=f"🎵 {display_name}\nНе удалось отправить как аудио, файл во вложении.",
                                            read_timeout=600, write_timeout=600,
                                            connect_timeout=600, pool_timeout=600
                                        )
                                    sent = True
                                    logger.info(f"Отправлен трек как документ: {display_name}")
                                except Exception as e2:
                                    last_error = e2
                                    logger.error(f"Ошибка send_document: {e2}")

                            if not sent:
                                await app.bot.send_message(
                                    chat_id=task['chat_id'],
                                    text=f"❌ Не удалось отправить {display_name} даже как документ.\nОшибка: {str(last_error)[:200]}"
                                )
                                continue

                            add_stats(f_path.stat().st_size)

                            # Финальное сообщение для пакета
                            if task.get('index') == task.get('total'):
                                try:
                                    await app.bot.send_message(
                                        chat_id=task['chat_id'],
                                        text='Загружено при поддержке #BocchiIsAlive <tg-emoji emoji-id="6041593232423391328">💠</tg-emoji>',
                                        parse_mode='HTML'
                                    )
                                    await app.bot.send_message(
                                        chat_id=task['chat_id'],
                                        text="🎸 Все треки обработаны. Выбери следующее действие:",
                                        reply_markup=main_markup
                                    )
                                except Exception as e:
                                    logger.error(f"Ошибка финального сообщения: {e}")

                    except Exception as e:
                        logger.error(f"Ошибка воркера: {e}", exc_info=True)
                        if status_msg:
                            try:
                                await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
                            except:
                                await app.bot.send_message(chat_id=task['chat_id'], text=f"❌ Ошибка: {str(e)[:200]}")
                    finally:
                        shutil.rmtree(tmp_dir, ignore_errors=True)
                        download_queue.task_done()
                        active_tasks_count -= 1
                        worker_busy = False
                        if status_msg:
                            try:
                                await status_msg.delete()
                            except:
                                pass
        except Exception as e:
            logger.critical(f"Воркер упал: {e}", exc_info=True)
            await asyncio.sleep(10)

# --- ПЕРИОДИЧЕСКАЯ ПРОВЕРКА ТОКЕНОВ ---
async def check_all_tokens(app):
    for chat_id, user_data in app.user_data.items():
        token_time = user_data.get('token_time')
        if token_time:
            time_left = TOKEN_LIFETIME - (time.time() - token_time)
            if 0 < time_left < 3600:
                try:
                    await app.bot.send_message(
                        chat_id,
                        f"⏰ Токен истечёт через {int(time_left//60)} минут. Обновите его через /start или кнопку «Обновить токен»."
                    )
                except Exception as e:
                    logger.error(f"Не удалось отправить напоминание: {e}")

# --- ЗАПУСК ---
async def post_init(app):
    global download_semaphore, download_queue, worker_task
    download_semaphore = asyncio.Semaphore(1)
    download_queue = asyncio.Queue()
    worker_task = asyncio.create_task(worker_loop(app))
    app.job_queue.run_repeating(lambda _: asyncio.create_task(check_all_tokens(app)), interval=900, first=10)

def main():
    try:
        cleanup_old_tmp_dirs()
        if not os.path.exists(STATS_FILE):
            with open(STATS_FILE, "w") as f:
                f.write("0")
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
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
        app.add_handler(conv)
        app.run_polling()
    except KeyboardInterrupt:
        logger.info("Бот остановлен")

if __name__ == "__main__":
    main()
