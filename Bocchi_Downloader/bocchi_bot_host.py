# (c) 2026 Hanako
# Проект "Bocchi Downloader" (Server Edition)

import asyncio
import logging
import os
import re
import shutil
import time
import urllib.parse
import uuid
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests
import psutil
from dotenv import load_dotenv
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, USLT, TDRC, TCON, TALB, TPE2
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters
)
from yandex_music import Client

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %name)s - %(message)s')
logger = logging.getLogger("BocchiStation")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТОКЕН")
DOWNLOADER_PATH = os.getenv("DOWNLOADER_PATH", "yandex-music-downloader")
STATS_FILE = os.getenv("STATS_FILE", "stats.txt")
MAX_LINKS = int(os.getenv("MAX_LINKS", "5"))
DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", "600"))
TOKEN_LIFETIME = int(os.getenv("TOKEN_LIFETIME", "86400"))
DEFAULT_QUALITY = int(os.getenv("DEFAULT_QUALITY", "2"))
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "1"))

BOT_START_TIME = time.time()

# Глобальные объекты
download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
user_processing = {}          # user_id -> bool (занят ли пользователь)
user_locks = {}               # user_id -> Lock для последовательности запросов от одного пользователя
last_processed_msg = {}
last_auth_warning = {}
WARNING_COOLDOWN = 60

WAITING_FOR_TOKEN, WAITING_FOR_LINK = range(2)

QUALITY_NAMES = {0: "Низкое", 1: "Среднее", 2: "Высокое"}
QUALITY_NAMES_GENITIVE = {0: "низкого", 1: "среднего", 2: "высокого"}
QUALITY_BUTTONS = {"Низкое": 0, "Среднее": 1, "Высокое": 2}

quality_keyboard = [[KeyboardButton("Низкое"), KeyboardButton("Среднее"), KeyboardButton("Высокое")]]
quality_markup = ReplyKeyboardMarkup(quality_keyboard, resize_keyboard=True, one_time_keyboard=True)

main_menu_keyboard = [
    ["🎵 Начать загрузку", "❌ Удалить токен"],
    ["🔄 Обновить токен", "⚙️ Качество"]
]
main_markup = ReplyKeyboardMarkup(main_menu_keyboard, resize_keyboard=True)

# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================
def is_message_too_old(update: Update) -> bool:
    return update.message.date.timestamp() < BOT_START_TIME if update.message else False

