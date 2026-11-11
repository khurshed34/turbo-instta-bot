
import os
import logging
import asyncio
from io import BytesIO
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Салом! Ман TurboInstta ҳастам.\n\n"
        "🔗 Пайванди Instagram-ро фирист:\n"
        "🎬 Reels\n"
        "📹 Видео\n"
        "🖼 Сурат\n"
        "📚 Carousel\n\n"
        "⚠️ Танҳо маводи дастрас ва иҷозатдодашуда."
    )


async def download_instagram(url):
    loop = asyncio.get_running_loop()

    def work():
        options = {
            "format": "best",
            "outtmpl": "/tmp/%(id)s.%(ext)s",
            "noplaylist": False,
            "quiet": True,
            "no_warnings": True,
            "max_filesize": 49 * 1024 * 1024,
        }

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)

        entries = info.get("entries") or [info]
        files = []

        for entry in entries:
            filename = ydl.prepare_filename(entry)
            if os.path.isfile(filename):
                files.append(filename)

        return files

    return await loop.run_in_executor(None, work)


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

    files = []

    try:
        files = await download_instagram(url)

        if not files:
            await msg.edit_text(
                "❌ Мавод ёфт нашуд ё Instagram дастрасиро маҳдуд кард."
            )
            return

        await msg.edit_text("📤 Ирсоли файлҳо...")

        for filename in files:
            with open(filename, "rb") as media:
                if filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                    await update.message.reply_photo(photo=media)
                else:
                    await update.message.reply_video(video=media)

        await msg.delete()

    except Exception as error:
        logger.exception("Instagram download failed")
        await msg.edit_text(
            "❌ Боргирӣ нашуд.\n"
            "Сабаб: " + str(error)[:700]
        )

    finally:
        for filename in files:
            try:
                os.remove(filename)
            except OSError:
                pass


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
