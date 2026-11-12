
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
# MENU
# =====================================

BTN_INSTAGRAM = "📸 Instagram"
BTN_VIDEO = "🎬 YouTube Видео"
BTN_SHORTS = "📱 YouTube Shorts"
BTN_MP3 = "🎵 YouTube MP3"
BTN_BACK = "⬅️ Меню"

MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton(BTN_INSTAGRAM)],
        [KeyboardButton(BTN_VIDEO), KeyboardButton(BTN_SHORTS)],
        [KeyboardButton(BTN_MP3)],
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
        "Яке аз тугмаҳоро интихоб кун:\n\n"
        "📸 Instagram — акс, Reels ва Carousel\n"
        "🎬 YouTube Видео — видео бо овоз\n"
        "📱 YouTube Shorts — Shorts\n"
        "🎵 YouTube MP3 — аудио\n\n"
        "⚠️ Танҳо маводи дастрас ва иҷозатдодашуда.",
        reply_markup=MENU
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
                raise ValueError("Андозаи файл аз 49 MB зиёд аст.")

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

    stories = loader.get_stories(
        userids=[profile.userid]
    )

    for story in stories:

        for item in story.get_items():

            if requested_id and str(item.mediaid) != requested_id:
                continue

            index = len(results) + 1

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

            download_file(media_url, filename)

            results.append((filename, media_type))

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
                f"media_{index}{ext}"
            )

            download_file(media_url, filename)
            results.append((filename, media_type))

        return results

    if not post.is_video:

        filename = os.path.join(folder, "photo.jpg")

        download_file(post.url, filename)

        return [(filename, "photo")]

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

        if os.path.isfile(path) and filename.lower().endswith(
            (".mp4", ".mkv", ".webm", ".mov")
        ):
            results.append((path, "video"))

    return results


def download_instagram(url, folder):

    parsed = urlparse(url)

    parts = [
        p for p in parsed.path.strip("/").split("/")
        if p
    ]

    if parts and parts[0].lower() == "stories":
        return download_story(url, folder)

    return download_post(url, folder)


# =====================================
# YOUTUBE URL CHECK
# =====================================

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


def is_youtube_url(url):

    parsed = urlparse(url)

    hostname = (parsed.hostname or "").lower()

    return (
        parsed.scheme in ("http", "https")
        and hostname in YOUTUBE_HOSTS
    )


# =====================================
# YOUTUBE DOWNLOAD
# =====================================

def download_youtube(url, folder, mode):

    parsed = urlparse(url)

    is_shorts = "/shorts/" in parsed.path.lower()

    if mode == "shorts" and not is_shorts:
        raise ValueError(
            "Ин пайванди Shorts нест. "
            "Пайванди YouTube Shorts фирист."
        )

    if mode == "video" and is_shorts:
        raise ValueError(
            "Ин Shorts аст. Тугмаи YouTube Shorts-ро интихоб кун."
        )

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
    }

    if mode in ("video", "shorts"):

        options.update({
            "format": (
                "best[ext=mp4]/best"
            ),
            "merge_output_format": "mp4",
        })

    elif mode == "mp3":

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

        if os.path.getsize(path) > MAX_SIZE:
            raise ValueError(
                "Файл аз 49 MB зиёд аст."
            )

        if mode == "mp3" and filename.lower().endswith(".mp3"):
            results.append((path, "audio"))

        elif mode in ("video", "shorts") and filename.lower().endswith(
            (".mp4", ".mkv", ".webm", ".mov")
        ):
            results.append((path, "video"))

    return results


# =====================================
# SEND FILES
# =====================================

async def send_files(update, msg, files, folder):

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
                    title="TurboInstta Audio"
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


# =====================================
# MAIN HANDLER
# =====================================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    # MENU BUTTONS

    if text == BTN_INSTAGRAM:
        context.user_data["mode"] = "instagram"

        await update.message.reply_text(
            "📸 Пайванди Instagram-ро фирист."
        )
        return

    if text == BTN_VIDEO:
        context.user_data["mode"] = "video"

        await update.message.reply_text(
            "🎬 Пайванди видеои YouTube-ро фирист.\n\n"
            "⚠️ Танҳо видеоеро истифода бар, ки зеркашии он иҷозат дорад."
        )
        return

    if text == BTN_SHORTS:
        context.user_data["mode"] = "shorts"

        await update.message.reply_text(
            "📱 Пайванди YouTube Shorts-ро фирист."
        )
        return

    if text == BTN_MP3:
        context.user_data["mode"] = "mp3"

        await update.message.reply_text(
            "🎵 Пайванди YouTube-ро барои аудио фирист.\n\n"
            "⚠️ Танҳо аудиоеро истифода бар, ки зеркашии он иҷозат дорад."
        )
        return

    if text == BTN_BACK:
        context.user_data["mode"] = None

        await update.message.reply_text(
            "🏠 Менюи асосӣ:",
            reply_markup=MENU
        )
        return

    url = text
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    is_instagram = hostname in (
        "instagram.com",
        "www.instagram.com"
    )

    is_youtube = is_youtube_url(url)

    mode = context.user_data.get("mode")

    if is_instagram:
        service = "instagram"

    elif is_youtube:
        service = "youtube"

        if mode not in ("video", "shorts", "mp3"):
            await update.message.reply_text(
                "⬇️ Аввал яке аз тугмаҳои YouTube-ро интихоб кун.",
                reply_markup=MENU
            )
            return

    else:
        await update.message.reply_text(
            "❌ Пайванд нодуруст аст.\n"
            "Instagram ё YouTube фирист."
        )
        return

    msg = await update.message.reply_text(
        "⏳ Пайванд тафтиш шуда истодааст..."
    )

    folder = tempfile.mkdtemp(prefix="turbo_")

    try:

        loop = asyncio.get_running_loop()

        if service == "instagram":

            files = await loop.run_in_executor(
                None,
                download_instagram,
                url,
                folder
            )

        else:

            files = await loop.run_in_executor(
                None,
                download_youtube,
                url,
                folder,
                mode
            )

        await send_files(
            update,
            msg,
            files,
            folder
        )

    except Exception as error:

        logger.exception(
            "%s download failed",
            service
        )

        error_text = str(error)

        if "Login error" in error_text or "feedback_required" in error_text:
            error_text = (
                "Instagram воридшавии автоматиро рад кард. "
                "Stories ҳоло дастрас нест. "
                "Reels, акс ва Carousel-ро алоҳида санҷ."
            )

        await msg.edit_text(
            "❌ Боргирӣ иҷро нашуд.\n\n"
            "Сабаб: " + error_text[:600]
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
        "TurboInstta started successfully"
    )

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
