# (c) 2026 Hanako
# Проект "Bocchi Downloader"
# Копирование и использование без разрешения автора запрещено.

import subprocess
import asyncio
import logging
import time
import re
import os
import uuid
import psutil
import shutil
import random
import requests
import urllib.parse
from pathlib import Path

import syncedlyrics  # не используется, но оставлен на случай
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, USLT, TDRC, TCON, TALB, APIC, TPE2
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover

from yandex_music import Client
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters, Application
)
from dotenv import load_dotenv

# Новая библиотека для Catbox / Litterbox
from catboxpy import AsyncCatboxClient, LitterboxClient

load_dotenv()

# --- НАСТРОЙКА ЛОГИРОВАНИЯ ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(message)s')
logger = logging.getLogger("BocchiStation")

# --- КОНФИГУРАЦИЯ (из переменных окружения) ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТОКЕН_ЗДЕСЬ")
DOWNLOADER_PATH = os.getenv("DOWNLOADER_PATH", "yandex-music-downloader")
STATS_FILE = os.getenv("STATS_FILE", "../stats.txt")
MAX_LINKS = int(os.getenv("MAX_LINKS", "10"))
DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", "600"))  # 10 минут
TOKEN_LIFETIME = int(os.getenv("TOKEN_LIFETIME", "86400"))    # 24 часа

BOT_START_TIME = time.time()

# --- ГЛОБАЛЬНЫЕ ОБЪЕКТЫ ---
download_semaphore = None
download_queue = None
link_accumulators = {}
worker_busy = False
active_tasks_count = 0
WAITING_FOR_TOKEN, WAITING_FOR_LINK = range(2)

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def is_message_too_old(update: Update) -> bool:
    if update.message:
        msg_time = update.message.date.timestamp()
        return msg_time < BOT_START_TIME
    return False

def get_plural_tracks(n):
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} трек"
    elif 2 <= n % 10 <= 4 and (n % 100 < 10 or n % 100 >= 20):
        return f"{n} трека"
    else:
        return f"{n} треков"

# --- СЕТЕВОЙ ПОИСК МЕТАДАННЫХ (iTunes) ---
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
        logger.error(f"Ошибка поиска в iTunes API: {e}")
    return {}

# --- УТИЛИТЫ ---
def cleanup_old_tmp_dirs():
    count = 0
    for tmp_dir in Path('.').glob('bocchi_tmp_*'):
        if tmp_dir.is_dir():
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                count += 1
            except Exception as e:
                logger.error(f"Не удалось удалить папку {tmp_dir}: {e}")
    if count:
        print(f"🎸 Найдено и удалено забытых временных папок: {count}")

def add_stats(bytes_added):
    try:
        current = 0.0
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, "r") as f: current = float(f.read())
        with open(STATS_FILE, "w") as f:
            f.write(str(current + bytes_added))
    except:
        pass

def get_formatted_stats():
    try:
        if not os.path.exists(STATS_FILE): return "0 Б"
        with open(STATS_FILE, "r") as f:
            bytes_val = float(f.read())
        for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
            if bytes_val < 1024.0: return f"{bytes_val:.2f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.2f} ТБ"
    except:
        return "0 Б"

def get_v2raya_status():
    try:
        status = subprocess.check_output(["systemctl", "is-active", "v2raya"]).decode().strip()
        return "🟢 Включена" if status == "active" else "🔴 Выключена"
    except:
        return "⚪ Статус неизвестен"

def get_network_signal():
    try:
        with open("/proc/net/wireless", "r") as f:
            lines = f.readlines()
            if len(lines) > 2:
                data = lines[2].split()
                return f"{data[3].replace('.', '')} дБм (Lnk: {data[2].replace('.', '')}/70)"
    except:
        pass
    return "🔌 Ethernet"

