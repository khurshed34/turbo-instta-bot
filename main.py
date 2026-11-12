
import os
import re
import sqlite3
import shutil
import logging
import asyncio
import tempfile
import requests

from urllib.parse import urlparse
from datetime import datetime, timezone

from instaloader import Instaloader, Post

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# =====================================
# SETTINGS
# =====================================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

DB_FILE = "bot_data.sqlite3"

MAX_SIZE = 49 * 1024 * 1024
MAX_PHOTO_SIZE = 10 * 1024 * 1024

INSTAGRAM_HOSTS = {
    "instagram.com",
    "www.instagram.com",
    "m.instagram.com",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
    ),
    "Referer": "https://www.instagram.com/",
}

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

# =====================================
# LANGUAGES
# =====================================

TEXTS = {
    "tg": {
        "welcome": (
            "👋 Хуш омадӣ ба Instagram Downloader PRO!\n\n"
            "📸 Post — акс ва видео\n"
            "🎬 Reels — видео\n"
            "🖼 Carousel — ҳамаи аксҳо ва видеоҳо\n"
            "📖 Story — бо дастрасии иҷозатдодашуда\n\n"
            "🔗 Пайванди Instagram-ро фирист."
        ),
        "send_link": "🔗 Пайванди Instagram-ро фирист.",
        "invalid": "❌ Пайванди Instagram нодуруст аст.",
        "story": (
            "📖 Instagram Story муайян шуд.\n\n"
            "Барои Story-и аккаунтҳои дигар дастрасии "
            "умумии расмӣ вуҷуд надорад.\n"
            "Ин бот ҳоло танҳо Post, Reels ва Carousel-ро "
            "зеркашӣ мекунад."
        ),
        "processing": "⏳ Пайванд коркард шуда истодааст...",
        "sending": "📤 Ирсоли файлҳо...",
        "success": "✅ Боргирӣ анҷом ёфт!\n\n📦 Файлҳо: {}",
        "not_found": "❌ Ягон файл ёфт нашуд.",
        "error": "❌ Боргирӣ иҷро нашуд.\n\nСабаб: {}",
        "too_big": "❌ Файл аз 49 MB зиёд аст.",
        "private": (
            "❌ Post дастрас нест ё аккаунт хусусӣ мебошад."
        ),
        "language": "🌐 Забонро интихоб кун:",
        "language_saved": "✅ Забон иваз карда шуд.",
        "admin_denied": "❌ Ин бахш танҳо барои Admin аст.",
        "admin_title": "🛠 Панели Admin",
        "stats": (
            "📊 ОМОРИ БОТ\n\n"
            "👥 Истифодабарандагон: {}\n"
            "⬇️ Боргириҳои муваффақ: {}\n"
            "❌ Боргириҳои номуваффақ: {}\n"
            "📦 Ҳамаи дархостҳо: {}"
        ),
        "admin_button": "📊 Омори бот",
        "back": "⬅️ Бозгашт",
        "menu": "🏠 Меню",
    },

    "ru": {
        "welcome": (
            "👋 Добро пожаловать в Instagram Downloader PRO!\n\n"
            "📸 Post — фото и видео\n"
            "🎬 Reels — видео\n"
            "🖼 Carousel — все фото и видео\n"
            "📖 Story — при наличии разрешённого доступа\n\n"
            "🔗 Отправьте ссылку Instagram."
        ),
        "send_link": "🔗 Отправьте ссылку Instagram.",
        "invalid": "❌ Неверная ссылка Instagram.",
        "story": (
            "📖 Обнаружена Instagram Story.\n\n"
            "Общедоступного официального доступа к Stories "
            "других аккаунтов нет.\n"
            "Сейчас бот поддерживает Post, Reels и Carousel."
        ),
        "processing": "⏳ Обрабатываю ссылку...",
        "sending": "📤 Отправляю файлы...",
        "success": "✅ Загрузка завершена!\n\n📦 Файлов: {}",
        "not_found": "❌ Файлы не найдены.",
        "error": "❌ Не удалось загрузить.\n\nПричина: {}",
        "too_big": "❌ Файл превышает 49 MB.",
        "private": (
            "❌ Публикация недоступна или аккаунт закрытый."
        ),
        "language": "🌐 Выберите язык:",
        "language_saved": "✅ Язык изменён.",
        "admin_denied": "❌ Этот раздел доступен только Admin.",
        "admin_title": "🛠 Панель Admin",
        "stats": (
            "📊 СТАТИСТИКА БОТА\n\n"
            "👥 Пользователи: {}\n"
            "⬇️ Успешные загрузки: {}\n"
            "❌ Неудачные загрузки: {}\n"
            "📦 Всего запросов: {}"
        ),
        "admin_button": "📊 Статистика бота",
        "back": "⬅️ Назад",
        "menu": "🏠 Меню",
    },
}

