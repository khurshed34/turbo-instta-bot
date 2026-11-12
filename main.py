
import os
import re
import shutil
import logging
import asyncio
import tempfile
import requests

from urllib.parse import urlparse
from instaloader import Instaloader, Post

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =====================================
# SETTINGS
# =====================================

TOKEN = os.getenv("BOT_TOKEN")

MAX_FILE_SIZE = 49 * 1024 * 1024
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

BTN_INSTAGRAM = "📸 Instagram"

MAIN_MENU = ReplyKeyboardMarkup(
    [[KeyboardButton(BTN_INSTAGRAM)]],
    resize_keyboard=True,
)

# =====================================
# START
# =====================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "👋 Салом! Ман Instagram Downloader ҳастам.\n\n"
        "📸 Ман метавонам зеркашӣ кунам:\n\n"
        "• Post\n"
        "• Reels\n"
        "• Carousel\n\n"
        "🔗 Пайванди Instagram-ро фирист.\n\n"
        "⚠️ Танҳо маводеро истифода бар, ки "
        "ҳуқуқи зеркашӣ ё истифодаашро дорӣ.",
        reply_markup=MAIN_MENU,
    )


# =====================================
# CHECK INSTAGRAM URL
# =====================================

def extract_instagram_url(text):

    match = re.search(
        r"https?://[^\s]+",
        text,
        re.IGNORECASE,
    )

    if not match:
        raise ValueError("Пайванди Instagram ёфт нашуд.")

    url = match.group(0).rstrip(".,!?)]}")

    parsed = urlparse(url)

    host = (parsed.hostname or "").lower()

    if parsed.scheme not in ("http", "https"):
        raise ValueError("Пайванд нодуруст аст.")

    if host not in INSTAGRAM_HOSTS:
        raise ValueError("Ин пайванди Instagram нест.")

    parts = [
        item for item in parsed.path.strip("/").split("/")
        if item
    ]

    if not parts:
        raise ValueError("Пайванди Instagram нодуруст аст.")

    if parts[0].lower() == "stories":
        raise ValueError(
            "📖 Ин пайванди Instagram Story аст.\n\n"
            "Ин версия танҳо Post, Reels ва Carousel-ро "
            "дастгирӣ мекунад."
        )

    if parts[0].lower() not in ("p", "reel", "reels", "tv"):
        raise ValueError(
            "❌ Навъи пайванд дастгирӣ намешавад.\n\n"
            "Post, Reels ё Carousel фирист."
        )

    if len(parts) < 2:
        raise ValueError("Коди Post ё Reels ёфт нашуд.")

    shortcode = parts[1]

    if not re.fullmatch(r"[A-Za-z0-9_-]+", shortcode):
        raise ValueError("Коди Instagram нодуруст аст.")

    return url, shortcode


# =====================================
# DOWNLOAD FILE
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

        content_length = response.headers.get(
            "Content-Length"
        )

        if content_length:
            if int(content_length) > MAX_FILE_SIZE:
                raise ValueError(
                    "Файл аз 49 MB зиёд аст."
                )

        with open(path, "wb") as file:

            for chunk in response.iter_content(
                chunk_size=256 * 1024
            ):

                if not chunk:
                    continue

                total += len(chunk)

                if total > MAX_FILE_SIZE:
                    raise ValueError(
                        "Файл аз 49 MB зиёд аст."
                    )

                file.write(chunk)

    if total == 0:
        raise ValueError("Файли зеркашидашуда холӣ аст.")

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

        raise RuntimeError(
            "Instagram маълумоти ин Post-ро дастрас накард. "
            "Шояд Post хусусӣ, нестшуда ё маҳдуд бошад."
        ) from error

    results = []

    # =================================
    # CAROUSEL
    # =================================

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

            download_file(
                media_url,
                filename,
            )

            results.append(
                (filename, media_type)
            )

    # =================================
    # SINGLE PHOTO
    # =================================

    elif not post.is_video:

        filename = os.path.join(
            folder,
            "instagram_photo.jpg",
        )

        download_file(
            post.url,
            filename,
        )

        results.append(
            (filename, "photo")
        )

    # =================================
    # REELS / VIDEO
    # =================================

    else:

        filename = os.path.join(
            folder,
            "instagram_video.mp4",
        )

        download_file(
            post.video_url,
            filename,
        )

        results.append(
            (filename, "video")
        )

    if not results:
        raise ValueError("Ягон файл ёфт нашуд.")

    return results


# =====================================
# SEND FILES TO TELEGRAM
# =====================================

async def send_files(update, msg, files):

    if not files:

        await msg.edit_text(
            "❌ Ягон файл ёфт нашуд."
        )

        return

    await msg.edit_text(
        f"📤 Ирсоли {len(files)} файл..."
    )

    sent = 0

    for filename, media_type in files:

        if not os.path.isfile(filename):
            continue

        size = os.path.getsize(filename)

        if size == 0 or size > MAX_FILE_SIZE:
            continue

        with open(filename, "rb") as media:

            if (
                media_type == "photo"
                and size <= MAX_PHOTO_SIZE
            ):

                await update.message.reply_photo(
                    photo=media,
                )

            elif media_type == "video":

                await update.message.reply_video(
                    video=media,
                    supports_streaming=True,
                )

            else:

                await update.message.reply_document(
                    document=media,
                )

        sent += 1

    if sent == 0:

        await msg.edit_text(
            "❌ Файл ба Telegram фиристода нашуд."
        )

        return

    await msg.edit_text(
        "✅ Зеркашӣ анҷом ёфт!\n\n"
        f"📦 Файлҳои фиристодашуда: {sent}"
    )


# =====================================
# ERROR HANDLER
# =====================================

def friendly_error(error):

    message = str(error)

    if isinstance(error, ValueError):
        return message

    if "401" in message or "403" in message:
        return (
            "❌ Instagram дастрасиро рад кард.\n"
            "Шояд Post маҳдуд ё хусусӣ бошад."
        )

    if "404" in message:
        return "❌ Post ё Reels ёфт нашуд."

    if "429" in message:
        return (
            "❌ Instagram дархостҳоро маҳдуд кард. "
            "Баъдтар аз нав санҷ."
        )

    return (
        "❌ Боргирӣ иҷро нашуд.\n"
        "Instagram метавонад дастрасиро маҳдуд карда бошад."
    )


# =====================================
# MESSAGE HANDLER
# =====================================

async def handle_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    if text == BTN_INSTAGRAM:

        await update.message.reply_text(
            "📸 Пайванди Instagram-ро фирист.\n\n"
            "Post, Reels ё Carousel."
        )

        return

    # CHECK LINK

    try:

        url, _ = extract_instagram_url(text)

    except ValueError as error:

        await update.message.reply_text(
            "❌ " + str(error)
        )

        return

    # PROCESSING

    msg = await update.message.reply_text(
        "⏳ Instagram пайванд санҷида мешавад..."
    )

    folder = tempfile.mkdtemp(
        prefix="instagram_"
    )

    try:

        loop = asyncio.get_running_loop()

        files = await loop.run_in_executor(
            None,
            download_instagram,
            url,
            folder,
        )

        await send_files(
            update,
            msg,
            files,
        )

    except Exception as error:

        logger.exception(
            "Instagram download failed"
        )

        try:

            await msg.edit_text(
                "❌ Боргирӣ иҷро нашуд.\n\n"
                "Сабаб: " + friendly_error(error)
            )

        except Exception:
            logger.exception(
                "Could not send error message"
            )

    finally:

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

    app = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text,
        )
    )

    logger.info(
        "Instagram Downloader started successfully"
    )

    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
