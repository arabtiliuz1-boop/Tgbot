import logging
import os
import tempfile

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

import yt_dlp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# If set (e.g. "http://localhost:8081"), the bot talks to your own local
# Bot API server instead of api.telegram.org, raising the upload limit
# from 50MB to 2GB. See the setup notes at the bottom of this file.
LOCAL_BOT_API_URL = os.environ.get("LOCAL_BOT_API_URL", "").rstrip("/")

MAX_FILESIZE_MB = int(os.environ.get("MAX_FILESIZE_MB", "2000" if LOCAL_BOT_API_URL else "50"))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salom! Menga YouTube, Instagram, TikTok yoki Twitter/X havolasini yuboring — "
        "video yuklab beraman.\n\n"
        "Audio (mp3) kerak bo'lsa, /audio dan keyin havolani yozing:\n"
        "/audio https://youtu.be/..."
    )


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE, audio_only: bool = False):
    text = update.message.text.strip()
    url = text.split(maxsplit=1)[-1] if text.startswith("/audio") else text

    if not url.startswith("http"):
        await update.message.reply_text("Iltimos, to'g'ri havola (link) yuboring.")
        return

    status_msg = await update.message.reply_text("Yuklanmoqda... ⏳")

    with tempfile.TemporaryDirectory() as tmpdir:
        outtmpl = os.path.join(tmpdir, "%(title).80s.%(ext)s")

        ydl_opts = {
            "outtmpl": outtmpl,
            "quiet": True,
            "noplaylist": True,
            "max_filesize": MAX_FILESIZE_MB * 1024 * 1024,
        }

        if audio_only:
            ydl_opts.update({
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            })
        else:
            ydl_opts.update({
                "format": f"best[filesize<{MAX_FILESIZE_MB}M]/best",
            })

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                if audio_only:
                    filename = os.path.splitext(filename)[0] + ".mp3"
        except Exception as e:
            logger.exception("Download failed")
            await status_msg.edit_text(f"Xatolik yuz berdi: {e}")
            return

        if not os.path.exists(filename):
            await status_msg.edit_text(
                "Fayl topilmadi yoki hajmi juda katta (50MB dan oshmasligi kerak)."
            )
            return

        try:
            with open(filename, "rb") as f:
                if audio_only:
                    await update.message.reply_audio(audio=f)
                else:
                    await update.message.reply_video(video=f)
        except Exception as e:
            logger.exception("Send failed")
            await status_msg.edit_text(f"Faylni yuborishda xatolik: {e}")
            return

    await status_msg.delete()


async def handle_audio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_link(update, context, audio_only=True)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_link(update, context, audio_only=False)


def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        raise SystemExit("BOT_TOKEN environment variable o'rnatilmagan. @BotFather'dan token oling.")

    builder = Application.builder().token(BOT_TOKEN)

    if LOCAL_BOT_API_URL:
        builder = builder.base_url(f"{LOCAL_BOT_API_URL}/bot").base_file_url(
            f"{LOCAL_BOT_API_URL}/file/bot"
        )
        logger.info("Using local Bot API server at %s (up to 2GB uploads)", LOCAL_BOT_API_URL)
    else:
        logger.info("Using cloud Bot API (api.telegram.org) — 50MB upload limit applies")

    app = builder.build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("audio", handle_audio_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()


if __name__ == "__main__":
    main()

# ---------------------------------------------------------------------------
# To unlock uploads up to 2GB (instead of the default 50MB), run your own
# local Bot API server and point this bot at it:
#
# 1. Get api_id and api_hash (free) from https://my.telegram.org/apps
#
# 2. Run the official Bot API server via Docker:
#      docker run -d -p 8081:8081 \
#        -e TELEGRAM_API_ID=<your_api_id> \
#        -e TELEGRAM_API_HASH=<your_api_hash> \
#        -v $(pwd)/bot-api-data:/var/lib/telegram-bot-api \
#        aiogram/telegram-bot-api:latest
#
# 3. Run this bot with:
#      export BOT_TOKEN="your_bot_token"
#      export LOCAL_BOT_API_URL="http://localhost:8081"
#      python bot.py
#
# Note: overall video quality/size is still bounded by your server's disk
# and bandwidth, and by whatever format yt-dlp can find for the source link.
# ---------------------------------------------------------------------------