def get_ping():
    try:
        output = subprocess.check_output(["ping", "-c", "1", "-W", "1", "ya.ru"], stderr=subprocess.STDOUT, text=True)
        match = re.search(r'time=([\d\.]+)', output)
        return float(match.group(1)) if match else 0.0
    except:
        return 0.0

def get_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return float(f.read()) / 1000.0
    except:
        return None

# --- ВОРКЕР (ЗАГРУЗКА) ---

async def worker(app: Application):
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

                cmd = [
                    DOWNLOADER_PATH, "--token", task['token'], "--quality", "2",
                    "--embed-cover", "--dir", str(tmp_dir), "--url", task['url'],
                    "--path-pattern", "#artist - #title",
                    "--lyrics-format", "lrc"
                ]

                proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE,
                                                            stderr=asyncio.subprocess.PIPE)

                try:
                    await asyncio.wait_for(proc.wait(), timeout=DOWNLOAD_TIMEOUT)
                except asyncio.TimeoutError:
                    try:
                        proc.kill()
                    except:
                        pass
                    await app.bot.send_message(
                        chat_id=task['chat_id'],
                        text="Ой... Кажется, я слишком долго пытаюсь это скачать. Сервер молчит, поэтому я вынуждена прерваться, чтобы не заставлять других ждать в очереди 🎸"
                    )
                    continue

                files = [f for f in tmp_dir.rglob('*') if f.suffix.lower() in ['.mp3', '.m4a']]
                for f_path in files:
                    file_size_mb = f_path.stat().st_size / (1024 * 1024)

                    # --- 1. ИСПОЛЬЗУЕМ ДАННЫЕ ИЗ API, ПЕРЕДАННЫЕ В ЗАДАЧЕ ---
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
                            logger.warning(f"Ошибка чтения данных из файла: {e}")
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

                    # --- 2. ИЩЕМ LRC-ФАЙЛ ---
                    lyrics = None
                    base_name = f_path.stem
                    lrc_files = list(tmp_dir.glob(f"{base_name}.lrc"))
                    if lrc_files:
                        lrc_file = lrc_files[0]
                        try:
                            with open(lrc_file, 'r', encoding='utf-8') as f:
                                lyrics = f.read().strip()
                            logger.info(f"LRC-текст найден в файле {lrc_file.name}")
                        except Exception as e:
                            logger.warning(f"Ошибка чтения LRC-файла: {e}")

                    # --- 3. ИЩЕМ НЕДОСТАЮЩИЕ ДАННЫЕ В ITUNES ---
                    itunes_data = await asyncio.to_thread(fetch_metadata_from_itunes, artist, title)

                    # --- 4. ДОПИСЫВАЕМ НОВЫЕ ТЕГИ В ФАЙЛ ---
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
                        logger.error(f"Не удалось записать дополнительные теги: {tag_e}")

                    # --- 5. ПЕРЕИМЕНОВАНИЕ ФАЙЛА ---
                    safe_filename = re.sub(r'[\\/*?:"<>|]', "", f"{artist} - {title}{f_path.suffix}")
                    new_f_path = f_path.with_name(safe_filename)

                    try:
                        f_path.rename(new_f_path)
                        f_path = new_f_path
                    except Exception as e:
                        logger.error(f"rename не удался: {e}, пробуем shutil.move")
                        try:
                            shutil.move(str(f_path), str(new_f_path))
                            f_path = new_f_path
                        except Exception as move_e:
                            logger.error(f"shutil.move тоже не сработал: {move_e}")
                            await app.bot.send_message(chat_id=task['chat_id'],
                                                       text=f"❌ Не удалось переименовать файл {display_name}.")
                            continue

                    if not f_path.exists():
                        logger.error(f"Файл не найден после переименования: {f_path}")
                        await app.bot.send_message(chat_id=task['chat_id'],
                                                   text=f"❌ Не удалось найти файл {display_name}.")
                        continue

                    # --- 6. ОТПРАВКА (Catbox/Litterbox) ---
                    if file_size_mb > 49.0:
                        uploaded = False
                        error_message = ""

                        # Сначала пробуем Litterbox (временное хранилище)
                        await status_msg.edit_text(
                            f"📦 Файл {display_name} весит {file_size_mb:.1f} МБ. Загружаю на временное облако...")
                        try:
                            litterbox = LitterboxClient()
                            # upload_file — синхронный, оборачиваем в asyncio.to_thread
                            url = await asyncio.to_thread(
                                litterbox.upload_file,
                                str(f_path),
                                expire_time="24h"
                            )
                            if url and url.startswith(("https://", "http://")):
                                await app.bot.send_message(
                                    chat_id=task['chat_id'],
                                    text=(
                                        f"🎁 Файл {display_name} слишком велик для Telegram.\n"
                                        f"Вот временная ссылка (действует 24 часа):\n\n"
                                        f"🔗 {url}"),
                                    disable_web_page_preview=True
                                )
                                uploaded = True
                            else:
                                error_message = "Litterbox вернул не ссылку"
                        except Exception as e:
                            error_message = f"Litterbox: {e}"
                            logger.error(error_message)

                        # Если Litterbox не сработал, пробуем Catbox (постоянное хранилище)
                        if not uploaded:
                            await status_msg.edit_text(
                                f"📦 Не удалось загрузить на временное облако, пробую постоянное...")
                            try:
                                catbox = AsyncCatboxClient()
                                url = await catbox.upload(str(f_path))
                                if url and url.startswith(("https://", "http://")):
                                    await app.bot.send_message(
                                        chat_id=task['chat_id'],
                                        text=(
                                            f"🎁 Файл {display_name} слишком велик для Telegram.\n"
                                            f"Вот постоянная ссылка (файл не удалится):\n\n"
                                            f"🔗 {url}"),
                                        disable_web_page_preview=True
                                    )
                                    uploaded = True
                                else:
                                    error_message = "Catbox вернул не ссылку"
                            except Exception as e:
                                error_message = f"Catbox: {e}"
                                logger.error(error_message)

                        if not uploaded:
                            await app.bot.send_message(
                                chat_id=task['chat_id'],
                                text=f"❌ Не удалось загрузить {display_name}. Ошибка: {error_message}"
                            )
                    else:
                        # Для файлов до 49 МБ отправляем через Bot API
                        try:
                            with open(f_path, 'rb') as f:
                                await app.bot.send_audio(
                                    chat_id=task['chat_id'],
                                    audio=f,
                                    performer=artist,
                                    title=title,
                                    duration=duration if duration > 0 else None,
                                    filename=safe_filename,
                                    read_timeout=600,
                                    write_timeout=600,
                                    connect_timeout=600,
                                    pool_timeout=600
                                )
                            logger.info(f"Успешно отправлен трек: {display_name}")
                        except Exception as e:
                            logger.error(f"Ошибка при отправке аудио {display_name}: {e}", exc_info=True)
                            await app.bot.send_message(
                                chat_id=task['chat_id'],
                                text=f"❌ Не удалось отправить {display_name}: {str(e)[:200]}"
                            )

                    add_stats(f_path.stat().st_size)

                try:
                    await status_msg.delete()
                except:
                    pass

            except Exception as e:
                logger.error(f"Worker Error: {e}")
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                download_queue.task_done()
                active_tasks_count -= 1
                worker_busy = False


