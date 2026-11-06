import json, os, re, logging
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from telegram import Update
from telegram.ext import (Application, CommandHandler, ContextTypes,
                          MessageHandler, filters)

# ====== الإعدادات (غيّرها حسب مدينتك) ======
TOKEN = os.getenv("BOT_TOKEN","9213906699:AAE6hzCBj-jkQEaLq5vyHlAybvhUb1st7p0")
CITY, COUNTRY = "Algiers", "Algeria"
TZ = ZoneInfo("Africa/Algiers")
METHOD = 19  # طريقة حساب الفجر (19 = الجزائر)
DATA_FILE = "data.json"
# ==========================================

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
PATTERN = re.compile(r"الحزب\s*(\d{1,2})")


def load():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def chat_data(data, chat_id):
    return data.setdefault(str(chat_id), {"members": {}, "reads": {}})


async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return
    text = msg.text.translate(DIGITS)
    user = msg.from_user
    data = load()
    c = chat_data(data, msg.chat_id)
    c["members"][str(user.id)] = user.first_name  # تسجيل العضو تلقائيا
    if "السلام عليكم" in text:
        m = PATTERN.search(text)
        if m:
            c["reads"][str(user.id)] = int(m.group(1))
            await msg.reply_text("✅ تم تسجيل وردك، بارك الله فيك")
    save(data)


async def join(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    u = update.effective_user
    chat_data(data, update.effective_chat.id)["members"][str(u.id)] = u.first_name
    save(data)
    await update.message.reply_text(f"تمت إضافتك يا {u.first_name}")


def build_report(c):
    reads = c["reads"]
    hizb = Counter(reads.values()).most_common(1)
    title = f"هذا الحزب {hizb[0][0]}" if hizb else "الورد اليومي"
    lines = [title]
    for uid, name in c["members"].items():
       lines.append(f"{name} " + ("✅✅" if uid in reads else "❌️"))
    return "\n".join(lines)


def get_fajr(day: datetime) -> datetime:
    url = f"https://api.aladhan.com/v1/timingsByCity/{day:%d-%m-%Y}"
    r = requests.get(url, params={"city": CITY, "country": COUNTRY,
                                  "method": METHOD}, timeout=20)
    t = r.json()["data"]["timings"]["Fajr"][:5]
    h, m = map(int, t.split(":"))
    return day.replace(hour=h, minute=m, second=0, microsecond=0)


def schedule_next(app: Application):
    now = datetime.now(TZ)
    fajr = get_fajr(now)
    if fajr <= now:
        fajr = get_fajr(now + timedelta(days=1))
    app.job_queue.run_once(daily_report, when=fajr)
    logging.info("التقرير القادم: %s", fajr)


async def daily_report(ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    for chat_id, c in data.items():
        if c["members"]:
            await ctx.bot.send_message(int(chat_id), build_report(c))
        c["reads"] = {}  # بداية يوم جديد
    save(data)
    schedule_next(ctx.application)


async def report_now(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    c = chat_data(load(), update.effective_chat.id)
    await update.message.reply_text(build_report(c))


async def post_init(app: Application):
    schedule_next(app)


def main():
    app = (Application.builder().token(TOKEN)
           .connect_timeout(30).read_timeout(30)
           .write_timeout(30).pool_timeout(30)
           .post_init(post_init).build())
    app.add_handler(CommandHandler("join", join))
    app.add_handler(CommandHandler("report", report_now))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.run_polling(bootstrap_retries=-1)


if __name__ == "__main__":
    main()
