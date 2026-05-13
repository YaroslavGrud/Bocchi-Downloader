#!/usr/bin/env python3

# (c) 2026 Hanako
# Проект "Bocchi Downloader" (Android Edition)
# Копирование и использование без разрешения автора запрещено.

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

import requests
from catboxpy import AsyncCatboxClient, LitterboxClient
from dotenv import load_dotenv
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, USLT, TDRC, TCON, TALB, APIC, TPE2
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes,
    ConversationHandler, filters
)
from yandex_music import Client

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %name)s - %(message)s')
logger = logging.getLogger("BocchiStation")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не задан!")

DOWNLOADER_PATH = os.getenv("DOWNLOADER_PATH", "yandex-music-downloader")
STATS_FILE = os.getenv("STATS_FILE", "../stats.txt")
MAX_LINKS = int(os.getenv("MAX_LINKS", "10"))
DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", "600"))
TOKEN_LIFETIME = int(os.getenv("TOKEN_LIFETIME", "86400"))

BOT_START_TIME = time.time()

download_semaphore = None
download_queue = None
link_accumulators = {}
user_delay_tasks = {}
worker_busy = False
active_tasks_count = 0
last_auth_warning = {}
WARNING_COOLDOWN = 60

WAITING_FOR_TOKEN, WAITING_FOR_LINK = range(2)

# Клавиатура – без кнопки "Статус"
main_menu_keyboard = [
    ["🎵 Начать загрузку"],
    ["❌ Удалить токен", "🔄 Обновить токен"]
]

# ------------------------------------------------------------
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
        logger.error(f"iTunes error: {e}")
    return {}

def cleanup_old_tmp_dirs():
    count = 0
    for tmp_dir in Path('.').glob('bocchi_tmp_*'):
        if tmp_dir.is_dir():
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                count += 1
            except Exception as e:
                logger.error(f"Не удалось удалить {tmp_dir}: {e}")
    if count:
        print(f"🎸 Удалено временных папок: {count}")

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

# ------------------------------------------------------------
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
            logger.warning(f"Анимация не удалась ({attempt+1}): {e}")
            if attempt == max_retries - 1:
                return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
            await asyncio.sleep(0.5 * (attempt + 1))
    return await bot.send_message(chat_id=chat_id, text=text, **kwargs)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup = ReplyKeyboardMarkup(main_menu_keyboard, resize_keyboard=True)
    await send_animated_message(
        context.bot, update.effective_chat.id,
        "🎸 Главное меню:",
        reply_markup=reply_markup
    )

