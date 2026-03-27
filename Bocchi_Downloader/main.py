# (c) 2026 BocchiStation
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
from dotenv import load_dotenv

import syncedlyrics
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

# Загрузка настроек из .env
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(message)s')
logger = logging.getLogger("BocchiStation")

# --- КОНФИГУРАЦИЯ ИЗ ОКРУЖЕНИЯ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DOWNLOADER_PATH = os.getenv("DOWNLOADER_PATH", "yandex-music-downloader")
STATS_FILE = os.getenv("STATS_FILE", "stats.txt")
MAX_LINKS = 10
BOT_START_TIME = time.time()
DOWNLOAD_TIMEOUT = 600  # 10 минут для загрузки трека в Telegram

# --- ГЛОБАЛЬНЫЕ ОБЪЕКТЫ ---
download_semaphore = None
download_queue = None
link_accumulators = {}
WAITING_FOR_TOKEN, WAITING_FOR_LINK = range(2)


# --- СЕТЕВОЙ ПОИСК МЕТАДАННЫХ ---
def fetch_metadata_from_itunes(artist, title):
    """Ищет дополнительную информацию о треке в базе iTunes (альбом, год, жанр, HQ обложка)"""
    try:
        query = urllib.parse.quote(f"{artist} {title}")
        url = f"https://itunes.apple.com/search?term={query}&entity=song&limit=1"
        resp = requests.get(url, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            if data['resultCount'] > 0:
                track = data['results'][0]

                # Достаем обложку в высоком качестве (1000x1000)
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
    current_dir = Path('.')
    count = 0
    for tmp_dir in current_dir.glob('bocchi_tmp_*'):
        if tmp_dir.is_dir():
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                count += 1
            except Exception as e:
                logger.error(f"Не удалось удалить папку {tmp_dir}: {e}")

    if count > 0:
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


def get_plural_tracks(n):
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} трек"
    elif 2 <= n % 10 <= 4 and (n % 100 < 10 or n % 100 >= 20):
        return f"{n} трека"
    else:
        return f"{n} треков"


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
    while True:
        task = await download_queue.get()
        tmp_dir = Path(f"bocchi_tmp_{uuid.uuid4().hex}")

        async with download_semaphore:
            try:
                tmp_dir.mkdir(parents=True, exist_ok=True)

                status_msg = await app.bot.send_message(
                    chat_id=task['chat_id'],
                    text=f"🌀 Обработка...\n{task['track_name']}"
                )

                # Запускаем оригинальный загрузчик Яндекса (он сам вшивает базовые теги)
                cmd = [
                    DOWNLOADER_PATH, "--token", task['token'], "--quality", "2",
                    "--embed-cover", "--dir", str(tmp_dir), "--url", task['url'],
                    "--path-pattern", "#artist - #title"
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

                    # --- 1. ЧИТАЕМ БАЗОВЫЕ ДАННЫЕ ОТ ЯНДЕКСА ИЗ ФАЙЛА ---
                    artist, title, duration = "Unknown", f_path.stem, 0
                    try:
                        if f_path.suffix == '.m4a':
                            audio_read = MP4(f_path)
                            artist = audio_read.get('\xa9ART', ['Unknown'])[0]
                            title = audio_read.get('\xa9nam', [f_path.stem])[0]
                            duration = int(audio_read.info.length)
                        else:
                            audio_t, audio_i = EasyID3(f_path), MP3(f_path)
                            artist = audio_t.get('artist', ['Unknown'])[0]
                            title = audio_t.get('title', [f_path.stem])[0]
                            duration = int(audio_i.info.length)
                    except Exception as e:
                        logger.warning(f"Ошибка чтения данных от Яндекса: {e}")

                    # Чистим данные от загрузчика Яндекса
                    artist = artist.replace("#artist", "Unknown").strip()
                    title = title.replace("#artist", "").replace("#title", "").strip(" -")
                    if not artist: artist = "Unknown"
                    if not title: title = "Unknown Track"

                    display_name = f"{artist} — {title}"

                    # --- 2. ИЩЕМ НЕДОСТАЮЩИЕ ДАННЫЕ В ИНТЕРНЕТЕ ---
                    itunes_data = await asyncio.to_thread(fetch_metadata_from_itunes, artist, title)
                    lyrics = await asyncio.to_thread(syncedlyrics.search, f"{artist} {title}")
                    if lyrics:
                        lyrics = re.sub(r'\[.*?\]', '', lyrics).strip()  # Убираем таймкоды

                        # --- 3. ДОПИСЫВАЕМ НОВЫЕ ТЕГИ В ФАЙЛ ---
                        try:
                            if f_path.suffix.lower() == '.m4a':
                                audio = MP4(f_path)
                                audio['aART'] = [artist]  # Исполнитель альбома

                                # Удаляем комментарий со ссылкой
                                audio.pop('\xa9cmt', None)

                                if itunes_data.get('album'): audio['\xa9alb'] = [itunes_data['album']]
                                if itunes_data.get('year'): audio['\xa9day'] = [str(itunes_data['year'])]
                                if itunes_data.get('genre'): audio['\xa9gen'] = [itunes_data['genre']]
                                if lyrics: audio['\xa9lyr'] = [lyrics]
                                if itunes_data.get('cover_bytes'):
                                    audio['covr'] = [
                                        MP4Cover(itunes_data['cover_bytes'], imageformat=MP4Cover.FORMAT_JPEG)]
                                audio.save()
                            else:
                                audio = MP3(f_path, ID3=ID3)
                                if audio.tags is None:
                                    audio.add_tags()
                                audio.tags.add(TPE2(encoding=3, text=artist))  # Исполнитель альбома

                                # Удаляем все комментарии, которые оставил загрузчик
                                audio.tags.delall('COMM')

                                if itunes_data.get('album'): audio.tags.add(TALB(encoding=3, text=itunes_data['album']))
                                if itunes_data.get('year'): audio.tags.add(
                                    TDRC(encoding=3, text=str(itunes_data['year'])))
                                if itunes_data.get('genre'): audio.tags.add(TCON(encoding=3, text=itunes_data['genre']))
                                if lyrics: audio.tags.add(USLT(encoding=3, lang='rus', desc='Lyrics', text=lyrics))
                                if itunes_data.get('cover_bytes'):
                                    audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover',
                                                        data=itunes_data['cover_bytes']))
                                audio.save()
                        except Exception as tag_e:
                            logger.error(f"Не удалось записать дополнительные теги: {tag_e}")
                        # --- 4. ПЕРЕИМЕНОВАНИЕ ФАЙЛА ДЛЯ БЕЗОПАСНОЙ ОТПРАВКИ ---
                        safe_filename = re.sub(r'[\\/*?:"<>|]', "", f"{artist} - {title}{f_path.suffix}")
                        new_f_path = f_path.with_name(safe_filename)

                        try:
                            f_path.rename(new_f_path)
                            f_path = new_f_path
                        except Exception as e:
                            logger.error(f"Не удалось переименовать файл: {e}")
                        # ------------------------------------------------------

                        if file_size_mb > 49.0:
                            await status_msg.edit_text(
                                f"📦 Файл {display_name} весит {file_size_mb:.1f} МБ. Telegram такое не пропустит.\n"
                                f"Перенаправляю на резервное облако...")
                            try:
                                with open(f_path, 'rb') as f:
                                    resp = await asyncio.to_thread(requests.post, "https://catbox.moe/user/api.php",
                                                                   data={"reqtype": "fileupload"},
                                                                   files={"fileToUpload": f})
                                if resp.status_code == 200:
                                    await app.bot.send_message(
                                        chat_id=task['chat_id'],
                                        text=(
                                            f"🎁 Telegram не может принять такой тяжелый файл, поэтому держи ссылку:\n\n"
                                            f"🎵 {display_name}\n"
                                            f"⚖️ Размер: {file_size_mb:.1f} МБ\n"
                                            f"🔗 Скачать: {resp.text}"),
                                        disable_web_page_preview=True
                                    )
                                else:
                                    raise Exception()
                            except:
                                await app.bot.send_message(chat_id=task['chat_id'],
                                                           text=f"❌ Ошибка загрузки {display_name} на облако.")
                        else:
                            with open(f_path, 'rb') as f:
                                await app.bot.send_audio(
                                    chat_id=task['chat_id'], audio=f,
                                    performer=artist, title=title, duration=duration,
                                    read_timeout=600, write_timeout=600, connect_timeout=600, pool_timeout=600
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


# --- ХЕНДЛЕРЫ ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    if 'yandex_token' in context.user_data:
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
        login = client.account_status().account.login
        await status_msg.edit_text(f"✅ Ура! Я узнала тебя, {login}! Теперь всё готово. Жду ссылки! 🎸")
        return WAITING_FOR_LINK
    except Exception as e:
        logger.error(f"Ошибка токена: {e}")
        await status_msg.edit_text("❌ Ой... Кажется, этот ключик не подходит. Попробуй скопировать его еще раз.")
        return WAITING_FOR_TOKEN


async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🎵 Начать работу":
        return await check_session(update, context)

    if 'yandex_token' not in context.user_data:
        return await check_session(update, context)

    content = (update.message.text or "") + " " + (update.message.caption or "")
    urls = re.findall(r'(https?://(?:m\.)?music\.yandex\.[a-z]{2,3}[^\s]+)', content)

    if not urls: return WAITING_FOR_LINK

    user_id = update.effective_user.id
    if user_id not in link_accumulators:
        link_accumulators[user_id] = []
        context.job_queue.run_once(process_accumulated_links, 1.5, data={
            'user_id': user_id, 'chat_id': update.effective_chat.id,
            'token': context.user_data['yandex_token']
        })

    link_accumulators[user_id].extend(urls)

    try:
        await update.message.delete()
    except:
        pass

    return WAITING_FOR_LINK


async def process_accumulated_links(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    user_id = data['user_id']
    if user_id not in link_accumulators or not link_accumulators[user_id]: return

    links = list(dict.fromkeys(link_accumulators.pop(user_id)))[:MAX_LINKS]
    total = len(links)
    if total == 0: return

    is_busy = download_semaphore.locked()
    msg_text = f"📥 Приняла запрос на {get_plural_tracks(total)}."

    if is_busy:
        q_size = download_queue.qsize()
        msg_text += f"\n🎸 Сейчас я немного занята на сервере... Твоя позиция в очереди: {q_size + 1}"

    init_msg = await context.bot.send_message(chat_id=data['chat_id'], text=msg_text)

    try:
        client = await asyncio.to_thread(Client(data['token']).init)

        for i, url in enumerate(links):
            track_name = "Аудиозапись (определяю...)"
            try:
                if '/track/' in url:
                    tid = re.search(r'track/(\d+)', url).group(1)
                    tinfo = await asyncio.to_thread(client.tracks, [tid])
                    if tinfo and tinfo[0]:
                        t = tinfo[0]
                        track_name = f"{t.artists[0].name} — {t.title}"
                elif '/album/' in url and '/track/' not in url:
                    track_name = "Целый альбом"
            except:
                pass

            await download_queue.put({
                'chat_id': data['chat_id'], 'url': url, 'token': data['token'],
                'track_name': track_name, 'index': i + 1, 'total': total,
                'init_msg_id': init_msg.message_id if i == 0 else None,
            })
    except Exception as e:
        logger.error(f"Process Links Error: {e}")


# --- МОНИТОРИНГ ---

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

        work_block = (
            "Очередь и загрузки 📥\n"
            f"• Сейчас меня ждут {download_queue.qsize()} человек\n"
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
    with open(STATS_FILE, "w") as f:
        f.write("0")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            MessageHandler(filters.Regex('^🎵 Начать работу$'), handle_download)
        ],
        states={
            WAITING_FOR_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_token)],
            WAITING_FOR_LINK: [MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_download)],
        },
        fallbacks=[CommandHandler('start', start)]

    )

    app.add_handler(CommandHandler('status', cmd_status))
    app.add_handler(conv)
    print("🎸 Бот запущен, статистика обнулена.")
    app.run_polling()


if __name__ == "__main__":
    main()
