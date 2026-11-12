
import os
import logging
import asyncio
import shutil
import subprocess
import tempfile
from urllib.parse import urlparse

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
INSTAGRAM_COOKIES = os.getenv("INSTAGRAM_COOKIES", "").strip()

MAX_SIZE = 49 * 1024 * 1024
MAX_FILES = 20

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("TurboInstta")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Салом! Ман TurboInstta ҳастам.\n\n"
        "🔗 Пайванди Instagram-ро фирист:\n\n"
        "🎬 Reels ва видео\n"
        "🖼 Суратҳо\n"
        "📚 Carousel\n\n"
        "⚠️ Танҳо маводи дастрас ва иҷозатдодашуда."
    )


def find_files(folder):
    result = []

    for root, dirs, names in os.walk(folder):
        for name in names:
            path = os.path.join(root, name)
            ext = os.path.splitext(name)[1].lower()

            if (
                os.path.isfile(path)
                and ext in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
                and os.path.getsize(path) > 0
            ):
                result.append(path)

    return sorted(result)


def download_sync(url, folder):
    errors = []

    cookie_file = None

    if INSTAGRAM_COOKIES:
        cookie_file = os.path.join(folder, "cookies.txt")

        with open(cookie_file, "w", encoding="utf-8") as f:
            f.write(INSTAGRAM_COOKIES)

        os.chmod(cookie_file, 0o600)
        logger.info("Instagram Cookies configured")

    # Усули якум: gallery-dl
    gallery_dl = shutil.which("gallery-dl")

    if gallery_dl:
        try:
            command = [
                gallery_dl,
                "--destination", folder,
                "--filesize-max", "49M",
            ]

            if cookie_file:
                command.extend(["--cookies", cookie_file])

            command.append(url)

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=180
            )

            files = find_files(folder)

            if files:
                logger.info("gallery-dl downloaded %d files", len(files))
                return files

            if result.stderr:
                errors.append("gallery-dl: " + result.stderr[-500:])

            if result.returncode != 0:
                logger.warning("gallery-dl exited with code %s",
                               result.returncode)

        except subprocess.TimeoutExpired:
            errors.append("gallery-dl: вақти зеркашӣ гузашт")
        except Exception as error:
            errors.append("gallery-dl: " + str(error))

    # Усули дуюм: yt-dlp
    try:
        options = {
            "format": "best[ext=mp4]/best",
            "outtmpl": os.path.join(folder, "%(id)s.%(ext)s"),
            "noplaylist": False,
            "quiet": True,
            "no_warnings": False,
            "logger": logger,
            "max_filesize": MAX_SIZE,
            "retries": 3,
            "fragment_retries": 3,
            "socket_timeout": 30,
            "ignoreerrors": False,
        }

        if cookie_file:
            options["cookiefile"] = cookie_file

        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.extract_info(url, download=True)

    except Exception as error:
        errors.append("yt-dlp: " + str(error))
        logger.exception("yt-dlp download failed")

    files = find_files(folder)

    if files:
        logger.info("yt-dlp downloaded %d files", len(files))
        return files

    if not INSTAGRAM_COOKIES:
        errors.append(
            "INSTAGRAM_COOKIES насб нашудааст. "
            "Агар Instagram Login талаб кунад, Cookies лозим шуда метавонад."
        )

    raise RuntimeError(
        "Instagram файлро надод. " + " | ".join(errors)[-1500:]
    )


async def download_instagram(url, folder):
    return await asyncio.to_thread(download_sync, url, folder)


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    url = update.message.text.strip()

    try:
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https") or parsed.hostname not in (
            "instagram.com",
            "www.instagram.com",
            "m.instagram.com",
        ):
            await update.message.reply_text(
                "❌ Лутфан пайванди дурусти Instagram фирист."
            )
            return

        msg = await update.message.reply_text(
            "⏳ Маводро меҷӯям...\n"
            "Лутфан каме интизор шав."
        )

        with tempfile.TemporaryDirectory() as folder:
            files = await download_instagram(url, folder)

            if not files:
                await msg.edit_text("❌ Ягон файл ёфт нашуд.")
                return

            await msg.edit_text("📤 Файлҳо фиристода мешаванд...")

            sent = 0
            skipped = 0

            for filename in files[:MAX_FILES]:
                size = os.path.getsize(filename)

                if size > MAX_SIZE:
                    skipped += 1
                    continue

                ext = os.path.splitext(filename)[1].lower()

                try:
                    with open(filename, "rb") as media:
                        if ext in {".jpg", ".jpeg", ".png"}:
                            if size <= 10 * 1024 * 1024:
                                await update.message.reply_photo(
                                    photo=media
                                )
                            else:
                                await update.message.reply_document(
                                    document=media
                                )

                        elif ext == ".webp":
                            await update.message.reply_document(
                                document=media
                            )

                        elif ext in VIDEO_EXTENSIONS:
                            await update.message.reply_video(
                                video=media,
                                supports_streaming=True
                            )

                        sent += 1

                except Exception:
                    logger.exception(
                        "Telegram file sending failed: %s", filename
                    )
                    skipped += 1

            if len(files) > MAX_FILES:
                skipped += len(files) - MAX_FILES

            await msg.edit_text(
                "✅ Боргирӣ анҷом ёфт!\n\n"
                f"📥 Фиристода шуд: {sent}\n"
                f"⚠️ Фиристода нашуд: {skipped}"
            )

    except Exception as error:
        logger.exception("Instagram download failed")

        try:
            await msg.edit_text(
                "❌ Боргирӣ нашуд.\n\n"
                "Сабаб: " + str(error)[:2500]
            )
        except Exception:
            await update.message.reply_text(
                "❌ Хатогӣ: " + str(error)[:1000]
            )


async def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN дар GitHub Secrets нест!")

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

    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