# ------------------------------------------------------------
# ВОРКЕР (скачивание)
async def worker(app):
    global worker_busy, active_tasks_count
    while True:
        task = await download_queue.get()
        worker_busy = True
        tmp_dir = Path(f"bocchi_tmp_{uuid.uuid4().hex}")

        async with download_semaphore:
            try:
                tmp_dir.mkdir(parents=True, exist_ok=True)
                status_msg = await app.bot.send_message(
                    chat_id=task['chat_id'],
                    text=f"🌀 Обработка...\n{task['track_name']}"
                )
                await app.bot.send_chat_action(chat_id=task['chat_id'], action=ChatAction.TYPING)

                cmd = [
                    DOWNLOADER_PATH, "--token", task['token'], "--quality", "2",
                    "--embed-cover", "--dir", str(tmp_dir), "--url", task['url'],
                    "--path-pattern", "#artist - #title",
                    "--lyrics-format", "lrc"
                ]

                max_retries = 3
                retry_delay = 5
                success = False
                for attempt in range(max_retries):
                    proc = await asyncio.create_subprocess_exec(
                        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                    )
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=DOWNLOAD_TIMEOUT)
                        success = True
                        break
                    except asyncio.TimeoutError:
                        proc.kill()
                        if attempt == max_retries - 1:
                            await app.bot.send_message(
                                chat_id=task['chat_id'],
                                text="Ой... Кажется, я слишком долго пытаюсь это скачать. Сервер молчит, поэтому я вынуждена прерваться, чтобы не заставлять других ждать в очереди 🎸"
                            )
                        else:
                            await asyncio.sleep(retry_delay)
                if not success:
                    continue

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
                                artist = audio_read.get('\xa9ART', ['Unknown'])[0]
                                title = audio_read.get('\xa9nam', [f_path.stem])[0]
                                if not duration:
                                    duration = int(audio_read.info.length)
                            else:
                                audio_t, audio_i = EasyID3(f_path), MP3(f_path)
                                artist = audio_t.get('artist', ['Unknown'])[0]
                                title = audio_t.get('title', [f_path.stem])[0]
                                if not duration:
                                    duration = int(audio_i.info.length)
                        except Exception as e:
                            logger.warning(f"Ошибка чтения метаданных: {e}")
                            artist = "Unknown"
                            title = f_path.stem

                    if not task.get('artist'):
                        artist = artist.replace("#artist", "Unknown").strip()
                        title = title.replace("#artist", "").replace("#title", "").strip(" -")
                        if not artist:
                            artist = "Unknown"
                        if not title:
                            title = "Unknown Track"

                    display_name = f"{artist} — {title}"

                    # LRC-текст
                    lyrics = None
                    lrc_files = list(tmp_dir.glob(f"{f_path.stem}.lrc"))
                    if lrc_files:
                        try:
                            with open(lrc_files[0], 'r', encoding='utf-8') as f:
                                lyrics = f.read().strip()
                        except Exception as e:
                            logger.warning(f"Ошибка чтения LRC: {e}")

                    itunes_data = await asyncio.to_thread(fetch_metadata_from_itunes, artist, title)

                    # Запись тегов
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
                        logger.error(f"Теги не записаны: {tag_e}")

                    # Переименование
                    safe_filename = re.sub(r'[\\/*?:"<>|]', "", f"{artist} - {title}{f_path.suffix}")
                    new_f_path = f_path.with_name(safe_filename)
                    try:
                        f_path.rename(new_f_path)
                        f_path = new_f_path
                    except:
                        shutil.move(str(f_path), str(new_f_path))
                        f_path = new_f_path

                    if not f_path.exists():
                        await app.bot.send_message(chat_id=task['chat_id'],
                                                   text=f"❌ Не найден файл {display_name}.")
                        continue

                    # Отправка
                    if file_size_mb > 49.0:
                        uploaded = False
                        await status_msg.edit_text(f"📦 Файл {display_name} весит {file_size_mb:.1f} МБ. Загружаю на временное облако...")
                        try:
                            litterbox = LitterboxClient()
                            url = await asyncio.to_thread(litterbox.upload_file, str(f_path), expire_time="24h")
                            if url and url.startswith(("https://", "http://")):
                                await app.bot.send_message(
                                    chat_id=task['chat_id'],
                                    text=f"🎁 Файл {display_name} слишком велик для Telegram.\nВот временная ссылка (действует 24 часа):\n\n🔗 {url}",
                                    disable_web_page_preview=True
                                )
                                uploaded = True
                        except Exception as e:
                            logger.error(f"Litterbox error: {e}")
                        if not uploaded:
                            try:
                                catbox = AsyncCatboxClient()
                                url = await catbox.upload(str(f_path))
                                if url:
                                    await app.bot.send_message(
                                        chat_id=task['chat_id'],
                                        text=f"🎁 Файл {display_name} слишком велик для Telegram.\nВот постоянная ссылка (файл не удалится):\n\n🔗 {url}",
                                        disable_web_page_preview=True
                                    )
                                    uploaded = True
                            except Exception as e:
                                logger.error(f"Catbox error: {e}")
                        if not uploaded:
                            await app.bot.send_message(chat_id=task['chat_id'],
                                                       text=f"❌ Не удалось загрузить {display_name}.")
                    else:
                        with open(f_path, 'rb') as f:
                            await app.bot.send_audio(
                                chat_id=task['chat_id'],
                                audio=f,
                                performer=artist,
                                title=title,
                                duration=duration if duration > 0 else None,
                                filename=safe_filename,
                                read_timeout=600, write_timeout=600,
                                connect_timeout=600, pool_timeout=600
                            )
                        logger.info(f"Отправлен: {display_name}")

                    add_stats(f_path.stat().st_size)

                    # Финальное сообщение для последнего трека в пачке
                    if task.get('index') == task.get('total'):
                        try:
                            await app.bot.send_message(
                                chat_id=task['chat_id'],
                                text='Загружено при поддержке #BocchiIsAlive <tg-emoji emoji-id="6041593232423391328">💠</tg-emoji>',
                                parse_mode='HTML'
                            )
                            reply_markup = ReplyKeyboardMarkup(main_menu_keyboard, resize_keyboard=True)
                            await app.bot.send_message(
                                chat_id=task['chat_id'],
                                text="🎸 Все треки обработаны. Выбери следующее действие:",
                                reply_markup=reply_markup
                            )
                        except Exception as e:
                            logger.error(f"Ошибка отправки финального сообщения или меню: {e}")
                try:
                    await status_msg.delete()
                except:
                    pass

            except Exception as e:
                logger.error(f"Worker Error: {e}")
                await app.bot.send_message(chat_id=task['chat_id'], text=f"❌ Ошибка: {str(e)[:200]}")
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                download_queue.task_done()
                active_tasks_count -= 1
                worker_busy = False

