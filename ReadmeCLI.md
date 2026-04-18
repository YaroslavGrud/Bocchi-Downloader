# Bocchi Downloader — автономный пакет для Android
Инструмент для скачивания музыки с Яндекс.Музыки, упакованный в полностью автономный пакет.  
Достаточно один раз собрать архив на устройстве с интернетом, а затем развернуть его на любом Android‑устройстве **без доступа к сети**.

[![Platform](https://img.shields.io/badge/Platform-Android-green)](https://www.android.com)
[![Termux](https://img.shields.io/badge/Termux-Required-blue)](https://termux.com)
[![Arch](https://img.shields.io/badge/Arch-aarch64%20%7C%20armhf-blue)](https://github.com/YaroslavGrud/Bocchi-Downloader)
[![Offline](https://img.shields.io/badge/Offline-Ready-success)](https://github.com/YaroslavGrud/Bocchi-Downloader)
[![Size](https://img.shields.io/badge/Size-4_GB-orange)](https://github.com/YaroslavGrud/Bocchi-Downloader)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)

## 📦 Что внутри?

- **Termux** с предустановленным `proot-distro`
- **Ubuntu** (rootfs для вашей архитектуры `aarch64` / `armhf`)
- **Python 3** + виртуальное окружение
- **FFmpeg**, **git**, **wget** и все зависимости
- Сам скрипт **Bocchi Downloader** (`bocchi_bot_CLI.py`)
- Лаунчер `run_bocchi.sh`

## ⚙️ Требования

- **≈4 ГБ** свободного места для сборки и восстановления

### Для сборки (один раз)
- Android‑устройство с **интернетом**
- Установленный [Termux](https://play.google.com/store/apps/details?id=com.termux&pcampaignid=web_share)

### Для восстановления (офлайн)
- Android‑устройство (любая архитектура, поддерживаемая Termux)
- Установленный Termux (можно из `.apk` без интернета)
- Файл архива `termux-native-bocchi.tar.gz` (полученный после сборки)

## 🛠️ Сборка офлайн‑пакета

Выполните **одну** команду в Termux на устройстве с интернетом.  
Она скачает Ubuntu, установит все зависимости, создаст правильный лаунчер и упакует всё в архив.

```bash
set +H && termux-setup-storage && pkg update -y && pkg upgrade -y && pkg install -y proot-distro wget tar && ARCH=$(uname -m) && if [ "$ARCH" = "aarch64" ]; then ROOTFS_ARCH="aarch64"; elif [ "$ARCH" = "armv7l" ] || [ "$ARCH" = "armv8l" ]; then ROOTFS_ARCH="armhf"; else echo "Unsupported architecture: $ARCH"; exit 1; fi && ROOTFS_URL="https://github.com/termux/proot-distro/releases/download/v4.18.0/ubuntu-noble-${ROOTFS_ARCH}-pd-v4.18.0.tar.xz" && mkdir -p $PREFIX/var/lib/proot-distro/dlcache && echo "📥 Скачивание Ubuntu rootfs для ${ROOTFS_ARCH}..." && wget -O $PREFIX/var/lib/proot-distro/dlcache/ubuntu-rootfs.tar.xz $ROOTFS_URL && yes | proot-distro remove ubuntu 2>/dev/null || true && proot-distro reset ubuntu 2>/dev/null || true && proot-distro install ubuntu && proot-distro login ubuntu -- bash -c "apt update && apt upgrade -y && apt install -y python3 python3-pip python3-venv ffmpeg git wget && mkdir -p /root/bocchi_bundle && cd /root/bocchi_bundle && python3 -m venv bocchi_env && bocchi_env/bin/pip install https://github.com/llistochek/yandex-music-downloader/archive/main.zip aiohttp mutagen yandex-music colorama setuptools wheel && wget -O bocchi_bot_CLI.py https://raw.githubusercontent.com/YaroslavGrud/Bocchi-Downloader/Yaroslav_grud/Bocchi_Downloader/bocchi_bot_CLI.py && echo 'IyEvYmluL2Jhc2gKRElSPSIkKGNkICIkKGRpcm5hbWUgIiQwIikiICYmIHB3ZCkiCnNvdXJjZSAiJERJUi9ib2NjaGlfZW52L2Jpbi9hY3RpdmF0ZSIKZXhlYyBweXRob24gIiRESVIvYm9jY2hpX2JvdF9DTEkucHkiICIkQCIK' | base64 -d > run_bocchi.sh && chmod +x run_bocchi.sh" && proot-distro backup ubuntu --output $HOME/ubuntu-backup.tar.gz && cd /data/data/com.termux/files && tar -czvf /sdcard/Download/termux-native-bocchi.tar.gz ./usr ./home && set -H && echo "✅ Готово! Архив: /sdcard/Download/termux-native-bocchi.tar.gz"
```

**⏱️ Время сборки:** 15–30 минут (зависит от скорости интернета и процессора).  
**💾 Размер архива:** ≈ 1.5–2 ГБ.

После завершения в папке `/sdcard/Download/` появится файл `termux-native-bocchi.tar.gz`.  
**Сохраните его — это ваш полностью автономный установщик.**

## ♻️ Восстановление на новом устройстве (без интернета)

1. **Установите Termux** из `.apk`‑файла (можно перенести на телефон любым способом).
2. **Скопируйте файл** `termux-native-bocchi.tar.gz` в папку `/sdcard/Download/`.
3. **Выполните в Termux** команду восстановления:

```bash
printf '\033[1;36m🚀 Bocchi Downloader — восстановление\033[0m\n' && termux-setup-storage 2>/dev/null && cd /data/data/com.termux/files && printf '\033[1;33m📦 Распаковка данных...\033[0m\n' && tar -xzf /sdcard/Download/termux-native-bocchi.tar.gz 2>/dev/null && printf '\033[1;33m🔄 Восстановление Ubuntu...\033[0m\n' && proot-distro restore ~/ubuntu-backup.tar.gz 2>&1 | grep -v "Warning" && printf '\033[1;32m✅ Запуск загрузчика!\033[0m\n' && proot-distro login ubuntu -- /root/bocchi_bundle/run_bocchi.sh
```
**⏱️ Время восстановления:** 2–5 минут.  
**💾 Размер:** ≈ 2.5 ГБ.

После процесса распаковки автоматически запустится Bocchi Downloader.  
Загруженные файлы сохраняются в `Downloads/BocchiDownloads`

> [!TIP]
>
> Чтобы не вводить длинную команду каждый раз когда перезапускаете загрузчик, создайте **алиас**:
>
> ```bash
> echo "alias bocchi='proot-distro login ubuntu -- /root/bocchi_bundle/run_bocchi.sh'" >> ~/.bashrc && source ~/.bashrc
> ```
>
> Теперь достаточно набрать `bocchi` и нажать Enter — загрузчик запустится.

## 🧹 Удаление

Если нужно полностью удалить офлайн‑пакет и освободить место:

```bash
proot-distro remove ubuntu && rm -rf /data/data/com.termux/files/usr/var/lib/proot-distro/dlcache/* && rm -f ~/ubuntu-backup.tar.gz && rm -f /sdcard/Download/termux-native-bocchi.tar.gz
```

Termux вернётся в исходное состояние.

> [!IMPORTANT]
> ### Где взять токен?
>
> 1.  Перейди по [ссылке](https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41195d)
> 2.  Нажми «Войти» или «Разрешить».
> 3.  Страница может стать пустой — это нормально!
> 4.  Токен будет между `access_token=` и `&token_type`
>
> ### Почему архив такой большой?
> Внутри находится полноценная Ubuntu + Python + FFmpeg + все зависимости. Это необходимо для полной автономности.
>
> ### Можно ли перенести архив на другой телефон с другой архитектурой?
> Да, если использовалась сборка **с эмуляцией x86_64**. В данной версии сборка **нативная** — она привязана к архитектуре (`aarch64` или `armhf`). Для переноса между разными архитектурами потребуется собрать пакет с QEMU (см. расширенную документацию).
>
> ### Что делать, если при запуске появляется ошибка «event not found»?
> Используйте команды без восклицательных знаков или с `set +H`, как указано в инструкции.

## 📄 Лицензия

Проект распространяется под лицензией MIT.  
Используемые компоненты:  
- [Termux](https://github.com/termux/termux-app) (GPLv3)  
- [proot-distro](https://github.com/termux/proot-distro) (GPLv3)  
- [yandex-music-downloader](https://github.com/llistochek/yandex-music-downloader) (MIT)  
- [Bocchi Downloader](https://github.com/YaroslavGrud/Bocchi-Downloader) (MIT)