# --- ХЕНДЛЕРЫ ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update):
        logger.debug("Игнорирую старое сообщение /start")
        return WAITING_FOR_LINK

    kb = [[KeyboardButton("🎵 Начать работу")]]
    welcome_text = (
        "🌸 Привет! Это Bocchi Downloader 🎸\n"
        "Я живу на маленькой станции Raspberry Pi (на моей любимой малинке).\n"
        "И я очень постараюсь помочь тебе скачать любимые треки из Яндекс Музыки, чтобы они всегда были под рукой.\n\n"
        "✨ Как мы будем работать:\n"
        f"• Можешь присылать до {MAX_LINKS} ссылок за один раз.\n"
        "• Я буду скачивать всё аккуратно и строго по очереди.\n\n"
        "Жми кнопку ниже, чтобы войти в аккаунт и начать!"
    )
    await update.message.reply_text(
        welcome_text,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )
    return WAITING_FOR_LINK


async def check_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update):
        logger.debug("Игнорирую старое сообщение в check_session")
        return WAITING_FOR_LINK

    if 'yandex_token' in context.user_data:
        token_time = context.user_data.get('token_time', 0)
        if time.time() - token_time > TOKEN_LIFETIME:
            del context.user_data['yandex_token']
            if 'token_time' in context.user_data:
                del context.user_data['token_time']
            await update.message.reply_text(
                "🕐 Срок действия токена истёк. Пожалуйста, авторизуйтесь заново."
            )
            return WAITING_FOR_LINK
        await update.message.reply_text("✅ Токен активен. Жду твои ссылки!")
        return WAITING_FOR_LINK

    auth_text = (
        "🔑 Авторизация\n\n"
        "Чтобы я могла найти твои треки в хорошем качестве, мне нужен доступ к Яндекс Музыке.\n\n"
        "1️⃣ Перейди по [этой ссылке](https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41195d)\n"
        "2️⃣ Нажми «Войти» или «Разрешить».\n"
        "3️⃣ После входа страница может стать первоначальной или полностью пустой — не пугайся, так и должно быть!\n"
        "4️⃣ Скопируй весь адрес из строки браузера (там будет длинный-длинный текст) и отправь его мне сюда 📋"
    )
    await update.message.reply_text(auth_text, parse_mode="Markdown", disable_web_page_preview=True)
    return WAITING_FOR_TOKEN