# ------------------------------------------------------------
# ХЕНДЛЕРЫ
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update):
        return WAITING_FOR_LINK
    last_auth_warning.pop(update.effective_user.id, None)
    kb = [[KeyboardButton("🎵 Начать работу")]]
    welcome_text = (
        "🌸 Привет! Это Bocchi Downloader 🎸\n\n"
        "Теперь я живу на Android и "
        "буду помогать тебе скачать любимые треки из Яндекс Музыки.\n\n"
        "✨ Как мы будем работать:\n"
        f"• Можешь присылать до {MAX_LINKS} ссылок за один раз.\n"
        "• Я буду скачивать всё аккуратно и строго по очереди.\n\n"
        "Жми кнопку ниже, чтобы войти в аккаунт и начать!"
    )
    await send_animated_message(
        context.bot, update.effective_chat.id,
        welcome_text,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )
    return WAITING_FOR_LINK

async def check_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update):
        return WAITING_FOR_LINK
    if is_token_valid(context):
        await show_main_menu(update, context)
        return WAITING_FOR_LINK
    auth_text = (
        "🔑 Авторизация\n\n"
        "Чтобы я могла найти твои треки в хорошем качестве, мне нужен доступ к Яндекс Музыке.\n\n"
        "1️⃣ Перейди по [этой ссылке](https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41195d)\n"
        "2️⃣ Нажми «Войти» или «Разрешить».\n"
        "3️⃣ После входа страница может стать первоначальной или полностью пустой — не пугайся, так и должно быть!\n"
        "4️⃣ Скопируй весь адрес из строки браузера (там будет длинный-длинный текст) и отправь его мне сюда 📋"
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
    raw_text = update.message.text.strip()
    token_match = re.search(r"(y0_[a-zA-Z0-9_-]+)", raw_text)
    if token_match:
        token = token_match.group(1)
    else:
        access_match = re.search(r"access_token=([^&]+)", raw_text)
        token = access_match.group(1) if access_match else None
    if token is None:
        if re.search(r'music\.yandex\.[a-z]{2,3}/', raw_text):
            await send_animated_message(
                context.bot, update.effective_chat.id,
                "🔑 Сначала необходимо авторизоваться. Пожалуйста, отправь токен, как описано выше.\n"
                "А после авторизации сможешь отправлять ссылки на музыку."
            )
        else:
            await send_animated_message(
                context.bot, update.effective_chat.id,
                "❌ Не удалось распознать токен. Убедись, что ты скопировал весь адрес из строки браузера после авторизации.\n"
                "Он должен содержать 'access_token=' или начинаться с 'y0_'."
            )
        return WAITING_FOR_TOKEN
    try:
        await update.message.delete()
    except:
        pass
    status_msg = await update.message.reply_text("🔍 Заглядываю в твой токен...")
    try:
        client = await asyncio.to_thread(Client(token).init)
        await asyncio.to_thread(client.account_status)
        context.user_data['yandex_token'] = token
        context.user_data['token_time'] = time.time()
        last_auth_warning.pop(update.effective_user.id, None)
        login = client.account_status().account.login
        await status_msg.edit_text(f"✅ Ура! Я узнала тебя, {login}! Теперь всё готово. Жду ссылки! 🎸")
        await show_main_menu(update, context)
        return WAITING_FOR_LINK
    except Exception as e:
        logger.error(f"Ошибка токена: {e}")
        await status_msg.edit_text("❌ Ой... Кажется, этот ключик не подходит. Попробуй скопировать его еще раз.")
        return WAITING_FOR_TOKEN

async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update):
        return WAITING_FOR_LINK
    if update.message.text == "🎵 Начать работу":
        return await check_session(update, context)
    if update.message.text == "🎵 Начать загрузку":
        await send_animated_message(
            context.bot, update.effective_chat.id,
            "🎵 Отправь мне ссылки на треки, альбомы или плейлисты."
        )
        return WAITING_FOR_LINK
    if update.message.text == "❌ Удалить токен":
        context.user_data.pop('yandex_token', None)
        context.user_data.pop('token_time', None)
        await send_animated_message(context.bot, update.effective_chat.id, "🔓 Токен удалён. Вы вышли из аккаунта.")
        kb = [[KeyboardButton("🎵 Начать работу")]]
        await send_animated_message(
            context.bot, update.effective_chat.id,
            "Для продолжения авторизуйтесь заново.",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
        return WAITING_FOR_LINK
    if update.message.text == "🔄 Обновить токен":
        await send_animated_message(context.bot, update.effective_chat.id, "🔑 Пожалуйста, отправь новый токен.")
        return WAITING_FOR_TOKEN

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    message = update.message

    if not is_token_valid(context):
        try:
            await message.delete()
        except Exception:
            pass
        now = time.time()
        last = last_auth_warning.get(user_id, 0)
        if now - last > WARNING_COOLDOWN:
            last_auth_warning[user_id] = now
            await context.bot.send_message(
                chat_id=chat_id,
                text="🔑 Токен не активен или истёк. Используй /start или кнопку 'Начать работу' для авторизации.\n\n"
                     "Все отправленные ссылки были удалены."
            )
        return WAITING_FOR_TOKEN

    content = (update.message.text or "") + " " + (update.message.caption or "")
    urls = re.findall(r'(https?://(?:m\.)?music\.yandex\.[a-z]{2,3}[^\s]+)', content)
    if not urls:
        return WAITING_FOR_LINK

    if user_id in user_delay_tasks:
        user_delay_tasks[user_id].cancel()
    link_accumulators.setdefault(user_id, []).extend(urls)

    async def delayed_process():
        await asyncio.sleep(1.5)
        await process_accumulated_links(user_id, chat_id, context, context.user_data['yandex_token'])

    task = asyncio.create_task(delayed_process())
    user_delay_tasks[user_id] = task

    try:
        await message.delete()
    except Exception:
        pass
    return WAITING_FOR_LINK

async def process_accumulated_links(user_id, chat_id, context, token):
    global active_tasks_count
    user_delay_tasks.pop(user_id, None)
    if user_id not in link_accumulators or not link_accumulators[user_id]:
        return
    raw_links = list(dict.fromkeys(link_accumulators.pop(user_id)))[:MAX_LINKS]
    if not raw_links:
        return

    try:
        client = await asyncio.to_thread(Client(token).init)
        await asyncio.to_thread(client.account_status)
    except Exception as e:
        logger.error(f"Ошибка клиента: {e}")
        await context.bot.send_message(chat_id, "❌ Ошибка авторизации. Попробуй снова.")
        return

    all_tasks = []
    for url in raw_links:
        try:
            if '/track/' in url:
                track_id = re.search(r'track/(\d+)', url).group(1)
                track_info = await asyncio.to_thread(client.tracks, [track_id])
                if track_info and track_info[0]:
                    t = track_info[0]
                    artist = t.artists[0].name if t.artists else "Unknown"
                    title = t.title
                    duration = t.duration_ms // 1000 if t.duration_ms else 0
                    all_tasks.append({
                        'chat_id': chat_id, 'url': url, 'token': token,
                        'artist': artist, 'title': title, 'duration': duration,
                        'track_name': f"{artist} — {title}"
                    })
                else:
                    logger.warning(f"Трек не найден: {url}")
            elif '/album/' in url and '/track/' not in url:
                album_id = re.search(r'album/(\d+)', url).group(1)
                album = await asyncio.to_thread(client.albums, album_id)
                if album and album.volumes:
                    for track in album.volumes[0]:
                        artist = track.artists[0].name if track.artists else "Unknown"
                        title = track.title
                        duration = track.duration_ms // 1000 if track.duration_ms else 0
                        track_url = f"https://music.yandex.ru/track/{track.id}"
                        all_tasks.append({
                            'chat_id': chat_id, 'url': track_url, 'token': token,
                            'artist': artist, 'title': title, 'duration': duration,
                            'track_name': f"{artist} — {title}"
                        })
                else:
                    logger.warning(f"Альбом не найден или пуст: {url}")
            elif '/playlist/' in url:
                playlist_match = re.search(r'users/([^/]+)/playlists/(\d+)', url) or re.search(r'playlist/(\d+)', url)
                if playlist_match:
                    if len(playlist_match.groups()) == 2:
                        username, playlist_id = playlist_match.groups()
                        playlist = await asyncio.to_thread(client.users_playlists, playlist_id, username)
                    else:
                        playlist_id = playlist_match.group(1)
                        playlist = await asyncio.to_thread(client.playlist, playlist_id)
                    if playlist and playlist.tracks:
                        for track_data in playlist.tracks:
                            track = track_data.track
                            if track:
                                artist = track.artists[0].name if track.artists else "Unknown"
                                title = track.title
                                duration = track.duration_ms // 1000 if track.duration_ms else 0
                                track_url = f"https://music.yandex.ru/track/{track.id}"
                                all_tasks.append({
                                    'chat_id': chat_id, 'url': track_url, 'token': token,
                                    'artist': artist, 'title': title, 'duration': duration,
                                    'track_name': f"{artist} — {title}"
                                })
                    else:
                        logger.warning(f"Плейлист не найден или пуст: {url}")
                else:
                    logger.warning(f"Не удалось распознать плейлист: {url}")
            else:
                logger.warning(f"Неизвестный тип ссылки: {url}")
        except Exception as e:
            logger.error(f"Ошибка обработки ссылки {url}: {e}")
            continue

    if not all_tasks:
        await context.bot.send_message(chat_id, "❌ Не удалось найти треки по твоим ссылкам.")
        return

    total = len(all_tasks)
    queue_position = download_queue.qsize() + 1
    msg_text = f"📥 Приняла запрос на {get_plural_tracks(total)}. Твоя позиция в очереди: {queue_position}"
    if worker_busy:
        msg_text += f"\n🎸 Сейчас я немного занята, но скоро начну скачивать твои треки."
    await context.bot.send_message(chat_id, msg_text)

    for idx, task in enumerate(all_tasks):
        task['index'] = idx + 1
        task['total'] = total
        await download_queue.put(task)

    active_tasks_count += len(all_tasks)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_animated_message(
        context.bot, update.effective_chat.id,
        "❌ Действие отменено. Используй /start для начала."
    )
    return ConversationHandler.END

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
                        f"⏰ Твой токен истечёт через {int(time_left//60)} минут. Пожалуйста, обнови его командой /start или кнопкой 'Обновить токен'."
                    )
                except Exception as e:
                    logger.error(f"Не удалось отправить напоминание: {e}")

