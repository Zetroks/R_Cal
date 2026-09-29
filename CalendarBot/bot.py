"""Telegram-бот календаря (python-telegram-bot, long polling).

Функции:
- /start: регистрация новичков (заявка админу) или меню для своих;
- опрос pending-заявок -> админу сообщение с кнопками да/нет;
- одобрение создаёт пользователя, пароль прилетает юзеру в личку;
- кнопка "Неделя": дела на 7 дней от имени юзера (его доступами);
- кнопка "Установщик": ссылка на релиз десктоп-клиента.

Env: TELEGRAM_BOT_TOKEN (обязательно), TELEGRAM_ADMIN_ID (обязательно),
CAL_API_URL (по умолчанию http://127.0.0.1:8011),
INSTALLER_URL (по умолчанию страница релизов).

Запуск: .\\.venv\\Scripts\\python.exe -m CalendarBot.bot
"""

import asyncio
import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, ConversationHandler, MessageHandler, filters)

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
# общий секрет бота и сервера (CAL_BOT_SECRET из .env), НЕ путать с токеном Telegram
BOT_SECRET = os.environ.get("CAL_BOT_SECRET", "")
ADMIN_ID = int(os.environ.get("TELEGRAM_ADMIN_ID") or 0)
API = os.environ.get("CAL_API_URL", "http://127.0.0.1:8011").rstrip("/")
INSTALLER_URL = os.environ.get(
    "INSTALLER_URL", "https://github.com/Zetroks/R_Cal/releases")

BASE_DIR = Path(__file__).resolve().parent
SEEN_FILE = BASE_DIR / ".pending_seen.json"

ASK_LOGIN = 1

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("calbot")


# ---------------- server api ----------------

def _admin_headers() -> dict:
    return {"X-Bot-Token": BOT_SECRET, "X-Telegram-Id": str(ADMIN_ID)}


def _user_headers(tg_id: int) -> dict:
    return {"X-Bot-Token": BOT_SECRET, "X-Telegram-Id": str(tg_id)}


def _req(method: str, path: str, headers: dict, **kw):
    return requests.request(method, API + path, headers=headers, timeout=20, **kw)


async def api_me(tg_id: int):
    """(status, body): 200 ок, 401 неизвестен, 403 не аппрувнут."""
    def _call():
        try:
            r = _req("GET", "/me", _user_headers(tg_id))
            return r.status_code, (r.json() if r.status_code == 200 else None)
        except Exception as exc:
            return -1, str(exc)

    return await asyncio.to_thread(_call)


# ---------------- seen state ----------------

def load_seen() -> set:
    try:
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def save_seen(seen: set):
    try:
        SEEN_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")
    except OSError:
        pass


# ---------------- menu ----------------

MENU = ReplyKeyboardMarkup([["\U0001F4C5 Неделя", "\U0001F4E5 Установщик"]],
                           resize_keyboard=True)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    status, _ = await api_me(tg_id)
    if status == 200:
        await update.message.reply_text("С возвращением.", reply_markup=MENU)
        return ConversationHandler.END
    if status == 403:
        await update.message.reply_text("Заявка на рассмотрении, жди.")
        return ConversationHandler.END
    await update.message.reply_text(
        "Привет! Это календарь R_Cal. Придумай логин для входа:")
    return ASK_LOGIN