async def save_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update):
        logger.debug("Игнорирую старое сообщение в save_token")
        return WAITING_FOR_TOKEN

    raw_text = update.message.text.strip()
    token_match = re.search(r"(y0_[a-zA-Z0-9_-]+)", raw_text)
    token = token_match.group(1) if token_match else raw_text

    try:
        await update.message.delete()
    except:
        pass

    status_msg = await update.message.reply_text("🔍 Заглядываю в твой токен...")
    try:
        client = await asyncio.to_thread(Client(token).init)
        context.user_data['yandex_token'] = token
        context.user_data['token_time'] = time.time()
        login = client.account_status().account.login
        await status_msg.edit_text(f"✅ Ура! Я узнала тебя, {login}! Теперь всё готово. Жду ссылки! 🎸")
        return WAITING_FOR_LINK
    except Exception as e:
        logger.error(f"Ошибка токена: {e}")
        await status_msg.edit_text("❌ Ой... Кажется, этот ключик не подходит. Попробуй скопировать его еще раз.")
        return WAITING_FOR_TOKEN


async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update):
        logger.debug(f"Игнорирую старое сообщение от {update.effective_user.id}")
        return WAITING_FOR_LINK

    if update.message.text == "🎵 Начать работу":
        return await check_session(update, context)

    if 'yandex_token' in context.user_data:
        token_time = context.user_data.get('token_time', 0)
        if time.time() - token_time > TOKEN_LIFETIME:
            del context.user_data['yandex_token']
            if 'token_time' in context.user_data:
                del context.user_data['token_time']
            await update.message.reply_text(
                "🕐 Срок действия токена истёк. Пожалуйста, авторизуйтесь заново."
            )
            return WAITING_FOR_LINK
    else:
        return await check_session(update, context)

    content = (update.message.text or "") + " " + (update.message.caption or "")
    urls = re.findall(r'(https?://(?:m\.)?music\.yandex\.[a-z]{2,3}[^\s]+)', content)

    if not urls:
        return WAITING_FOR_LINK

    user_id = update.effective_user.id
    if user_id not in link_accumulators:
        link_accumulators[user_id] = []
        context.job_queue.run_once(process_accumulated_links, 1.5, data={
            'user_id': user_id,
            'chat_id': update.effective_chat.id,
            'token': context.user_data['yandex_token']
        })

    link_accumulators[user_id].extend(urls)

    try:
        await update.message.delete()
    except:
        pass

    return WAITING_FOR_LINK


