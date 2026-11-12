
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
# BUTTONS
# =====================================

BTN_INSTAGRAM = "📸 Instagram"
BTN_YOUTUBE = "▶️ YouTube"
BTN_TIKTOK = "🎵 TikTok"

BTN_VIDEO = "🎬 YouTube Видео"
BTN_SHORTS = "📱 YouTube Shorts"
BTN_MP3 = "🎧 YouTube MP3"
BTN_BACK = "⬅️ Меню"

MAIN_MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton(BTN_INSTAGRAM)],
        [KeyboardButton(BTN_YOUTUBE), KeyboardButton(BTN_TIKTOK)],
    ],
    resize_keyboard=True
)

YOUTUBE_MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton(BTN_VIDEO)],
        [KeyboardButton(BTN_SHORTS)],
        [KeyboardButton(BTN_MP3)],
        [KeyboardButton(BTN_BACK)],
    ],
    resize_keyboard=True
)

# =====================================
# START
# =====================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["mode"] = None

    await update.message.reply_text(
        "👋 Салом! Ман TurboInstta ҳастам.\n\n"
        "🚀 Як шабакаро интихоб кун:\n\n"
        "📸 Instagram\n"
        "▶️ YouTube\n"
        "🎵 TikTok\n\n"
        "⚠️ Танҳо маводеро истифода бар, ки "
        "ҳуқуқи зеркашӣ ё истифодаашро дорӣ.",
        reply_markup=MAIN_MENU
    )


# =====================================
# DIRECT DOWNLOAD
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
                raise ValueError("Файл аз 49 MB зиёд аст.")

            f.write(chunk)

    return path


# =====================================
# INSTAGRAM
# =====================================

def download_instagram(url, folder):

    parsed = urlparse(url)

    parts = [
        p for p in parsed.path.strip("/").split("/")
        if p
    ]

    if not parts:
        raise ValueError("Пайванди Instagram нодуруст аст.")

    if parts[0].lower() == "stories":
        raise ValueError(
            "Instagram Stories ҳоло дастрас нест. "
            "Воридшавии автоматиро Instagram рад мекунад."
        )

    match = re.search(
        r"instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)",
        url,
        re.IGNORECASE
    )

    if not match:
        raise ValueError(
            "Пайванди Instagram бояд ба Post, Reel ё Carousel бошад."
        )

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

    # CAROUSEL

    if post.typename == "GraphSidecar":

        for index, node in enumerate(
            post.get_sidecar_nodes(),
            start=1
        ):

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
                f"instagram_{index}{ext}"
            )

            download_file(media_url, filename)

            results.append((filename, media_type))

        return results

    # PHOTO

    if not post.is_video:

        filename = os.path.join(
            folder,
            "instagram_photo.jpg"
        )

        download_file(post.url, filename)

        return [(filename, "photo")]

    # VIDEO / REELS

    filename = os.path.join(
        folder,
        "instagram_video.mp4"
    )

    download_file(post.video_url, filename)

    return [(filename, "video")]


# =====================================
# URL CHECK
# =====================================

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}

TIKTOK_HOSTS = {
    "tiktok.com",
    "www.tiktok.com",
    "m.tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
}


def check_url(url):

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return None

    host = (parsed.hostname or "").lower()

    if host in ("instagram.com", "www.instagram.com"):
        return "instagram"

    if host in YOUTUBE_HOSTS:
        return "youtube"

    if host in TIKTOK_HOSTS:
        return "tiktok"

    return None


# =====================================
# YOUTUBE + TIKTOK
# =====================================

def download_ytdlp(url, folder, mode):

    output = os.path.join(
        folder,
        "%(id)s.%(ext)s"
    )

    options = {
        "outtmpl": output,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "max_filesize": MAX_SIZE,
        "restrictfilenames": True,
        "overwrites": True,
        "retries": 2,
        "fragment_retries": 2,
    }

    # VIDEO

    if mode in ("youtube_video", "youtube_shorts", "tiktok"):

        options.update({
            "format": "best[ext=mp4]/best",
            "merge_output_format": "mp4",
        })

    # MP3

    elif mode == "youtube_mp3":

        options.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })

    else:
        raise ValueError("Навъи зеркашӣ нодуруст аст.")

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

    results = []

    for filename in os.listdir(folder):

        path = os.path.join(folder, filename)

        if not os.path.isfile(path):
            continue

        size = os.path.getsize(path)

        if size > MAX_SIZE:
            raise ValueError("Файл аз 49 MB зиёд аст.")

        ext = os.path.splitext(filename)[1].lower()

        if mode == "youtube_mp3":

            if ext == ".mp3":
                results.append((path, "audio"))

        elif ext == ".mp4":
            results.append((path, "video"))

        elif ext in (".mkv", ".webm", ".mov"):
            results.append((path, "document"))

    return results