async def reg_login(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    login = (update.message.text or "").strip()
    name = update.effective_user.full_name
    if len(login) < 3 or not login.replace("_", "").replace("-", "").isalnum():
        await update.message.reply_text("Логин: минимум 3 символа, буквы/цифры/_/-. Ещё раз:")
        return ASK_LOGIN

    def _call():
        try:
            r = _req("POST", "/register_request",
                     {"Content-Type": "application/json"},
                     json={"telegram_id": tg_id, "login": login, "name": name})
            return r.status_code, r.text
        except Exception as exc:
            return -1, str(exc)

    code, body = await asyncio.to_thread(_call)
    if code == 200:
        await update.message.reply_text(
            "Заявка отправлена админу. Как подтвердит — пришлю сюда логин и пароль.")
        return ConversationHandler.END
    if code == 409:
        await update.message.reply_text(f"Этот логин занят ({body}). Придумай другой:")
        return ASK_LOGIN
    await update.message.reply_text(f"Сервер недоступен ({code}). Попробуй позже: /start")
    return ConversationHandler.END


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Ладно. Будет надо — /start")
    return ConversationHandler.END


# ---------------- week ----------------

def _fmt_day(day_iso: str, payload: dict) -> str | None:
    lines = []
    for e in (payload.get("annual") or []) + (payload.get("daily") or []):
        title = e.get("title") or "(без названия)"
        if title == "restricted":
            title = "(занято)"
        lines.append(f"• {title}")
    if not lines:
        return None
    return f"<b>{day_iso}</b>\n" + "\n".join(lines)


async def cmd_week(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    status, _ = await api_me(tg_id)
    if status == 401:
        await update.message.reply_text("Сначала регистрация: /start")
        return
    if status != 200:
        await update.message.reply_text("Заявка на рассмотрении, жди.")
        return

    def _call():
        out = []
        for i in range(7):
            day = (date.today() + timedelta(days=i)).isoformat()
            try:
                r = _req("GET", "/day", _user_headers(tg_id), params={"date": day})
                if r.status_code != 200:
                    continue
                text = _fmt_day(day, r.json())
                if text:
                    out.append(text)
            except Exception:
                continue
        return out

    chunks = await asyncio.to_thread(_call)
    if not chunks:
        await update.message.reply_text("На неделю ничего нет. Отдыхай.")
        return
    await update.message.reply_text("\n\n".join(chunks), parse_mode="HTML")


async def cmd_installer(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Десктоп-клиент:\n{INSTALLER_URL}")


async def on_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    if text.startswith("\U0001F4C5"):
        await cmd_week(update, ctx)
    elif text.startswith("\U0001F4E5"):
        await cmd_installer(update, ctx)


# ---------------- pending poll + approve ----------------

async def poll_pending(ctx: ContextTypes.DEFAULT_TYPE):
    seen = ctx.bot_data.setdefault("seen", load_seen())

    def _call():
        try:
            r = _req("GET", "/pending_registrations", _admin_headers())
            if r.status_code != 200:
                return None
            return r.json().get("pending", [])
        except Exception as exc:
            log.warning("pending poll failed: %s", exc)
            return None

    pending = await asyncio.to_thread(_call)
    if not pending:
        return
    fresh = [p for p in pending if p["id"] not in seen]
    if not fresh:
        return
    for p in fresh:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("Да", callback_data=f"ap:{p['id']}"),
            InlineKeyboardButton("Нет", callback_data=f"dn:{p['id']}"),
        ]])
        try:
            await ctx.bot.send_message(
                ADMIN_ID,
                f"Пользователь {p.get('name') or '?'} "
                f"(@id {p['telegram_id']}) хочет присоединиться "
                f"под логином {p['login']}.",
                reply_markup=kb)
            seen.add(p["id"])
        except Exception as exc:
            log.warning("notify admin failed: %s", exc)
    save_seen(seen)


async def on_decision(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if update.effective_user.id != ADMIN_ID:
        await query.answer("Только для админа.")
        return
    await query.answer()
    try:
        action, pid = query.data.split(":")
        pid = int(pid)
    except (ValueError, AttributeError):
        return

    def _call():
        try:
            r = _req("POST", "/approve_registration", _admin_headers(),
                     json={"pending_id": pid, "approve": action == "ap"})
            return r.status_code, (r.json() if r.status_code == 200 else r.text)
        except Exception as exc:
            return -1, str(exc)

    code, body = await asyncio.to_thread(_call)
    if code != 200:
        await query.edit_message_text(f"Ошибка: {body}")
        return
    if isinstance(body, dict) and body.get("status") == "approved":
        await query.edit_message_text(
            f"{body['login']} одобрен(а). Пароль отправлен пользователю.")
        try:
            await ctx.bot.send_message(
                body["telegram_id"],
                f"Доступ разрешён!\nЛогин: {body['login']}\nПароль: {body['password']}\n"
                f"Десктоп-клиент: {INSTALLER_URL}")
        except Exception as exc:
            log.warning("notify user failed: %s", exc)
    else:
        await query.edit_message_text("Отклонено.")
        tg_id = body.get("telegram_id") if isinstance(body, dict) else None
        if tg_id:
            try:
                await ctx.bot.send_message(tg_id, "Админ отклонил заявку.")
            except Exception:
                pass


# ---------------- main ----------------

def main():
    if not BOT_TOKEN or not ADMIN_ID:
        raise SystemExit("TELEGRAM_BOT_TOKEN / TELEGRAM_ADMIN_ID не заданы (.env)")
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={ASK_LOGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_login)]},
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("week", cmd_week))
    app.add_handler(MessageHandler(filters.Regex("^\U0001F4C5"), on_menu))
    app.add_handler(MessageHandler(filters.Regex("^\U0001F4E5"), on_menu))
    app.add_handler(CallbackQueryHandler(on_decision, pattern="^(ap|dn):"))

    app.job_queue.run_once(lambda ctx: poll_pending(ctx), when=5)
    app.job_queue.run_repeating(lambda ctx: poll_pending(ctx), interval=20, first=25)

    log.info("bot polling, api=%s", API)
    app.run_polling()


if __name__ == "__main__":
    main()