def is_token_valid(context: ContextTypes.DEFAULT_TYPE) -> bool:
    token = context.user_data.get('yandex_token')
    if not token:
        return False
    token_time = context.user_data.get('token_time', 0)
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
                return {
                    'album': track.get('collectionName'),
                    'year': track.get('releaseDate', '')[:4],
                    'genre': track.get('primaryGenreName'),
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

def check_memory():
    try:
        mem = psutil.virtual_memory()
        return mem.available >= 150 * 1024 * 1024
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
    match = re.match(r'(https?://(?:[a-z0-9-]+\.)*yandex\.[a-z]{2,3})(?:/music)?', url, re.IGNORECASE)
    if match:
        base_domain = match.group(1)
        if '/music' in url or re.search(r'//music\.', url, re.IGNORECASE):
            return base_domain
        return f"{base_domain}/music"
    return "https://music.yandex.ru"

def parse_yandex_url(url: str):
    parsed = urlparse(url)
    path = parsed.path
    query = parse_qs(parsed.query)

    if re.search(r'/track/(\d+)', path):
        return ('track', re.search(r'/track/(\d+)', path).group(1), None)
    if '/album/' in path and '/track/' not in path:
        album_match = re.search(r'/album/(\d+)', path)
        if album_match:
            return ('album', album_match.group(1), None)
    playlist_match = re.search(r'/users/([^/]+)/playlists/(\d+)', path)
    if playlist_match:
        return ('playlist', playlist_match.group(2), playlist_match.group(1))
    playlist_match2 = re.search(r'/playlist/(\d+)', path)
    if playlist_match2:
        return ('playlist', playlist_match2.group(1), None)
    if 'handlers/playlist.jsx' in path:
        owner = query.get('owner', [None])[0]
        kinds = query.get('kinds', [None])[0]
        if owner and kinds:
            return ('playlist', kinds, owner)
    return (None, None, None)

async def send_animated_message(bot, chat_id, text, **kwargs):
    await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    await asyncio.sleep(0.3)
    return await bot.send_message(chat_id=chat_id, text=text, **kwargs)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_animated_message(
        context.bot, update.effective_chat.id,
        "🎸 Главное меню:",
        reply_markup=main_markup
    )

# ===================== АВТОРИЗАЦИЯ =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update):
        return WAITING_FOR_LINK
    user_id = update.effective_user.id
    if user_id not in user_locks:
        user_locks[user_id] = asyncio.Lock()
    async with user_locks[user_id]:
        if is_token_valid(context):
            await show_main_menu(update, context)
            return WAITING_FOR_LINK
        kb = [[KeyboardButton("🎵 Начать работу")]]
        welcome = "🌸 Привет! Это Bocchi Downloader 🎸\n\nЯ буду скачивать треки из Яндекс Музыки.\nЖми кнопку ниже для входа."
        await send_animated_message(
            context.bot, update.effective_chat.id,
            welcome,
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
        return WAITING_FOR_LINK

async def check_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update):
        return WAITING_FOR_LINK
    user_id = update.effective_user.id
    async with user_locks.setdefault(user_id, asyncio.Lock()):
        if is_token_valid(context):
            await show_main_menu(update, context)
            return WAITING_FOR_LINK
        auth_text = (
            "🔑 Авторизация\n\n"
            "1️⃣ Перейди по [ссылке](https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41195d)\n"
            "2️⃣ Нажми «Войти» или «Разрешить».\n"
            "3️⃣ Скопируй весь адрес из строки браузера и отправь его мне."
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
    token = token_match.group(1) if token_match else None
    if not token:
        access_match = re.search(r"access_token=([^&]+)", raw_text)
        token = access_match.group(1) if access_match else None
    if not token:
        await send_animated_message(
            context.bot, update.effective_chat.id,
            "❌ Не удалось распознать токен. Попробуйте ещё раз."
        )
        return WAITING_FOR_TOKEN
    try:
        await update.message.delete()
    except:
        pass
    status_msg = await send_animated_message(
        context.bot, update.effective_chat.id,
        "🔍 Проверяю токен..."
    )
    try:
        client = Client(token).init()
        context.user_data['yandex_token'] = token
        context.user_data['token_time'] = time.time()
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

async def cmd_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update):
        return
    current = get_user_quality(context)
    await send_animated_message(
        context.bot, update.effective_chat.id,
        f"🎵 Текущее качество: *{QUALITY_NAMES[current]}*\n\nВыберите новое:",
        parse_mode='Markdown',
        reply_markup=quality_markup
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_animated_message(
        context.bot, update.effective_chat.id,
        "❌ Действие отменено."
    )
    return ConversationHandler.END

# ===================== ЗАГРУЗКА И ОТПРАВКА ОДНОГО ТРЕКА =====================
async def download_and_send_one_track(task, context, status_msg):
    tmp_dir = Path(f"bocchi_tmp_{uuid.uuid4().hex}")
    current_quality = task['quality']
    actual_quality_used = None
    success = False

    try:
        tmp_dir.mkdir(parents=True, exist_ok=True)
        await status_msg.edit_text(
            f"🌀 Скачивание...\n{task['track_name']}\nКачество: {QUALITY_NAMES[current_quality]}"
        )

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

        quality_to_try = current_quality
        for attempt in range(3):
            returncode, stdout, stderr = await run_downloader(quality_to_try)
            if returncode == 0:
                success = True
                actual_quality_used = quality_to_try
                break
            stderr_text = stderr.decode('utf-8', errors='replace')
            logger.warning(f"Код {returncode}, stderr: {stderr_text[:200]}")
            if any(k in stderr_text.lower() for k in ['forbidden', 'blocked', 'denied', 'регион']):
                await status_msg.edit_text(f"❌ Трек заблокирован Яндексом: {task['track_name']}")
                return False
            if returncode == -9 and quality_to_try > 0:
                quality_to_try -= 1
                await status_msg.edit_text(
                    f"⚠️ Не хватило памяти, понижаю качество до {QUALITY_NAMES_GENITIVE[quality_to_try]}..."
                )
                continue
            if attempt == 2:
                await status_msg.edit_text(f"❌ Ошибка скачивания: {stderr_text[:150]}")
                return False
            await asyncio.sleep(3)

        if not success:
            return False

        if actual_quality_used != current_quality:
            await status_msg.edit_text(
                f"🎵 {task['track_name']} скачан в качестве {QUALITY_NAMES[actual_quality_used]}.\n🔄 Подготавливаю отправку..."
            )

        files = list(tmp_dir.glob("*.mp3")) + list(tmp_dir.glob("*.m4a"))
        if not files:
            await status_msg.edit_text("❌ Файл не найден после скачивания.")
            return False
        f_path = files[0]

        artist = task.get('artist')
        title = task.get('title')
        duration = task.get('duration', 0)
        if not artist or not title:
            try:
                if f_path.suffix == '.m4a':
                    audio = MP4(f_path)
                    artist = audio.get('\xa9ART', ['Неизвестен'])[0]
                    title = audio.get('\xa9nam', [f_path.stem])[0]
                    duration = int(audio.info.length)
                else:
                    audio = EasyID3(f_path)
                    artist = audio.get('artist', ['Неизвестен'])[0]
                    title = audio.get('title', [f_path.stem])[0]
                    duration = int(MP3(f_path).info.length)
            except:
                artist = task.get('artist', 'Неизвестен')
                title = task.get('title', f_path.stem)

        display_name = f"{artist} — {title}"
        safe_filename = re.sub(r'[\\/*?:"<>|]', "", f"{artist} - {title}{f_path.suffix}")

        lyrics = None
        lrc_files = list(tmp_dir.glob(f"{f_path.stem}.lrc"))
        if lrc_files:
            try:
                with open(lrc_files[0], 'r', encoding='utf-8') as lf:
                    lyrics = lf.read().strip()
            except:
                pass

        itunes_data = await asyncio.to_thread(fetch_metadata_from_itunes, artist, title)

        try:
            if f_path.suffix == '.m4a':
                audio = MP4(f_path)
                audio['aART'] = [artist]
                if itunes_data.get('album'): audio['\xa9alb'] = [itunes_data['album']]
                if itunes_data.get('year'): audio['\xa9day'] = [str(itunes_data['year'])]
                if itunes_data.get('genre'): audio['\xa9gen'] = [itunes_data['genre']]
                if lyrics: audio['\xa9lyr'] = [lyrics]
                audio.save()
            else:
                audio = MP3(f_path, ID3=ID3)
                if audio.tags is None:
                    audio.add_tags()
                audio.tags.add(TPE2(encoding=3, text=artist))
                if itunes_data.get('album'): audio.tags.add(TALB(encoding=3, text=itunes_data['album']))
                if itunes_data.get('year'): audio.tags.add(TDRC(encoding=3, text=str(itunes_data['year'])))
                if itunes_data.get('genre'): audio.tags.add(TCON(encoding=3, text=itunes_data['genre']))
                if lyrics:
                    audio.tags.add(USLT(encoding=3, lang='rus', desc='Lyrics', text=lyrics))
                audio.save()
        except Exception as tag_e:
            logger.error(f"Ошибка тегов: {tag_e}")

        new_path = f_path.with_name(safe_filename)
        try:
            f_path.rename(new_path)
            f_path = new_path
        except:
            shutil.move(str(f_path), str(new_path))
            f_path = new_path

        await status_msg.edit_text(f"📤 Отправляю {display_name}...")
        with open(f_path, 'rb') as af:
            await context.bot.send_audio(
                chat_id=task['chat_id'],
                audio=af,
                performer=artist,
                title=title,
                duration=duration if duration > 0 else None,
                filename=safe_filename,
                read_timeout=120, write_timeout=120
            )
        add_stats(f_path.stat().st_size)
        await status_msg.delete()
        return True

    except Exception as e:
        logger.exception(f"Ошибка в download_and_send_one_track: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        return False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

# ===================== ОСНОВНАЯ ОБРАБОТКА ССЫЛОК =====================
async def process_links(update: Update, context: ContextTypes.DEFAULT_TYPE, urls: list):
    """Обрабатывает список ссылок, загружает треки последовательно с семафором."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    token = context.user_data['yandex_token']

    # Сначала парсим все ссылки, собираем задания
    try:
        client = Client(token).init()
    except Exception as e:
        await send_animated_message(context.bot, chat_id, f"❌ Ошибка авторизации: {e}")
        return

    all_tasks = []
    for url in urls:
        base_url = extract_base_url(url)
        content_type, content_id, username = parse_yandex_url(url)
        if not content_type:
            await send_animated_message(context.bot, chat_id, f"❌ Не удалось распознать: {url}")
            continue
        try:
            if content_type == 'track':
                track = await asyncio.to_thread(client.tracks, [content_id])
                if track and track[0]:
                    t = track[0]
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
            elif content_type == 'album':
                album = await asyncio.to_thread(client.albums, [content_id])
                if album and album[0] and album[0].volumes:
                    for volume in album[0].volumes:
                        for track in volume:
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
                    await send_animated_message(context.bot, chat_id, f"❌ Альбом пуст: {url}")
            elif content_type == 'playlist':
                if username:
                    playlist = await asyncio.to_thread(client.users_playlists, content_id, username)
                else:
                    playlist = await asyncio.to_thread(client.playlist, content_id)
                if isinstance(playlist, list) and playlist:
                    playlist = playlist[0]
                if playlist and playlist.tracks:
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
                    await send_animated_message(context.bot, chat_id, f"❌ Плейлист пуст: {url}")
        except Exception as e:
            await send_animated_message(context.bot, chat_id, f"❌ Ошибка парсинга {url}: {e}")

    if not all_tasks:
        await send_animated_message(context.bot, chat_id, "❌ Не найдено треков для скачивания.")
        return

    total = len(all_tasks)
    await send_animated_message(context.bot, chat_id, f"📥 Найдено {get_plural_tracks(total)}. Начинаю загрузку...")

    # Проверяем семафор: если занят, предупреждаем и не начинаем
    if download_semaphore.locked():
        await send_animated_message(
            context.bot, chat_id,
            "⚠️ Загрузчик сейчас занят другим пользователем. Пожалуйста, попробуйте через минуту."
        )
        return

    # Захватываем семафор на всё время обработки всех треков пользователя
    async with download_semaphore:
        for idx, task in enumerate(all_tasks, 1):
            status_msg = await send_animated_message(
                context.bot, chat_id,
                f"🔄 Обработка {idx}/{total}: {task['track_name']}"
            )
            success = await download_and_send_one_track(task, context, status_msg)
            if not success:
                # если трек не скачался, продолжаем со следующим
                continue
            if idx < total:
                await asyncio.sleep(1)  # небольшая пауза между треками

    await send_animated_message(
        context.bot, chat_id,
        "✅ Все треки обработаны! Возвращаюсь в главное меню.",
        reply_markup=main_markup
    )

# ===================== ХЕНДЛЕР СООБЩЕНИЙ =====================
async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update):
        return WAITING_FOR_LINK

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = update.message.text

    # Обработка кнопок меню
    if text == "🎵 Начать работу":
        return await check_session(update, context)
    if text == "🎵 Начать загрузку":
        await send_animated_message(
            context.bot, chat_id,
            "🎵 Отправьте ссылки на треки, альбомы или плейлисты."
        )
        return WAITING_FOR_LINK
    if text == "❌ Удалить токен":
        await cmd_logout(update, context)
        return WAITING_FOR_LINK
    if text == "🔄 Обновить токен":
        await send_animated_message(
            context.bot, chat_id,
            "🔑 Пожалуйста, отправьте новый токен."
        )
        return WAITING_FOR_TOKEN
    if text == "⚙️ Качество":
        await cmd_quality(update, context)
        return WAITING_FOR_LINK
    if text in QUALITY_BUTTONS:
        new_q = QUALITY_BUTTONS[text]
        if set_user_quality(context, new_q):
            await send_animated_message(
                context.bot, chat_id,
                f"✅ Качество изменено на *{QUALITY_NAMES[new_q]}*.",
                parse_mode='Markdown',
                reply_markup=main_markup
            )
        else:
            await send_animated_message(context.bot, chat_id, "❌ Ошибка смены качества.")
        return WAITING_FOR_LINK

    # Проверка токена
    if not is_token_valid(context):
        await send_animated_message(
            context.bot, chat_id,
            "🔑 Токен не активен. Используйте /start или кнопку «Начать работу»."
        )
        return WAITING_FOR_TOKEN

    # Извлечение ссылок
    content = (update.message.text or "") + " " + (update.message.caption or "")
    urls = re.findall(r'(https?://(?:[a-z0-9-]+\.)*yandex\.[a-z]{2,3}(?:/music)?/(?:track|album|playlist|handlers/playlist\.jsx)[^\s]*)', content)
    if not urls:
        await send_animated_message(
            context.bot, chat_id,
            "❌ Не найдена ссылка на Яндекс.Музыку."
        )
        return WAITING_FOR_LINK

    # Ограничиваем количество ссылок
    urls = urls[:MAX_LINKS]

    # Блокировка на пользователя (чтобы его следующие запросы не запускались, пока текущий не закончен)
    if user_id in user_processing and user_processing[user_id]:
        await send_animated_message(
            context.bot, chat_id,
            "⚠️ Вы уже отправили запрос, подождите, пока обработается текущий."
        )
        return WAITING_FOR_LINK

    user_processing[user_id] = True
    try:
        await process_links(update, context, urls)
    finally:
        user_processing.pop(user_id, None)

    return WAITING_FOR_LINK

# ===================== ЗАПУСК =====================
def main():
    cleanup_old_tmp_dirs()
    if not os.path.exists(STATS_FILE):
        with open(STATS_FILE, "w") as f:
            f.write("0")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start), MessageHandler(filters.Regex('^🎵 Начать работу$'), handle_download)],
        states={
            WAITING_FOR_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_token)],
            WAITING_FOR_LINK: [MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_download)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    app.add_handler(CommandHandler('logout', cmd_logout))
    app.add_handler(CommandHandler('quality', cmd_quality))
    app.add_handler(conv)
    logger.info("Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
