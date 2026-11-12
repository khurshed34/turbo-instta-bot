
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

TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)

MAX_SIZE = 49 * 1024 * 1024
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Салом! Ман TurboInstta ҳастам.\n\n"
        "🔗 Пайванди Instagram-ро фирист:\n\n"
        "🎬 Reels ва видео\n"
        "📸 Сурат\n"
        "📚 Carousel (ҳамаи аксҳо)\n\n"
        "⚠️ Танҳо маводи дастрас ва иҷозатдодашуда."
    )


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
                raise ValueError("Андозаи файл аз ҳад зиёд аст.")

            f.write(chunk)

    return path


def download_instagram(url, folder):
    match = re.search(
        r"instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)",
        url
    )

    if not match:
        raise ValueError("Пайванди Instagram нодуруст аст.")

    shortcode = match.group(1)

    loader = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        save_metadata=False,
        compress_json=False,
        quiet=True
    )

    post = instaloader.Post.from_shortcode(
        loader.context,
        shortcode
    )

    results = []

    # Карусел
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

            download_file(media_url, filename)
            results.append((filename, media_type))

        return results

    # Як сурат
    if not post.is_video:
        filename = os.path.join(folder, "photo.jpg")

        download_file(post.url, filename)

        results.append((filename, "photo"))
        return results

    # Reels ё видео
    options = {
        "format": "best[ext=mp4]/best",
        "outtmpl": os.path.join(folder, "%(id)s.%(ext)s"),
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
            results.append((path, "video"))

    return results


async def handle_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.message or not update.message.text:
        return

    url = update.message.text.strip()

    parsed = urlparse(url)

    if parsed.hostname not in (
        "instagram.com",
        "www.instagram.com",
    ):
        await update.message.reply_text(
            "❌ Лутфан пайванди дурусти Instagram фирист."
        )
        return

    msg = await update.message.reply_text(
        "⏳ Instagram-ро тафтиш карда истодаам..."
    )

    folder = tempfile.mkdtemp(prefix="turbo_")

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
                "❌ Ягон акс ё видео ёфт нашуд."
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

                if media_type == "photo" and size <= 10 * 1024 * 1024:
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
        logger.exception("Instagram download failed")

        await msg.edit_text(
            "❌ Боргирӣ нашуд.\n\n"
            "Сабаб: " + str(error)[:700]
        )

    finally:
        shutil.rmtree(folder, ignore_errors=True)


async def main():
    if not TOKEN:
        raise RuntimeError(
            "BOT_TOKEN дар GitHub Secrets нест!"
        )

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_link
        )
    )

    logger.info("TurboInstta started")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
