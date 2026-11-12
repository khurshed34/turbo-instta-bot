
import os
import re
import shutil
import logging
import asyncio
import tempfile
import requests

import instaloader
import yt_dlp

from urllib.parse import urlparse
from telegram import Update
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

INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")

MAX_SIZE = 49 * 1024 * 1024
MAX_PHOTO_SIZE = 10 * 1024 * 1024

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
    )
}

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)


# =====================================
# START
# =====================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "👋 Салом! Ман TurboInstta ҳастам.\n\n"
        "🔗 Пайванди Instagram-ро фирист:\n\n"
        "🎬 Reels ва видео\n"
        "📸 Сурат\n"
        "📚 Carousel\n"
        "📲 Instagram Stories\n\n"
        "⚠️ Танҳо маводи дастрас ва иҷозатдодашуда."
    )


# =====================================
# DOWNLOAD DIRECT FILE
# =====================================

def download_file(url, path):

    response = requests.get(
        url,
        headers=HEADERS,
        stream=True,
        timeout=40
    )

    response.raise_for_status()

    total = 0

    with open(path, "wb") as f:

        for chunk in response.iter_content(1024 * 256):

            if not chunk:
                continue

            total += len(chunk)

            if total > MAX_SIZE:
                raise ValueError(
                    "Андозаи файл аз 49 MB зиёд аст."
                )

            f.write(chunk)

    return path


# =====================================
# INSTAGRAM LOGIN
# =====================================

def create_instagram_loader(login=False):

    loader = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        save_metadata=False,
        compress_json=False,
        quiet=True
    )

    if login:

        if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
            raise ValueError(
                "INSTAGRAM_USERNAME ё INSTAGRAM_PASSWORD "
                "дар GitHub Secrets мавҷуд нест."
            )

        loader.login(
            INSTAGRAM_USERNAME,
            INSTAGRAM_PASSWORD
        )

    return loader


# =====================================
# INSTAGRAM STORIES
# =====================================

def download_story(url, folder):

    parsed = urlparse(url)

    parts = [
        p for p in parsed.path.strip("/").split("/")
        if p
    ]

    if len(parts) < 2 or parts[0].lower() != "stories":
        raise ValueError("Пайванди Stories нодуруст аст.")

    username = parts[1]

    if not re.fullmatch(r"[A-Za-z0-9_.]+", username):
        raise ValueError("Номи аккаунти Instagram нодуруст аст.")

    requested_id = parts[2] if len(parts) >= 3 else None

    loader = create_instagram_loader(login=True)

    profile = instaloader.Profile.from_username(
        loader.context,
        username
    )

    results = []
    index = 0

    stories = loader.get_stories(
        userids=[profile.userid]
    )

    for story in stories:

        for item in story.get_items():

            if requested_id:
                if str(item.mediaid) != requested_id:
                    continue

            index += 1

            if item.is_video:

                media_url = item.video_url
                ext = ".mp4"
                media_type = "video"

            else:

                media_url = item.url
                ext = ".jpg"
                media_type = "photo"

            filename = os.path.join(
                folder,
                f"story_{index}{ext}"
            )

            download_file(
                media_url,
                filename
            )

            results.append(
                (filename, media_type)
            )

    return results


# =====================================
# INSTAGRAM POSTS / REELS / CAROUSEL
# =====================================

def download_post(url, folder):

    match = re.search(
        r"instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)",
        url,
        re.IGNORECASE
    )

    if not match:
        raise ValueError("Пайванди пост нодуруст аст.")

    shortcode = match.group(1)

    loader = create_instagram_loader()

    post = instaloader.Post.from_shortcode(
        loader.context,
        shortcode
    )

    results = []

    # CAROUSEL

    if post.typename == "GraphSidecar":

        nodes = post.get_sidecar_nodes()

        for index, node in enumerate(nodes, start=1):

            if node.is_video:

                media_url = node.video_url
                ext = ".mp4"
                media_type = "video"

            else:

                media_url = node.display_url
                ext = ".jpg"
                media_type = "photo"

            filename = os.path.join(
                folder,
                f"media_{index}{ext}"
            )

            download_file(
                media_url,
                filename
            )

            results.append(
                (filename, media_type)
            )

        return results

    # SINGLE PHOTO

    if not post.is_video:

        filename = os.path.join(
            folder,
            "photo.jpg"
        )

        download_file(
            post.url,
            filename
        )

        return [(filename, "photo")]

    # REELS / VIDEO

    options = {
        "format": "best[ext=mp4]/best",
        "outtmpl": os.path.join(
            folder,
            "%(id)s.%(ext)s"
        ),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "max_filesize": MAX_SIZE,
        "merge_output_format": "mp4",
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

    for filename in os.listdir(folder):

        path = os.path.join(folder, filename)

        if os.path.isfile(path):

            if filename.endswith((".mp4", ".mkv", ".webm", ".mov")):
                results.append(
                    (path, "video")
                )

    return results


# =====================================
# MAIN DOWNLOAD ROUTER
# =====================================

def download_instagram(url, folder):

    parsed = urlparse(url)

    parts = [
        p for p in parsed.path.strip("/").split("/")
        if p
    ]

    if parts and parts[0].lower() == "stories":

        return download_story(
            url,
            folder
        )

    return download_post(
        url,
        folder
    )


# =====================================
# TELEGRAM HANDLER
# =====================================

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message or not update.message.text:
        return

    url = update.message.text.strip()

    parsed = urlparse(url)

    hostname = (parsed.hostname or "").lower()

    if hostname not in (
        "instagram.com",
        "www.instagram.com",
    ):

        await update.message.reply_text(
            "❌ Лутфан пайванди дурусти Instagram фирист."
        )

        return

    if not parsed.path:
        await update.message.reply_text(
            "❌ Пайванд нодуруст аст."
        )
        return

    msg = await update.message.reply_text(
        "⏳ Instagram-ро тафтиш карда истодаам..."
    )

    folder = tempfile.mkdtemp(
        prefix="turbo_"
    )

    files = []

    try:

        loop = asyncio.get_running_loop()

        files = await loop.run_in_executor(
            None,
            download_instagram,
            url,
            folder
        )

        if not files:

            await msg.edit_text(
                "❌ Ягон акс ё видео ёфт нашуд.\n\n"
                "Шояд Story нест ё Instagram дастрасиро маҳдуд кардааст."
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

            if size > MAX_SIZE:
                continue

            with open(filename, "rb") as media:

                if media_type == "photo" and size <= MAX_PHOTO_SIZE:

                    await update.message.reply_photo(
                        photo=media
                    )

                elif media_type == "video":

                    await update.message.reply_video(
                        video=media,
                        supports_streaming=True
                    )

                else:

                    await update.message.reply_document(
                        document=media
                    )

            sent += 1

        await msg.edit_text(
            f"✅ Боргирӣ анҷом ёфт!\n\n"
            f"📦 Файлҳои фиристодашуда: {sent}"
        )

    except Exception as error:

        logger.exception(
            "Instagram download failed"
        )

        await msg.edit_text(
            "❌ Боргирӣ нашуд.\n\n"
            "Сабаб: " + str(error)[:700]
        )

    finally:

        shutil.rmtree(
            folder,
            ignore_errors=True
        )


# =====================================
# MAIN
# =====================================

async def main():

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
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_link
        )
    )

    logger.info(
        "TurboInstta started successfully"
    )

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    await asyncio.Event().wait()


if __name__ == "__main__":

    asyncio.run(main())
