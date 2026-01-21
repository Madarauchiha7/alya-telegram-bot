import os
import json
import logging
from pathlib import Path

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from openai import AsyncOpenAI

# ---------- Config ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_KEY")

# Optional: only these Telegram user IDs can use /admin
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}

DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)
USERS_FILE = DATA_DIR / "users.json"

SYSTEM_PROMPT = "You are Alya, a sweet, smart anime-style girl assistant."

# ---------- Logging ----------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("alya-bot")

# ---------- Persistence ----------
def load_users() -> set[int]:
    if not USERS_FILE.exists():
        return set()
    try:
        data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
        return {int(x) for x in data.get("users", [])}
    except Exception:
        logger.exception("Failed to load users.json")
        return set()

def save_users(users: set[int]) -> None:
    payload = {"users": sorted(users)}
    USERS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

users: set[int] = load_users()

# ---------- OpenAI Client ----------
if not OPENAI_KEY:
    raise RuntimeError("OPENAI_KEY environment variable missing.")
client = AsyncOpenAI(api_key=OPENAI_KEY)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable missing.")

# ---------- Helpers ----------
def track_user(update: Update) -> None:
    uid = update.effective_user.id if update.effective_user else None
    if uid is None:
        return
    if uid not in users:
        users.add(uid)
        save_users(users)

def is_admin(user_id: int) -> bool:
    return (not ADMIN_IDS) or (user_id in ADMIN_IDS)

# ---------- Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_user(update)
    user = update.effective_user
    name = user.first_name if user else "friend"
    await update.message.reply_text(
        f"Hey {name}!
I am Alya.
Ask me anything!"
    )

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_user(update)
    uid = update.effective_user.id if update.effective_user else 0
    if not is_admin(uid):
        await update.message.reply_text("Access denied.")
        return
    await update.message.reply_text(f"Total Users: {len(users)}")

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_user(update)

    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    if not text:
        return

    try:
        resp = await client.responses.create(
            model="gpt-4o-mini",
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        )
        reply = resp.output_text.strip() if resp.output_text else "Sorry, I couldn't generate a reply."
        await update.message.reply_text(reply)

    except Exception:
        logger.exception("OpenAI error")
        await update.message.reply_text("Sorry, something went wrong. Try again in a moment.")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if name == "main":
    main()
