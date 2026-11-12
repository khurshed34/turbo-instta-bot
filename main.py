
import os
import sys
import logging
import asyncio
import shutil
import subprocess
import tempfile

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import yt_dlp

TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Салом! Ман TurboInstta ҳастам.\n\n"
        "🔗 Пайванди Instagram-ро фирист:\n"
        "🎬 Reels ва видео\n"
        "🖼 Суратҳо\n"
        "📚 Carousel\n\n"
        "⚠️ Танҳо маводи дастрас ва иҷозатдодашуда."
    )


def find_files(folder):
    files = []

    for root, dirs, names in os.walk(folder):
        for name in names:
            path = os.path.join(root, name)

            if os.path.isfile(path):
                ext = os.path.splitext(name)[1].lower()

                if ext in IMAGE_EXTENSIONS or ext in VIDEO_EXTENSIONS:
                    files.append(path)

    return sorted(files)


def download_sync(url, folder):
    errors = []

    # Аввал суратҳо ва галереяҳоро месанҷем
    gallery_dl = shutil.which("gallery-dl")

    if gallery_dl:
        try:
            result = subprocess.run(
                [gallery_dl, "-d", folder, url],
                capture_output=True,
                text=True,
                timeout=180
            )

            files = find_files(folder)

            if files:
                return files

            if result.stderr:
                errors.append(result.stderr[-500:])

        except Exception as error:
            errors.append(str(error))

    # Агар gallery-dl файл наёбад, yt-dlp-ро месанҷем
    try:
        options = {
            "format": "best",
            "outtmpl": os.path.join(folder, "%(id)s.%(ext)s"),
            "noplaylist": False,
            "quiet": True,
            "no_warnings": True,
            "max_filesize": 49 * 1024 * 1024,
            "retries": 2,
            "fragment_retries": 2,
            "ignoreerrors": True,
        }

        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.extract_info(url, download=True)

    except Exception as error:
        errors.append(str(error))

    files = find_files(folder)

    if files:
        return files

    raise RuntimeError(
        "Instagram файлро надод. "
        + " | ".join(errors)[-700:]
    )


async def download_instagram(url, folder):
    return await asyncio.to_thread(download_sync, url, folder)


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    if "instagram.com/" not in url:
        await update.message.reply_text(
            "❌ Лутфан пайванди дурусти Instagram фирист."
        )
        return

    msg = await update.message.reply_text(
        "⏳ Маводро меҷӯям, каме интизор шав..."
    )

    try:
        with tempfile.TemporaryDirectory() as folder:
            files = await download_instagram(url, folder)

            if not files:
                await msg.edit_text("❌ Ягон файл ёфт нашуд.")
                return

            await msg.edit_text("📤 Файлҳо фиристода мешаванд...")

            sent = 0
            skipped = 0

            for filename in files[:20]:
                size = os.path.getsize(filename)

                if size > 49 * 1024 * 1024:
                    skipped += 1
                    continue

                ext = os.path.splitext(filename)[1].lower()

                try:
                    with open(filename, "rb") as media:
                        if ext in IMAGE_EXTENSIONS:
                            if size <= 10 * 1024 * 1024:
                                await update.message.reply_photo(photo=media)
                            else:
                                await update.message.reply_document(
                                    document=media
                                )

                        elif ext in VIDEO_EXTENSIONS:
                            await update.message.reply_video(video=media)

                        sent += 1

                except Exception:
                    logger.exception("File sending failed: %s", filename)
                    skipped += 1

            await msg.edit_text(
                f"✅ Тайёр!\n"
                f"📥 Фиристода шуд: {sent}\n"
                f"⚠️ Фиристода нашуд: {skipped}"
            )

    except Exception as error:
        logger.exception("Instagram download failed")
        await msg.edit_text(
            "❌ Боргирӣ нашуд.\nСабаб: " + str(error)[:700]
        )


async def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN дар GitHub Secrets нест!")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link)
    )

    logger.info("TurboInstta started")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