# ------------------------------------------------------------
# ЗАПУСК
async def post_init(app):
    global download_semaphore, download_queue
    download_semaphore = asyncio.Semaphore(1)
    download_queue = asyncio.Queue()
    asyncio.create_task(worker(app))
    app.job_queue.run_repeating(lambda _: asyncio.create_task(check_all_tokens(app)), interval=900, first=10)

def main():
    if not shutil.which(DOWNLOADER_PATH):
        logger.error(f"❌ Загрузчик '{DOWNLOADER_PATH}' не найден. Установите yandex-music-downloader.")
        return

    cleanup_old_tmp_dirs()
    if not os.path.exists(STATS_FILE):
        with open(STATS_FILE, "w") as f:
            f.write("0")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start),
                      MessageHandler(filters.Regex('^🎵 Начать работу$'), handle_download)],
        states={
            WAITING_FOR_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_token)],
            WAITING_FOR_LINK: [MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_download)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    app.add_handler(CommandHandler('logout', lambda u,c: send_animated_message(c.bot, u.effective_chat.id, "Используй меню: ❌ Удалить токен")))
    app.add_handler(CommandHandler('menu', show_main_menu))
    app.add_handler(conv)

    try:
        app.run_polling()
    except KeyboardInterrupt:
        logger.info("Бот остановлен.")

if __name__ == "__main__":
    main()