async def process_accumulated_links(context: ContextTypes.DEFAULT_TYPE):
    global active_tasks_count
    data = context.job.data
    user_id = data['user_id']
    if user_id not in link_accumulators or not link_accumulators[user_id]:
        return

    raw_links = list(dict.fromkeys(link_accumulators.pop(user_id)))[:MAX_LINKS]
    if not raw_links:
        return

    try:
        client = await asyncio.to_thread(Client(data['token']).init)
    except Exception as e:
        logger.error(f"Не удалось инициализировать клиент: {e}")
        await context.bot.send_message(chat_id=data['chat_id'], text="❌ Ошибка авторизации. Попробуй снова.")
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
                    track_name = f"{artist} — {title}"
                    all_tasks.append({
                        'chat_id': data['chat_id'],
                        'url': url,
                        'token': data['token'],
                        'artist': artist,
                        'title': title,
                        'duration': duration,
                        'track_name': track_name
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
                        track_name = f"{artist} — {title}"
                        all_tasks.append({
                            'chat_id': data['chat_id'],
                            'url': track_url,
                            'token': data['token'],
                            'artist': artist,
                            'title': title,
                            'duration': duration,
                            'track_name': track_name
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
                                track_name = f"{artist} — {title}"
                                all_tasks.append({
                                    'chat_id': data['chat_id'],
                                    'url': track_url,
                                    'token': data['token'],
                                    'artist': artist,
                                    'title': title,
                                    'duration': duration,
                                    'track_name': track_name
                                })
                    else:
                        logger.warning(f"Плейлист не найден или пуст: {url}")
                else:
                    logger.warning(f"Не удалось распознать плейлист: {url}")
            else:
                logger.warning(f"Неизвестный тип ссылки: {url}")
        except Exception as e:
            logger.error(f"Ошибка обработки ссылки {url}: {e}")

    if not all_tasks:
        await context.bot.send_message(chat_id=data['chat_id'], text="❌ Не удалось найти треки по твоим ссылкам.")
        return

    total = len(all_tasks)
    is_busy = worker_busy
    msg_text = f"📥 Приняла запрос на {get_plural_tracks(total)}."

    if is_busy:
        q_size = download_queue.qsize()
        msg_text += f"\n🎸 Сейчас я немного занята на сервере... Твоя позиция в очереди: {q_size + 1}"

    init_msg = await context.bot.send_message(chat_id=data['chat_id'], text=msg_text)

    for idx, task in enumerate(all_tasks):
        task['index'] = idx + 1
        task['total'] = total
        task['init_msg_id'] = init_msg.message_id if idx == 0 else None
        await download_queue.put(task)

    active_tasks_count += len(all_tasks)


async def cmd_logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update):
        return
    if 'yandex_token' in context.user_data:
        del context.user_data['yandex_token']
        if 'token_time' in context.user_data:
            del context.user_data['token_time']
        await update.message.reply_text("🔓 Токен удалён. Вы вышли из аккаунта.")
    else:
        await update.message.reply_text("Вы и так не авторизованы.")


# --- МОНИТОРИНГ ---

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_message_too_old(update):
        logger.debug("Игнорирую старое сообщение /status")
        return

    status_msg = await update.message.reply_text(
        "🌸 Секретный блокнот Хитори 🎸\n\n"
        "Ой! Ты... ты заглянул сюда?!\n"
        "Я... я не думала, что кому-то захочется смотреть на мои записи.\n\n"
        "Подожди секунду, я попробую записать всё, что сейчас чувствую...\n"
        "Т-только не смотри слишком пристально, ладно?"
    )
    await asyncio.sleep(3)
    res_block, net_block, work_block = "", "", ""

    for i in range(15):
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory()

        temp = get_temp()
        if temp is None:
            t_status = "⚪ не знаю, что со мной... не могу найти датчик температуры"
        elif temp < 45:
            t_status = f"🟢 чувствую себя отлично, мне совсем не жарко ({temp:.1f}°C)"
        elif temp < 60:
            t_status = f"🟡 работаю в обычном режиме, всё в порядке ({temp:.1f}°C)"
        elif temp < 70:
            t_status = f"🟠 ощущаю нагрузку, внутри становится теплее ({temp:.1f}°C)"
        elif temp < 85:
            t_status = f"🔴 чувствую себя тяжеловато, плата сильно нагрелась ({temp:.1f}°C)"
        else:
            t_status = f"🚫 кажется, сгорю... мне очень плохо! ({temp:.1f}°C)"

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

        net_signal = get_network_signal()
        if "дБм" in net_signal:
            try:
                dbm = int(re.search(r'(-\d+)', net_signal).group(1))
                if dbm >= -50:
                    n_lvl = "сейчас просто идеальная"
                elif dbm >= -70:
                    n_lvl = "вполне стабильная"
                elif dbm >= -85:
                    n_lvl = "стала какой-то слабой"
                else:
                    n_lvl = "почти совсем пропала..."
            except:
                n_lvl = "вроде бы держится"
        elif "Eth" in net_signal or "кабель" in net_signal.lower():
            n_lvl = "подключена по проводам, тут всё надежно"
        else:
            n_lvl = "ведет себя странно, я не понимаю сигнал"

        res_block = (
            "Моё самочувствие 🌸\n"
            f"• Мои мысли заняты {c_status} ({cpu}%)\n"
            f"• Моя память заполнена {m_status} ({mem.percent}%)\n"
            f"• Сейчас я {t_status}\n\n"
        )

        net_block = (
            "Связь с миром 🌐\n"
            f"• Маскировка сети: {get_v2raya_status()}\n"
            f"• Моя сеть: {n_lvl} ({net_signal})\n"
            f"• Скорость отклика: {get_ping()} мс к серверам Яндекса\n\n"
        )

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

        footer = f"⏱ Побуду с тобой еще {15 - i} сек...\n{random.choice(live_thoughts)}"
        full_text = f"🌸 Секретный блокнот Хитори 🎸\n\n{res_block}{net_block}{work_block}{footer}"

        try:
            await status_msg.edit_text(full_text)
        except:
            pass
        await asyncio.sleep(1)

    try:
        final_text = (
            f"🌸 Секретный блокнот Хитори 🎸\n\n"
            f"{res_block}{net_block}{work_block}"
            f"✅ (Фух... Я закончила слежку. Пойду спрячусь обратно в шкаф...)"
        )
        await status_msg.edit_text(final_text)
        await asyncio.sleep(5)
        await status_msg.delete()
    except Exception as e:
        logger.error(f"Ошибка при удалении секретного блокнота: {e}")


# --- ЗАПУСК ---

async def post_init(app: Application):
    global download_semaphore, download_queue
    download_semaphore = asyncio.Semaphore(1)
    download_queue = asyncio.Queue()
    asyncio.create_task(worker(app))


def main():
    cleanup_old_tmp_dirs()
    if not os.path.exists(STATS_FILE):
        with open(STATS_FILE, "w") as f: f.write("0")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start),
                      MessageHandler(filters.Regex('^🎵 Начать работу$'), handle_download)],
        states={
            WAITING_FOR_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_token)],
            WAITING_FOR_LINK: [MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_download)],
        },
        fallbacks=[CommandHandler('start', start)]
    )

    app.add_handler(CommandHandler('status', cmd_status))
    app.add_handler(CommandHandler('logout', cmd_logout))
    app.add_handler(conv)
    app.run_polling()


if __name__ == "__main__":
    main()
