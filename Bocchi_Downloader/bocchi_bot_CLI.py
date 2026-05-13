#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bocchi Downloader CLI — консольная версия загрузчика музыки с Яндекс.Музыки.
Автор: Hanako (c) 2026
Безопасная версия с защитой от SSRF, Path Traversal, Log Injection.
Расширенная поддержка всех типов ссылок (включая uuid/iframe плейлисты).
"""

import asyncio
import atexit
import json
import logging
import os
import re
import shutil
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import aiohttp
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, USLT, TDRC, TCON, APIC, TPE2
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from yandex_music import Client

# ---------- цветной вывод (опционально) ----------
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    C = {
        'info': Fore.CYAN,
        'ok': Fore.GREEN,
        'warn': Fore.YELLOW,
        'err': Fore.RED,
        'menu': Fore.MAGENTA,
        'reset': Style.RESET_ALL,
    }
except ImportError:
    C = {k: '' for k in ['info', 'ok', 'warn', 'err', 'menu', 'reset']}

def cprint(text, color='info'):
    """Выводит цветной текст, если доступна colorama."""
    print(f"{C.get(color, '')}{text}{C['reset']}")

# ---------- получение одного символа с клавиатуры (для отмены) ----------
if os.name == 'nt':
    import msvcrt
    def getch():
        return msvcrt.getch().decode('utf-8', errors='ignore')
else:
    import termios, tty
    def getch():
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        return ch

# ---------- папка для хранения данных ----------
SCRIPT_DIR = Path(sys.argv[0]).parent.resolve()
APP_DIR = SCRIPT_DIR / "Data"
APP_DIR.mkdir(parents=True, exist_ok=True)

# ---------- логирование ----------
LOG_DIR = APP_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_PATH = LOG_DIR / f"bocchi_{time.strftime('%Y-%m-%d_%H-%M-%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(LOG_PATH, encoding='utf-8')]
)
logger = logging.getLogger("BocchiCLI")

# ---------- хранение токена ----------
TOKEN_FILE = APP_DIR / "token.json"

# ---------- папка для загрузок (адаптирована под мобильные устройства) ----------
def get_download_dir():
    termux = Path("/data/data/com.termux/files/home/storage/downloads")
    if termux.exists():
        return termux / "BocchiDownloads"
    android = Path("/storage/emulated/0/Download")
    if android.exists():
        return android / "BocchiDownloads"
    home = Path.home() / "Downloads"
    if home.exists():
        return home / "BocchiDownloads"
    return Path.home() / "BocchiDownloads"

DOWNLOAD_DIR = get_download_dir()
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ---------- настройки (можно переопределить через переменные окружения) ----------
DOWNLOADER_PATH = os.getenv("DOWNLOADER_PATH", "yandex-music-downloader")
MAX_LINKS = int(os.getenv("MAX_LINKS", "10"))
DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", "600"))
TOKEN_LIFETIME = int(os.getenv("TOKEN_LIFETIME", "86400"))
DEFAULT_QUALITY = int(os.getenv("DEFAULT_QUALITY", "2"))
MIN_FREE_DISK_MB = int(os.getenv("MIN_FREE_DISK_MB", "20"))
TRACK_DELAY_SECONDS = float(os.getenv("TRACK_DELAY_SECONDS", "2.0"))

# ========== БЕЗОПАСНАЯ ОБРАБОТКА STATS_FILE (закрытие CWE-22, CWE-117) ==========
DATA_DIR = APP_DIR

def resolve_stats_file_path():
    """
    Безопасно определяет путь к файлу статистики.
    Закрывает уязвимости Path Traversal (#43, #45) и Log Injection (#51).
    """
    raw_stats_file = os.getenv("STATS_FILE", "stats.txt")
    # Защита от Log Injection: удаляем \r и \n
    safe_for_log = raw_stats_file.replace("\r", "").replace("\n", "")

    base_dir = DATA_DIR.resolve()
    default_path = (base_dir / "stats.txt").resolve()

    raw_path = Path(raw_stats_file)

    if raw_path.is_absolute():
        logger.warning("Небезопасный STATS_FILE '%s', используется значение по умолчанию.", safe_for_log)
        return default_path

    safe_parts = []
    for part in raw_path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            logger.warning("Небезопасный STATS_FILE '%s', используется значение по умолчанию.", safe_for_log)
            return default_path
        safe_parts.append(part)

    try:
        candidate = (base_dir / Path(*safe_parts)).resolve()
    except Exception:
        logger.warning("STATS_FILE вызвал ошибку разрешения пути: '%s'", safe_for_log)
        return default_path

    if candidate == base_dir or base_dir in candidate.parents:
        return candidate
    else:
        logger.warning("STATS_FILE выходит за пределы DATA_DIR: '%s'", safe_for_log)
        return default_path

STATS_FILE_PATH = resolve_stats_file_path()

QUALITY_NAMES = {0: "Низкое", 1: "Среднее", 2: "Высокое"}
QUALITY_NAMES_GENITIVE = {0: "низкого", 1: "среднего", 2: "высокого"}

# ---------- глобальное состояние ----------
user_quality = DEFAULT_QUALITY
user_token = None
token_timestamp = 0

# ---------- работа с токеном ----------
def save_token(token):
    global user_token, token_timestamp
    user_token = token
    token_timestamp = time.time()
    try:
        TOKEN_FILE.write_text(
            json.dumps({"token": token, "timestamp": token_timestamp}),
            encoding='utf-8'
        )
    except Exception as e:
        logger.error("Ошибка сохранения токена: %s", e)

def load_token():
    global user_token, token_timestamp
    if not TOKEN_FILE.exists():
        return False
    try:
        data = json.loads(TOKEN_FILE.read_text(encoding='utf-8'))
        if time.time() - data.get('timestamp', 0) <= TOKEN_LIFETIME:
            user_token = data['token']
            token_timestamp = data['timestamp']
            return True
    except Exception as e:
        logger.error("Ошибка загрузки токена: %s", e)
    return False

def delete_token():
    global user_token, token_timestamp
    user_token = None
    token_timestamp = 0
    try:
        TOKEN_FILE.unlink(missing_ok=True)
    except Exception:
        pass

def is_token_valid():
    return user_token and (time.time() - token_timestamp) <= TOKEN_LIFETIME

# ---------- очистка при выходе ----------
def cleanup():
    logger.info("Очистка временных файлов...")
    try:
        for old in LOG_DIR.glob("bocchi_*.log"):
            if old.stat().st_mtime < time.time() - 86400:
                old.unlink(missing_ok=True)
    except Exception:
        pass
    for d in Path('.').glob('bocchi_tmp_*'):
        try:
            shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass

atexit.register(cleanup)

# ---------- вспомогательные функции ----------
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def wait_for_enter():
    print()
    cprint("Нажмите Enter, чтобы вернуться в меню...", 'info')
    input()

def get_plural_tracks(n):
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} трек"
    if 2 <= n % 10 <= 4 and (n % 100 < 10 or n % 100 >= 20):
        return f"{n} трека"
    return f"{n} треков"

def check_disk_space():
    try:
        free_mb = shutil.disk_usage(DOWNLOAD_DIR).free / (1024 * 1024)
        return free_mb >= MIN_FREE_DISK_MB, free_mb
    except Exception:
        return True, 9999

# ---------- безопасная загрузка обложек (защита от SSRF) ----------
ALLOWED_COVER_HOSTS = {
    'avatars.yandex.net',
    'music.yandex.ru',
    'music.yandex.net',
}

async def fetch_cover(uri):
    """Загружает обложку, проверяя безопасность URL."""
    if not uri:
        return None
    try:
        raw_url = f"https://{uri.replace('%%', '1000x1000')}"
        parsed = urlparse(raw_url)
        if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_COVER_HOSTS:
            cprint(f"⚠️ Заблокирована небезопасная ссылка на обложку", 'warn')
            return None
        async with aiohttp.ClientSession() as s:
            async with s.get(raw_url, timeout=aiohttp.ClientTimeout(15)) as r:
                if r.status == 200:
                    return await r.read()
        return None
    except Exception:
        return None

def extract_base_url(url):
    pattern = r'(https?://(?:[a-z0-9-]+\.)*yandex\.[a-z]{2,3})(?:/music)?'
    m = re.match(pattern, url, re.I)
    if m:
        base = m.group(1)
        if '/music' in url or 'music.' in url:
            return f"{base}/music"
        return base
    return "https://music.yandex.ru"

# ---------- расширенный парсинг URL (из серверной версии) ----------
def parse_yandex_url(url):
    parsed = urlparse(url)
    path = parsed.path
    query = parse_qs(parsed.query)

    # iframe-плейлист (новый)
    m = re.search(r'/iframe/playlist/([^/]+)/(\d+)', path)
    if m:
        return ('iframe_playlist', m.group(2), m.group(1))

    m = re.search(r'/track/(\d+)', path)
    if m:
        return ('track', m.group(1), None)

    m = re.search(r'/album/(\d+)', path)
    if m:
        return ('album', m.group(1), None)

    m = re.search(r'/users/([^/]+)/playlists/(\d+)', path)
    if m:
        return ('playlist', m.group(2), m.group(1))

    m = re.search(r'/playlist/(\d+)', path)
    if m:
        return ('playlist', m.group(1), None)

    # uuid-плейлист (например, /playlists/ps.12345)
    m = re.search(r'/playlists/([a-z0-9\-\.]+)', path)
    if m:
        return ('uuid_playlist', m.group(1), None)

    # старый формат handlers/playlist.jsx
    if 'handlers/playlist.jsx' in path:
        owner = query.get('owner', [None])[0]
        kinds = query.get('kinds', [None])[0]
        if owner and kinds:
            return ('playlist', kinds, owner)

    return (None, None, None)

# ---------- сбор треков из ссылок (безопасный, с поддержкой всех типов) ----------
async def collect_tracks_from_links(links):
    if not links:
        return []

    cprint(f"📎 Принято ссылок: {len(links)}. Анализирую...", 'info')

    # Безопасный API-запрос (защита от SSRF)
    ALLOWED_API_HOSTS = {
        'api.music.yandex.net',
        'api.music.yandex.ru',
    }

    async def api_request(url):
        headers = {"Authorization": f"OAuth {user_token}"}
        parsed = urlparse(url)

        if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_API_HOSTS:
            cprint(f"❌ Заблокирован небезопасный URL API: {url}", 'err')
            return 0, None

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as r:
                return r.status, await r.json() if r.status == 200 else None

    try:
        client = await asyncio.to_thread(Client, user_token)
        client = await asyncio.to_thread(client.init)
    except Exception as e:
        cprint(f"❌ Ошибка авторизации: {e}", 'err')
        return []

    all_tracks = []
    id_digits_re = re.compile(r'^\d+$')
    owner_re = re.compile(r'^[A-Za-z0-9._-]+$')
    uuid_re = re.compile(
        r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$'
    )
    for url in links:
        base = extract_base_url(url)
        typ, cid, username = parse_yandex_url(url)
        if typ is None:
            cprint(f"❌ Не удалось распознать ссылку: {url}", 'err')
            continue

        # Дополнительная валидация идентификаторов перед формированием URL API
        if typ in ('track', 'album'):
            if not (cid and id_digits_re.fullmatch(str(cid))):
                cprint(f"❌ Некорректный идентификатор: {url}", 'err')
                continue
            safe_cid = str(cid)
        elif typ == 'playlist':
            if not (cid and id_digits_re.fullmatch(str(cid)) and username and owner_re.fullmatch(str(username))):
                cprint(f"❌ Некорректные параметры плейлиста: {url}", 'err')
                continue
            safe_cid = str(cid)
        elif typ == 'iframe_playlist':
            if not (cid and id_digits_re.fullmatch(str(cid)) and username and owner_re.fullmatch(str(username))):
                cprint(f"❌ Некорректные параметры iframe-плейлиста: {url}", 'err')
                continue
            safe_cid = str(cid)
        elif typ == 'uuid_playlist':
            if not (cid and uuid_re.fullmatch(str(cid)) and username and owner_re.fullmatch(str(username))):
                cprint(f"❌ Некорректные параметры uuid-плейлиста: {url}", 'err')
                continue
            safe_cid = str(cid)
        else:
            # неизвестный тип
            cprint(f"❌ Неизвестный тип ссылки: {url}", 'err')
            continue

        try:
            if typ == 'track':
                tracks = await asyncio.to_thread(client.tracks, [safe_cid])
                if tracks and tracks[0]:
                    t = tracks[0]
                    artist = ', '.join(a.name for a in t.artists) or "Неизвестен"
                    title = t.title
                    ver = getattr(t, 'version', None) or getattr(t, 'subtitle', None)
                    if ver:
                        title = f"{title} ({ver})"
                    cover = await fetch_cover(t.cover_uri)
                    album = t.albums[0].title if t.albums else None
                    year = t.albums[0].year if t.albums else None
                    genre = t.albums[0].genre if t.albums else None
                    all_tracks.append({
                        'url': url,
                        'artist': artist,
                        'title': title,
                        'duration': t.duration_ms // 1000,
                        'track_name': f"{artist} — {title}",
                        'cover_bytes': cover,
                        'album': album,
                        'year': year,
                        'genre': genre,
                    })
                else:
                    cprint(f"❌ Трек не найден: {url}", 'err')

            elif typ == 'album':
                status, data = await api_request(
                    f"https://api.music.yandex.net/albums/{safe_cid}/with-tracks"
                )
                if status != 200 or not data:
                    cprint(f"❌ Альбом не найден: {url}", 'err')
                    continue
                alb = data['result']
                alb_title = alb.get('title', 'Неизвестный альбом')
                alb_cover = await fetch_cover(alb.get('cover_uri'))
                alb_year = alb.get('year')
                alb_genre = alb.get('genre')
                for vol in alb.get('volumes', []):
                    for tr in vol:
                        tid = tr.get('id')
                        if not tid:
                            continue
                        artist = ', '.join(a.get('name', 'Неизвестен') for a in tr.get('artists', [])) or "Неизвестен"
                        title = tr.get('title', 'Неизвестный трек')
                        ver = tr.get('version') or tr.get('subtitle')
                        if ver:
                            title = f"{title} ({ver})"
                        cover = await fetch_cover(tr.get('cover_uri')) or alb_cover
                        all_tracks.append({
                            'url': f"{base}/track/{tid}",
                            'artist': artist,
                            'title': title,
                            'duration': tr.get('duration_ms', 0) // 1000,
                            'track_name': f"{artist} — {title}",
                            'cover_bytes': cover,
                            'album': alb_title,
                            'year': alb_year,
                            'genre': alb_genre,
                        })

            elif typ in ('playlist', 'uuid_playlist', 'iframe_playlist'):
                # Пропускаем персональные подборки
                if safe_cid.startswith(('ps.', 'lk.', 'pl.')):
                    cprint(f"⚠️ Плейлист «{safe_cid}» — персональная подборка, пропущен.", 'warn')
                    continue

                # Пробуем разные endpoints
                endpoints = [f"https://api.music.yandex.net/playlists/{safe_cid}"]
                if username:
                    endpoints.append(f"https://api.music.yandex.net/users/{username}/playlists/{safe_cid}")

                success = False
                for ep in endpoints:
                    status, data = await api_request(ep)
                    if status == 403:
                        cprint(f"🔒 Плейлист приватный: {url}", 'err')
                        break
                    if status != 200 or not data or 'result' not in data:
                        continue
                    pl = data['result'].get('playlist', data['result'])
                    # Пропускаем служебные подборки
                    owner_login = pl.get('owner', {}).get('login', '')
                    if owner_login in ('yamusic', 'yandex'):
                        cprint("⚠️ Служебный плейлист пропущен.", 'warn')
                        break
                    playlist_title = pl.get('title', 'Неизвестный плейлист')
                    for item in pl.get('tracks', []):
                        tr = item.get('track')
                        if not tr:
                            continue
                        tid = tr.get('id')
                        artist = ', '.join(a.get('name', 'Неизвестен') for a in tr.get('artists', [])) or "Неизвестен"
                        title = tr.get('title', 'Неизвестный трек')
                        ver = tr.get('version') or tr.get('subtitle')
                        if ver:
                            title = f"{title} ({ver})"
                        cover = await fetch_cover(tr.get('cover_uri'))
                        alb = tr.get('albums', [{}])[0]
                        all_tracks.append({
                            'url': f"{base}/track/{tid}",
                            'artist': artist,
                            'title': title,
                            'duration': tr.get('duration_ms', 0) // 1000,
                            'track_name': f"{artist} — {title}",
                            'cover_bytes': cover,
                            'album': alb.get('title'),
                            'year': alb.get('year'),
                            'genre': alb.get('genre'),
                        })
                    success = True
                    break

                if not success and status != 403:
                    cprint(f"❌ Плейлист не найден или недоступен: {url}", 'err')

        except Exception as e:
            logger.error("Ошибка обработки ссылки %s: %s", url, e)
            cprint(f"❌ Ошибка: {e}", 'err')

    if not all_tracks:
        cprint("❌ Треки не найдены.", 'err')
    return all_tracks

# ---------- загрузка одного трека (с безопасным сохранением) ----------
async def download_track(task, cancel_event):
    tmp = Path(f"bocchi_tmp_{uuid.uuid4().hex}")
    q = user_quality
    used_q = None

    try:
        tmp.mkdir(parents=True, exist_ok=True)

        async def run(ql, path):
            cmd = [
                DOWNLOADER_PATH,
                "--token", user_token,
                "--quality", str(ql),
                "--embed-cover",
                "--cover-resolution", "original",
                "--dir", str(path),
                "--url", task['url'],
                "--path-pattern", "#artist - #title",
                "--lyrics-format", "lrc",
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=DOWNLOAD_TIMEOUT
                )
                return proc.returncode, stdout, stderr
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return -1, b'', b'Timeout'

        success = False
        qtry = q
        for attempt in range(3):
            if cancel_event.is_set():
                cprint("⏹ Загрузка отменена пользователем.", 'warn')
                return False

            ok, free_mb = check_disk_space()
            if not ok:
                if qtry > 0:
                    qtry -= 1
                    cprint(f"⚠️ Мало места ({free_mb:.1f} МБ). Понижаю качество до {QUALITY_NAMES_GENITIVE[qtry]}.", 'warn')
                    continue
                else:
                    cprint("❌ Недостаточно места даже для низкого качества.", 'err')
                    break

            code, _, stderr = await run(qtry, tmp)
            if code == 0:
                success = True
                used_q = qtry
                break
            else:
                err = stderr.decode('utf-8', errors='replace')
                logger.warning("Код возврата %d: %s", code, err[:200])
                cprint(f"❌ Ошибка загрузчика (код {code}): {err[:200]}", 'err')
                shutil.rmtree(tmp, ignore_errors=True)
                tmp.mkdir(parents=True, exist_ok=True)
                if code == -9:
                    if qtry > 0:
                        qtry -= 1
                        cprint(f"⚠️ Нехватка памяти. Понижаю качество до {QUALITY_NAMES_GENITIVE[qtry]}.", 'warn')
                        continue
                    else:
                        cprint("❌ Не хватает памяти даже на низком качестве.", 'err')
                        break
                if any(k in err.lower() for k in ['forbidden', 'blocked', '403', 'регион']):
                    cprint("❌ Трек заблокирован Яндексом.", 'err')
                    break
                if attempt == 2:
                    cprint("❌ Не удалось скачать после 3 попыток.", 'err')
                else:
                    await asyncio.sleep(5)

        if not success:
            return False

        if used_q != q:
            cprint(f"🎵 Скачан в качестве {QUALITY_NAMES[used_q]}.", 'ok')

        await asyncio.sleep(2)

        download_dir_resolved = DOWNLOAD_DIR.resolve()
        files_found = False
        for f in tmp.rglob('*'):
            if f.suffix.lower() not in ('.mp3', '.m4a'):
                continue
            files_found = True
            artist = task.get('artist', 'Неизвестен')
            title = task.get('title', f.stem)
            album = task.get('album')
            year = task.get('year')
            genre = task.get('genre')
            cover = task.get('cover_bytes')
            lyrics = None
            lrc = next(tmp.glob(f"{f.stem}.lrc"), None)
            if lrc:
                lyrics = lrc.read_text(encoding='utf-8').strip()

            # Запись метаданных (как раньше)
            try:
                if f.suffix.lower() == '.m4a':
                    audio = MP4(f)
                    audio['\xa9ART'] = [artist]
                    audio['\xa9nam'] = [title]
                    if album: audio['\xa9alb'] = [album]
                    if year: audio['\xa9day'] = [str(year)]
                    if genre: audio['\xa9gen'] = [genre]
                    audio.pop('\xa9cmt', None)
                    if lyrics: audio['\xa9lyr'] = [lyrics]
                    if cover: audio['covr'] = [MP4Cover(cover, imageformat=MP4Cover.FORMAT_JPEG)]
                    audio.save()
                else:
                    audio = MP3(f, ID3=ID3)
                    if audio.tags is None:
                        audio.add_tags()
                    easy = EasyID3(f)
                    easy['artist'] = [artist]
                    easy['title'] = [title]
                    if album: easy['album'] = [album]
                    easy.save()
                    audio.tags.add(TPE2(encoding=3, text=artist))
                    audio.tags.delall('COMM')
                    if year: audio.tags.add(TDRC(encoding=3, text=str(year)))
                    if genre: audio.tags.add(TCON(encoding=3, text=genre))
                    if lyrics: audio.tags.add(USLT(encoding=3, lang='rus', desc='Lyrics', text=lyrics))
                    if cover: audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, data=cover))
                    audio.save()
            except Exception as e:
                logger.error("Ошибка записи тегов: %s", e)

            # Безопасное имя файла: удаляем запрещённые символы и проверяем выход за пределы папки
            raw_name = f"{artist.replace(';', ',')} - {title}{f.suffix}"
            safe_name = re.sub(r'[\\/*?:"<>|]', "", raw_name)
            # Дополнительно убираем возможные переходы по директориям
            safe_name = safe_name.replace('..', '_').replace('/', '_').replace('\\', '_')
            dest = (download_dir_resolved / safe_name).resolve()
            # Проверяем, что итоговый путь остаётся внутри DOWNLOAD_DIR
            try:
                dest.relative_to(download_dir_resolved)
            except ValueError:
                cprint(f"⚠️ Некорректный путь сохранения: {dest}", 'err')
                continue
            try:
                shutil.move(str(f), dest)
                cprint(f"✅ Сохранён: {safe_name} ({dest.stat().st_size / 1024 / 1024:.2f} МБ)", 'ok')
            except Exception as e:
                logger.error("Ошибка перемещения: %s", e)
                cprint(f"❌ Не удалось сохранить файл: {e}", 'err')

        if not files_found:
            cprint("⚠️ Загрузчик не создал ни одного аудиофайла. Проверьте ссылку.", 'warn')
            logger.error("Файлы не найдены. Содержимое tmp: %s", list(tmp.rglob('*')))

        return True

    except asyncio.CancelledError:
        cprint("⏹ Загрузка прервана.", 'warn')
        return False
    except Exception as e:
        logger.error("Ошибка при загрузке трека: %s", e, exc_info=True)
        cprint(f"❌ Ошибка: {e}", 'err')
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

# ---------- команды меню ----------
async def cmd_auth():
    clear_screen()
    cprint("\n:: АВТОРИЗАЦИЯ", 'menu')
    print("1. Перейдите по ссылке:")
    print("https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41195d")
    print("2. Нажмите «Войти» или «Разрешить».")
    print("3. Скопируйте весь адрес из строки браузера и вставьте сюда.")
    raw = input("Вставьте URL: ").strip()
    token = None
    if m := re.search(r"(y0_[a-zA-Z0-9_-]+)", raw):
        token = m.group(1)
    elif m := re.search(r"access_token=([^&]+)", raw):
        token = m.group(1)
    if not token:
        cprint("❌ Токен не найден.", 'err')
        wait_for_enter()
        return
    try:
        client = await asyncio.to_thread(Client(token).init)
        login = client.account_status().account.login
        save_token(token)
        cprint(f"✅ Успешный вход как {login}!", 'ok')
    except Exception as e:
        logger.error("Ошибка токена: %s", e)
        cprint("❌ Токен недействителен.", 'err')
    wait_for_enter()

def cmd_logout():
    clear_screen()
    if not is_token_valid():
        cprint("ℹ️ Токен не установлен.", 'info')
    else:
        delete_token()
        cprint("🔓 Токен удалён.", 'ok')
    wait_for_enter()

async def cmd_set_quality():
    clear_screen()
    global user_quality
    cprint(":: КАЧЕСТВО", 'menu')
    print(f"Текущее: {QUALITY_NAMES[user_quality]}")
    print("0 - Низкое\n1 - Среднее\n2 - Высокое")
    q = input("Выберите (0/1/2): ").strip()
    if q in ('0', '1', '2'):
        user_quality = int(q)
        cprint(f"✅ Изменено на {QUALITY_NAMES[user_quality]}.", 'ok')
    else:
        cprint("Неверный ввод.", 'warn')
    wait_for_enter()

async def cmd_start_download():
    clear_screen()
    if not is_token_valid():
        cprint("❌ Сначала авторизуйтесь (пункт 1).", 'err')
        wait_for_enter()
        return

    cprint(":: ВВОД ССЫЛОК", 'menu')
    cprint("Вставляйте ссылки (по одной). Пустая строка — завершить.", 'info')
    links = []
    while True:
        try:
            line = sys.stdin.readline().strip()
        except KeyboardInterrupt:
            cprint("\nВвод отменён.", 'warn')
            wait_for_enter()
            return
        if not line:
            break
        # Простейшая проверка, что это ссылка Яндекса
        if re.search(r'yandex\.[a-z]{2,3}/', line, re.I) or 'iframe' in line:
            links.append(line)
        else:
            cprint("Пропущено (не ссылка Яндекс.Музыки).", 'warn')

    if not links:
        cprint("Ссылки не введены.", 'warn')
        wait_for_enter()
        return

    tracks = await collect_tracks_from_links(links[:MAX_LINKS])
    if not tracks:
        wait_for_enter()
        return

    total = len(tracks)
    cprint(f"📥 Найдено {get_plural_tracks(total)}. Начинаю загрузку...", 'ok')

    clear_screen()
    cprint(":: РЕЖИМ ЗАГРУЗКИ", 'menu')
    print("   Для отмены нажмите 0 (без Enter)\n")

    cancel_event = asyncio.Event()

    async def cancel_listener():
        loop = asyncio.get_event_loop()
        while not cancel_event.is_set():
            try:
                ch = await loop.run_in_executor(None, getch)
                if ch == '0':
                    cancel_event.set()
                    break
            except Exception:
                pass
            await asyncio.sleep(0.05)

    listener_task = asyncio.create_task(cancel_listener())

    success_count = 0
    for idx, track in enumerate(tracks, 1):
        if cancel_event.is_set():
            cprint("\n🛑 Загрузка отменена пользователем.", 'warn')
            break

        print(f"\r   ▶ [{idx}/{total}] {track['track_name']}                    ", end='', flush=True)
        if await download_track(track, cancel_event):
            success_count += 1
        await asyncio.sleep(TRACK_DELAY_SECONDS)

    listener_task.cancel()
    try:
        await listener_task
    except asyncio.CancelledError:
        pass

    print()
    if cancel_event.is_set():
        cprint(f"Загрузка прервана. Успешно загружено: {success_count} из {total}.", 'warn')
    else:
        cprint(f"🎸 Загрузка завершена! Успешно загружено: {success_count} из {total}.", 'ok')
    wait_for_enter()

def cmd_exit():
    clear_screen()
    cprint("👋 Завершение работы...", 'info')
    sys.exit(0)

def print_menu():
    clear_screen()
    border = "  ----------------------------------------"
    header = "  BOCCHI DOWNLOADER (CLI Edition)"
    token_stat = "✅ активен" if is_token_valid() else "❌ неактивен"
    print()
    cprint(header, 'menu')
    print(border)
    print()
    print("  :: СЕРВИС")
    print(f"     1. 🔑 Установить / обновить токен   [{token_stat}]")
    print("     2. ❌ Удалить токен")
    print()
    print("  :: НАСТРОЙКИ")
    print(f"     3. ⚙️  Качество загрузки         [{QUALITY_NAMES[user_quality]}]")
    print()
    print("  :: ЗАГРУЗКА")
    print("     4. 🎵 Начать загрузку (ввести ссылки)")
    print()
    print("  :: СИСТЕМА")
    print("     5. 🚪 Выход")
    print()
    print(border)
    print()

async def main_async():
    load_token()
    while True:
        print_menu()
        try:
            choice = input("   Выберите опцию (1-5): ").strip()
        except (EOFError, KeyboardInterrupt):
            cmd_exit()
        if choice == '1':
            await cmd_auth()
        elif choice == '2':
            cmd_logout()
        elif choice == '3':
            await cmd_set_quality()
        elif choice == '4':
            await cmd_start_download()
        elif choice == '5':
            cmd_exit()
        else:
            cprint("Неверный ввод.", 'warn')
            wait_for_enter()

def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        cmd_exit()

if __name__ == "__main__":
    main()