# =====================================
# SEND FILES
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

            elif media_type == "audio":

                await update.message.reply_audio(
                    audio=media,
                    title="TurboInstta MP3"
                )

            else:

                await update.message.reply_document(
                    document=media
                )

        sent += 1

    await msg.edit_text(
        f"✅ Анҷом ёфт!\n\n"
        f"📦 Файлҳои фиристодашуда: {sent}"
    )


# =====================================
# ERROR MESSAGES
# =====================================

def friendly_error(error):

    message = str(error)

    if "Sign in to confirm you're not a bot" in message:
        return (
            "YouTube ин дархостро маҳдуд кард.\n"
            "Сервери бот барои ин видео тасдиқи иловагӣ гирифта натавонист."
        )

    if "Private video" in message:
        return "❌ Ин видео хусусӣ аст ё дастрас нест."

    if "Video unavailable" in message:
        return "❌ Видео дастрас нест."

    if "Unsupported URL" in message:
        return "❌ Ин пайванд дастгирӣ намешавад."

    if "ffmpeg" in message.lower():
        return "❌ FFmpeg ёфт нашуд. Насби FFmpeg-ро дар bot.yml санҷ."

    if "Login error" in message or "feedback_required" in message:
        return (
            "❌ Instagram воридшавии автоматиро рад кард. "
            "Stories ҳоло кор намекунад."
        )

    return message[:600]


# =====================================
# MESSAGE HANDLER
# =====================================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    # INSTAGRAM BUTTON

    if text == BTN_INSTAGRAM:

        context.user_data["mode"] = "instagram"

        await update.message.reply_text(
            "📸 Пайванди Instagram-ро фирист.\n\n"
            "Дастгирӣ:\n"
            "• Reels\n"
            "• Post\n"
            "• Carousel"
        )
        return

    # YOUTUBE MENU

    if text == BTN_YOUTUBE:

        context.user_data["mode"] = None

        await update.message.reply_text(
            "▶️ Навъи YouTube-ро интихоб кун:",
            reply_markup=YOUTUBE_MENU
        )
        return

    if text == BTN_VIDEO:

        context.user_data["mode"] = "youtube_video"

        await update.message.reply_text(
            "🎬 Пайванди видеои YouTube-ро фирист."
        )
        return

    if text == BTN_SHORTS:

        context.user_data["mode"] = "youtube_shorts"

        await update.message.reply_text(
            "📱 Пайванди YouTube Shorts-ро фирист."
        )
        return

    if text == BTN_MP3:

        context.user_data["mode"] = "youtube_mp3"

        await update.message.reply_text(
            "🎧 Пайванди YouTube-ро барои MP3 фирист."
        )
        return

    # TIKTOK BUTTON

    if text == BTN_TIKTOK:

        context.user_data["mode"] = "tiktok"

        await update.message.reply_text(
            "🎵 Пайванди видеои TikTok-ро фирист."
        )
        return

    # BACK BUTTON

    if text == BTN_BACK:

        context.user_data["mode"] = None

        await update.message.reply_text(
            "🏠 Менюи асосӣ:",
            reply_markup=MAIN_MENU
        )
        return

    # CHECK URL

    service = check_url(text)

    if not service:

        await update.message.reply_text(
            "❌ Пайванд нодуруст аст.\n"
            "Instagram, YouTube ё TikTok фирист."
        )
        return

    mode = context.user_data.get("mode")

    if service == "instagram":

        mode = "instagram"

    elif service == "youtube":

        if mode not in (
            "youtube_video",
            "youtube_shorts",
            "youtube_mp3"
        ):

            await update.message.reply_text(
                "⬇️ Аввал тугмаи YouTube-ро интихоб кун.",
                reply_markup=YOUTUBE_MENU
            )
            return

        is_shorts = "/shorts/" in urlparse(text).path.lower()

        if mode == "youtube_shorts" and not is_shorts:

            await update.message.reply_text(
                "❌ Ин пайванди Shorts нест."
            )
            return

        if mode == "youtube_video" and is_shorts:

            await update.message.reply_text(
                "❌ Барои ин пайванд тугмаи YouTube Shorts-ро интихоб кун."
            )
            return

    elif service == "tiktok":

        mode = "tiktok"

    msg = await update.message.reply_text(
        "⏳ Дархост коркард шуда истодааст..."
    )

    folder = tempfile.mkdtemp(
        prefix="turbo_"
    )

    try:

        loop = asyncio.get_running_loop()

        if service == "instagram":

            files = await loop.run_in_executor(
                None,
                download_instagram,
                text,
                folder
            )

        else:

            files = await loop.run_in_executor(
                None,
                download_ytdlp,
                text,
                folder,
                mode
            )

        await send_files(
            update,
            msg,
            files
        )

    except Exception as error:

        logger.exception(
            "%s download failed",
            service
        )

        await msg.edit_text(
            "❌ Боргирӣ иҷро нашуд.\n\n"
            "Сабаб: " + friendly_error(error)
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
        CommandHandler("start", start)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text
        )
    )

    logger.info(
        "TurboInstta 3-in-1 started successfully"
    )

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