# =====================================
# DATABASE
# =====================================

def db_connect():

    return sqlite3.connect(DB_FILE)


def init_db():

    with db_connect() as db:

        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                language TEXT DEFAULT 'tg',
                joined_at TEXT
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                status TEXT,
                created_at TEXT
            )
        """)

        db.commit()


def register_user(user):

    with db_connect() as db:

        db.execute("""
            INSERT OR IGNORE INTO users
            (user_id, username, first_name, language, joined_at)
            VALUES (?, ?, ?, 'tg', ?)
        """, (
            user.id,
            user.username,
            user.first_name,
            datetime.now(timezone.utc).isoformat(),
        ))

        db.execute("""
            UPDATE users
            SET username = ?, first_name = ?
            WHERE user_id = ?
        """, (
            user.username,
            user.first_name,
            user.id,
        ))

        db.commit()


def get_language(user_id):

    with db_connect() as db:

        result = db.execute(
            "SELECT language FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    if result and result[0] in TEXTS:
        return result[0]

    return "tg"


def set_language(user_id, language):

    if language not in TEXTS:
        return

    with db_connect() as db:

        db.execute(
            "UPDATE users SET language = ? WHERE user_id = ?",
            (language, user_id),
        )

        db.commit()


def record_download(user_id, status):

    with db_connect() as db:

        db.execute("""
            INSERT INTO downloads
            (user_id, status, created_at)
            VALUES (?, ?, ?)
        """, (
            user_id,
            status,
            datetime.now(timezone.utc).isoformat(),
        ))

        db.commit()


def get_statistics():

    with db_connect() as db:

        users = db.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        success = db.execute(
            "SELECT COUNT(*) FROM downloads WHERE status = 'success'"
        ).fetchone()[0]

        failed = db.execute(
            "SELECT COUNT(*) FROM downloads WHERE status = 'failed'"
        ).fetchone()[0]

    return users, success, failed, success + failed


# =====================================
# KEYBOARDS
# =====================================

def main_keyboard(language):

    if language == "ru":

        return ReplyKeyboardMarkup(
            [
                [KeyboardButton("📸 Instagram")],
                [KeyboardButton("🌐 Язык / Забон")],
            ],
            resize_keyboard=True,
        )

    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📸 Instagram")],
            [KeyboardButton("🌐 Забон / Язык")],
        ],
        resize_keyboard=True,
    )


def language_keyboard():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🇹🇯 Тоҷикӣ",
                callback_data="lang_tg",
            ),
            InlineKeyboardButton(
                "🇷🇺 Русский",
                callback_data="lang_ru",
            ),
        ]
    ])


# =====================================
# START
# =====================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    register_user(user)

    language = get_language(user.id)

    await update.message.reply_text(
        TEXTS[language]["welcome"],
        reply_markup=main_keyboard(language),
    )


# =====================================
# LANGUAGE
# =====================================

async def language_command(update, context):

    user = update.effective_user

    register_user(user)

    language = get_language(user.id)

    await update.message.reply_text(
        TEXTS[language]["language"],
        reply_markup=language_keyboard(),
    )


async def callbacks(update, context):

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    if query.data.startswith("lang_"):

        language = query.data.replace("lang_", "")

        if language not in TEXTS:
            return

        register_user(query.from_user)

        set_language(user_id, language)

        await query.edit_message_text(
            TEXTS[language]["language_saved"]
        )

        await query.message.reply_text(
            TEXTS[language]["welcome"],
            reply_markup=main_keyboard(language),
        )

        return

    if query.data == "admin_stats":

        if user_id != ADMIN_ID or ADMIN_ID == 0:
            await query.edit_message_text(
                "❌ Access denied."
            )
            return

        language = get_language(user_id)

        users, success, failed, total = get_statistics()

        await query.edit_message_text(
            TEXTS[language]["stats"].format(
                users,
                success,
                failed,
                total,
            ),
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        TEXTS[language]["back"],
                        callback_data="admin_back",
                    )
                ]
            ]),
        )

        return

    if query.data == "admin_back":

        if user_id != ADMIN_ID or ADMIN_ID == 0:
            return

        language = get_language(user_id)

        await query.edit_message_text(
            TEXTS[language]["admin_title"],
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        TEXTS[language]["admin_button"],
                        callback_data="admin_stats",
                    )
                ]
            ]),
        )


# =====================================
# ADMIN PANEL
# =====================================

async def admin_command(update, context):

    user_id = update.effective_user.id

    if ADMIN_ID == 0 or user_id != ADMIN_ID:

        language = get_language(user_id)

        await update.message.reply_text(
            TEXTS[language]["admin_denied"]
        )

        return

    language = get_language(user_id)

    await update.message.reply_text(
        TEXTS[language]["admin_title"],
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    TEXTS[language]["admin_button"],
                    callback_data="admin_stats",
                )
            ]
        ]),
    )


# =====================================
# INSTAGRAM URL CHECK
# =====================================

def extract_instagram_url(text):

    match = re.search(
        r"https?://[^\s]+",
        text,
        re.IGNORECASE,
    )

    if not match:
        raise ValueError("invalid")

    url = match.group(0).rstrip(".,!?)]}")

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError("invalid")

    host = (parsed.hostname or "").lower()

    if host not in INSTAGRAM_HOSTS:
        raise ValueError("invalid")

    parts = [
        p for p in parsed.path.strip("/").split("/")
        if p
    ]

    if not parts:
        raise ValueError("invalid")

    if parts[0].lower() == "stories":
        raise RuntimeError("story")

    if parts[0].lower() not in ("p", "reel", "reels", "tv"):
        raise ValueError("invalid")

    if len(parts) < 2:
        raise ValueError("invalid")

    shortcode = parts[1]

    if not re.fullmatch(r"[A-Za-z0-9_-]+", shortcode):
        raise ValueError("invalid")

    return url, shortcode


# =====================================
# DOWNLOAD MEDIA
# =====================================

def download_file(url, path):

    total = 0

    with requests.get(
        url,
        headers=HEADERS,
        stream=True,
        timeout=(20, 60),
    ) as response:

        response.raise_for_status()

        length = response.headers.get("Content-Length")

        if length and int(length) > MAX_SIZE:
            raise ValueError("too_big")

        with open(path, "wb") as file:

            for chunk in response.iter_content(
                chunk_size=256 * 1024
            ):

                if not chunk:
                    continue

                total += len(chunk)

                if total > MAX_SIZE:
                    raise ValueError("too_big")

                file.write(chunk)

    if total == 0:
        raise ValueError("empty")

    return path


# =====================================
# INSTAGRAM DOWNLOADER
# =====================================

def download_instagram(url, folder):

    _, shortcode = extract_instagram_url(url)

    loader = Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        save_metadata=False,
        compress_json=False,
        quiet=True,
    )

    try:

        post = Post.from_shortcode(
            loader.context,
            shortcode,
        )

    except Exception as error:

        raise RuntimeError("private") from error

    results = []

    # CAROUSEL

    if post.typename == "GraphSidecar":

        for index, node in enumerate(
            post.get_sidecar_nodes(),
            start=1,
        ):

            if node.is_video:

                media_url = node.video_url
                extension = ".mp4"
                media_type = "video"

            else:

                media_url = node.display_url
                extension = ".jpg"
                media_type = "photo"

            filename = os.path.join(
                folder,
                f"instagram_{index}{extension}",
            )

            download_file(media_url, filename)

            results.append((filename, media_type))

    # PHOTO

    elif not post.is_video:

        filename = os.path.join(
            folder,
            "instagram_photo.jpg",
        )

        download_file(post.url, filename)

        results.append((filename, "photo"))

    # VIDEO / REELS

    else:

        filename = os.path.join(
            folder,
            "instagram_video.mp4",
        )

        download_file(post.video_url, filename)

        results.append((filename, "video"))

    if not results:
        raise ValueError("empty")

    return results


# =====================================
# SEND FILES
# =====================================

async def send_files(update, msg, files, language):

    if not files:

        await msg.edit_text(
            TEXTS[language]["not_found"]
        )

        return 0

    await msg.edit_text(
        TEXTS[language]["sending"]
    )

    sent = 0

    for filename, media_type in files:

        if not os.path.isfile(filename):
            continue

        size = os.path.getsize(filename)

        if size == 0 or size > MAX_SIZE:
            continue

        try:

            with open(filename, "rb") as media:

                if media_type == "photo" and size <= MAX_PHOTO_SIZE:

                    await update.message.reply_photo(
                        photo=media
                    )

                elif media_type == "video":

                    await update.message.reply_video(
                        video=media,
                        supports_streaming=True,
                    )

                else:

                    await update.message.reply_document(
                        document=media
                    )

            sent += 1

        except Exception:

            logger.exception("Telegram file sending failed")

            try:

                with open(filename, "rb") as media:

                    await update.message.reply_document(
                        document=media
                    )

                sent += 1

            except Exception:

                logger.exception("Document sending failed")

    await msg.edit_text(
        TEXTS[language]["success"].format(sent)
        if sent
        else TEXTS[language]["not_found"]
    )

    return sent


# =====================================
# MESSAGE HANDLER
# =====================================

async def handle_text(update, context):

    if not update.message or not update.message.text:
        return

    user = update.effective_user

    register_user(user)

    language = get_language(user.id)

    text = update.message.text.strip()

    if text in (
        "🌐 Забон / Язык",
        "🌐 Язык / Забон",
    ):

        await language_command(update, context)
        return

    if text == "📸 Instagram":

        await update.message.reply_text(
            TEXTS[language]["send_link"]
        )

        return

    try:

        url, _ = extract_instagram_url(text)

    except RuntimeError as error:

        if str(error) == "story":

            await update.message.reply_text(
                TEXTS[language]["story"]
            )

            return

        await update.message.reply_text(
            TEXTS[language]["invalid"]
        )

        return

    except ValueError:

        await update.message.reply_text(
            TEXTS[language]["invalid"]
        )

        return

    msg = await update.message.reply_text(
        TEXTS[language]["processing"]
    )

    folder = tempfile.mkdtemp(
        prefix="instagram_"
    )

    success = False

    try:

        loop = asyncio.get_running_loop()

        files = await loop.run_in_executor(
            None,
            download_instagram,
            url,
            folder,
        )

        sent = await send_files(
            update,
            msg,
            files,
            language,
        )

        success = sent > 0

    except Exception as error:

        logger.exception(
            "Instagram download failed"
        )

        error_text = str(error)

        if error_text == "private":
            reason = TEXTS[language]["private"]

        elif error_text == "too_big":
            reason = TEXTS[language]["too_big"]

        elif error_text == "empty":
            reason = TEXTS[language]["not_found"]

        else:
            reason = (
                "Instagram дастрасиро маҳдуд кард ё "
                "мавод дастрас нест."
                if language == "tg"
                else
                "Instagram ограничил доступ или "
                "материал недоступен."
            )

        await msg.edit_text(
            TEXTS[language]["error"].format(reason)
        )

    finally:

        record_download(
            user.id,
            "success" if success else "failed",
        )

        shutil.rmtree(
            folder,
            ignore_errors=True,
        )


# =====================================
# MAIN
# =====================================

def main():

    if not TOKEN:
        raise RuntimeError(
            "BOT_TOKEN дар GitHub Secrets нест!"
        )

    init_db()

    app = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("admin", admin_command)
    )

    app.add_handler(
        CommandHandler("language", language_command)
    )

    app.add_handler(
        CallbackQueryHandler(callbacks)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text,
        )
    )

    logger.info(
        "Instagram Downloader PRO started!"
    )

    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
