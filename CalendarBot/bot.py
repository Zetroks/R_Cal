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
import html
import json
import logging
import os
import re
from calendar import monthrange
from datetime import date, datetime, timedelta
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
UPDATE_SCRIPT = os.environ.get(
    "UPDATE_SCRIPT",
    str(Path(__file__).resolve().parent.parent / "scripts" / "update_prod.sh"))
BOT_UNIT = os.environ.get("BOT_UNIT", "calendar-bot")

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

MENU = ReplyKeyboardMarkup([["\u2795 Добавить"],
                            ["\U0001F4C5 Неделя", "\U0001F4E5 Установщик"]],
                           resize_keyboard=True)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    status, _ = await api_me(tg_id)
    if status == -1:
        await update.message.reply_text("Сервер недоступен, попробуй позже.")
        return ConversationHandler.END
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


def trunc(s: str, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[:n - 1] + "…"


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
            day = date.today() + timedelta(days=i)
            try:
                r = _req("GET", "/day", _user_headers(tg_id),
                         params={"date": day.isoformat()})
                if r.status_code != 200:
                    continue
                payload = r.json()
                for e in (payload.get("annual") or []):
                    out.append((day, "annual", e))
                for e in (payload.get("daily") or []):
                    out.append((day, "daily", e))
            except Exception:
                continue
        return out

    found = await asyncio.to_thread(_call)
    if not found:
        await update.message.reply_text("На неделю ничего нет. Отдыхай.")
        return
    kb = []
    for day, kind, e in found[:40]:
        title = e.get("title") or "(без названия)"
        if title == "restricted":
            title = "(занято)"
        kb.append([InlineKeyboardButton(
            f"{day.strftime('%d.%m')} · {trunc(title, 26)}",
            callback_data=f"ev:{kind}:{e.get('id')}")])
    await update.message.reply_text(
        "Неделя (нажми чтобы открыть):",
        reply_markup=InlineKeyboardMarkup(kb))


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


# ---------------- event card + wizard ----------------

ADD_KIND, ADD_TITLE, ADD_TYPE, ADD_DATES = range(10, 14)
LINK_VALUE, GEO_VALUE = range(20, 22)

_RANK = {"none": 0, "restricted": 1, "viewer": 2, "member": 3,
         "editor": 4, "manager": 5, "owner": 6}


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def parse_dt_input(text: str, default_year: int):
    """'05.10[.2026][ 15:00]' | '2026-10-05[ 15:00]' -> (datetime, has_time) | (None, False)."""
    t = (text or "").strip()
    m = re.match(r"^(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?(?:\s+(\d{1,2}):(\d{2}))?$", t)
    if m:
        d, mth = int(m.group(1)), int(m.group(2))
        y = int(m.group(3)) if m.group(3) else default_year
        hh = int(m.group(4)) if m.group(4) is not None else 0
        mm = int(m.group(5)) if m.group(5) is not None else 0
        try:
            return datetime(y, mth, d, hh, mm), m.group(4) is not None
        except ValueError:
            return None, False
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ](\d{1,2}):(\d{2}))?$", t)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                            int(m.group(4) or 0), int(m.group(5) or 0)), m.group(4) is not None
        except ValueError:
            return None, False
    return None, False


def parse_daily_input(text: str):
    m = re.match(r"^(\d{1,2})\.(\d{1,2})$", (text or "").strip())
    if not m:
        return None
    d, mth = int(m.group(1)), int(m.group(2))
    if 1 <= mth <= 12 and 1 <= d <= monthrange(2024, mth)[1]:
        return d, mth
    return None


def parse_coords(text: str):
    m = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$", (text or "").strip())
    if not m:
        m = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*$", (text or "").strip())
    if not m:
        return None
    lat, lon = float(m.group(1)), float(m.group(2))
    if -90 <= lat <= 90 and -180 <= lon <= 180:
        return lat, lon
    return None


def render_data_field(url_raw) -> str:
    if not url_raw or url_raw == "restricted":
        return ""
    try:
        data = json.loads(url_raw)
    except (ValueError, TypeError):
        return esc(url_raw)  # legacy plain text
    if not isinstance(data, dict):
        return esc(data)
    parts = []
    for u in data.get("URL", []):
        u = str(u)
        parts.append(f'<a href="{esc(u)}">{esc(trunc(u, 40))}</a>')
    for g in data.get("GEO", []):
        c = parse_coords(str(g))
        if c:
            parts.append(f'<a href="geo:{c[0]},{c[1]}">📍 {c[0]}, {c[1]}</a>')
        else:
            parts.append(esc(g))
    for key in ("COMMENT", "comment"):
        for c in data.get(key, []):
            parts.append(esc(c))
    return "\n".join(parts)


def append_data_field(url_raw, ftype: str, value: str) -> str:
    try:
        data = json.loads(url_raw or "")
        if not isinstance(data, dict):
            raise ValueError
    except (ValueError, TypeError):
        data = {}
        if url_raw and url_raw != "restricted":
            data["COMMENT"] = [url_raw]  # не теряем legacy-текст
    data.setdefault(ftype, []).append(value)
    return json.dumps(data, ensure_ascii=False)


def _ev_dt(s):
    m = re.match(r"^(\d+)-(\d+)-(\d+)[T ](\d+):(\d+)", s or "")
    if not m:
        return None
    return datetime(*map(int, m.groups()))


def card_text(kind: str, ev: dict) -> str:
    title = ev.get("title") or "(без названия)"
    if title == "restricted":
        title = "(занято)"
    lines = [f"<b>{esc(title)}</b>"]
    if kind == "annual":
        s, en = _ev_dt(ev.get("start_date")), _ev_dt(ev.get("end_date"))
        if s and en:
            if s.hour == 0 and s.minute == 0 and (
                    (en.hour, en.minute) in ((23, 59), (0, 0))):
                lines.append(f"📅 {s.strftime('%d.%m.%Y')}" +
                             ("" if s.date() == en.date() or
                              (en.hour, en.minute) == (0, 0) and (en.date() - s.date()).days == 1
                              else f" – {en.strftime('%d.%m.%Y')}"))
            else:
                lines.append(f"📅 {s.strftime('%d.%m.%Y %H:%M')} – {en.strftime('%d.%m.%Y %H:%M')}")
    else:
        try:
            lines.append(f"📅 ежегодно {int(ev.get('day')):02d}.{int(ev.get('month')):02d}")
        except (TypeError, ValueError):
            pass
    if ev.get("type_name"):
        lines.append(f"👥 {esc(ev['type_name'])}")
    links = render_data_field(ev.get("url"))
    if links:
        lines.append(links)
    return "\n".join(lines)


def card_keyboard(kind: str, eid) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("+ Ссылка", callback_data=f"evlink:{kind}:{eid}"),
         InlineKeyboardButton("+ Гео", callback_data=f"evgeo:{kind}:{eid}")],
        [InlineKeyboardButton("Удалить", callback_data=f"evdel:{kind}:{eid}")],
    ])


async def fetch_event(tg_id: int, kind: str, eid):
    def _call():
        try:
            r = _req("GET", "/event", _user_headers(tg_id),
                     params={"kind": kind, "id": eid})
            return r.status_code, (r.json() if r.status_code == 200 else r.text)
        except Exception as exc:
            return -1, str(exc)

    return await asyncio.to_thread(_call)


async def editable_types(tg_id: int):
    def _call():
        h = _user_headers(tg_id)
        types = _req("GET", "/event_types", h).json().get("event_types", [])
        try:
            acc = _req("GET", "/my_access", h).json()
        except Exception:
            acc = {}
        if acc.get("IsAdmin"):
            return types
        return [t for t in types
                if _RANK.get(str(acc.get(str(t["id"]), acc.get(t["id"], "none"))), 0) >= _RANK["member"]]

    return await asyncio.to_thread(_call)


async def show_card(query_or_msg, tg_id: int, kind: str, eid, edit: bool = False):
    code, body = await fetch_event(tg_id, kind, eid)
    text, kb = None, None
    if code == 200:
        text = card_text(kind, body["event"])
        kb = card_keyboard(kind, eid)
    else:
        text = "Недоступно."
    if edit:
        await query_or_msg.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await query_or_msg.reply_text(text, reply_markup=kb, parse_mode="HTML")


async def open_card(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        _, kind, eid = query.data.split(":")
    except ValueError:
        return
    await show_card(query.message, update.effective_user.id, kind, eid)


# ---------------- ADD wizard ----------------

async def _require_user(update, ctx):
    tg_id = update.effective_user.id
    status, _ = await api_me(tg_id)
    if status == -1:
        await update.message.reply_text("Сервер недоступен, попробуй позже.")
        return None
    if status == 401:
        await update.message.reply_text("Сначала регистрация: /start")
        return None
    if status != 200:
        await update.message.reply_text("Заявка на рассмотрении, жди.")
        return None
    return tg_id


async def add_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = await _require_user(update, ctx)
    if tg_id is None:
        return ConversationHandler.END
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Annual (даты)", callback_data="evkind:annual"),
         InlineKeyboardButton("Daily (день в году)", callback_data="evkind:daily")],
    ])
    await update.message.reply_text("Что создаём?", reply_markup=kb)
    return ADD_KIND


async def add_kind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kind = query.data.split(":")[1]
    ctx.user_data["add_kind"] = kind
    await query.edit_message_text("Название:")
    return ADD_TITLE


async def add_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    title = (update.message.text or "").strip()
    if not title:
        await update.message.reply_text("Пустое название, ещё раз:")
        return ADD_TITLE
    ctx.user_data["add_title"] = title
    try:
        types = await editable_types(update.effective_user.id)
    except Exception as exc:
        await update.message.reply_text(f"Не смог получить группы: {exc}")
        return ConversationHandler.END
    if not types:
        await update.message.reply_text("Нет групп, куда можно создавать.")
        return ConversationHandler.END
    kb = [[InlineKeyboardButton(t["name"][:30], callback_data=f"evtype:{t['id']}")]
          for t in types[:20]]
    await update.message.reply_text("Группа:", reply_markup=InlineKeyboardMarkup(kb))
    return ADD_TYPE


async def add_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["add_type"] = int(query.data.split(":")[1])
    if ctx.user_data["add_kind"] == "annual":
        await query.edit_message_text(
            "Начало [и конец через ; ]\nНапример: 05.10 15:00 ; 05.10 16:30\n"
            "Без времени — весь день. Конец можно пропустить (+1ч / до конца дня).")
    else:
        await query.edit_message_text("День и месяц (05.10):")
    return ADD_DATES


async def add_dates(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    kind = ctx.user_data["add_kind"]
    year = date.today().year

    def _create(payload):
        try:
            r = _req("POST", "/event", _user_headers(update.effective_user.id), json=payload)
            return r.status_code, (r.json() if r.status_code == 200 else r.text)
        except Exception as exc:
            return -1, str(exc)

    if kind == "daily":
        parsed = parse_daily_input(text)
        if not parsed:
            await update.message.reply_text("Не понял дату. Формат 05.10:")
            return ADD_DATES
        day, month = parsed
        payload = {"action": "upsert", "kind": "daily", "id": None,
                   "title": ctx.user_data["add_title"], "day": day, "month": month,
                   "type_id": ctx.user_data["add_type"], "version": 0, "is_deleted": False,
                   "start_date": None, "end_date": None, "url": None}
    else:
        parts = [p.strip() for p in text.split(";", 1)]
        start, start_t = parse_dt_input(parts[0], year)
        if not start:
            await update.message.reply_text("Не понял начало. Например: 05.10 15:00 ; 05.10 16:30")
            return ADD_DATES
        if len(parts) > 1 and parts[1] and parts[1] != "-":
            end, end_t = parse_dt_input(parts[1], year)
            if not end:
                await update.message.reply_text("Не понял конец. Ещё раз целиком:")
                return ADD_DATES
        else:
            end, end_t = None, False
        if not start_t and not end_t:
            end = start.replace(hour=23, minute=59, second=59)
        elif end is None:
            end = start + timedelta(hours=1)
        payload = {"action": "upsert", "kind": "annual", "id": None,
                   "title": ctx.user_data["add_title"],
                   "start_date": start.strftime("%Y-%m-%dT%H:%M:%S"),
                   "end_date": end.strftime("%Y-%m-%dT%H:%M:%S"),
                   "type_id": ctx.user_data["add_type"], "version": 0,
                   "is_deleted": False, "day": None, "month": None, "url": None}

    code, body = await asyncio.to_thread(_create, payload)
    if code != 200 or not isinstance(body, dict) or not body.get("id"):
        await update.message.reply_text(f"Не создалось: {body}")
        return ConversationHandler.END
    ctx.user_data.clear()
    await update.message.reply_text("Готово:")
    await show_card(update.message, update.effective_user.id, kind, body["id"])
    return ConversationHandler.END


async def add_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("Отмена.")
    return ConversationHandler.END


# ---------------- link / geo ----------------

async def _linkgeo_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE, ftype: str):
    query = update.callback_query
    await query.answer()
    try:
        _, kind, eid = query.data.split(":")
    except ValueError:
        return ConversationHandler.END
    ctx.user_data["lg_kind"] = kind
    ctx.user_data["lg_id"] = eid
    ctx.user_data["lg_type"] = ftype
    if ftype == "GEO":
        await query.message.reply_text("Пришли координаты (55.75, 37.61):")
    else:
        await query.message.reply_text("Пришли ссылку:")
    return LINK_VALUE if ftype == "URL" else GEO_VALUE


async def link_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    return await _linkgeo_start(update, ctx, "URL")


async def geo_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    return await _linkgeo_start(update, ctx, "GEO")


async def linkgeo_value(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    ftype = ctx.user_data.get("lg_type", "URL")
    kind, eid = ctx.user_data.get("lg_kind"), ctx.user_data.get("lg_id")
    text = (update.message.text or "").strip()
    if ftype == "GEO":
        coords = parse_coords(text)
        if not coords:
            await update.message.reply_text("Не похоже на координаты. Формат: 55.75, 37.61")
            return GEO_VALUE
        value = f"{coords[0]}, {coords[1]}"
    else:
        if not text or " " in text and not text.startswith("http"):
            pass
        value = text
        if not value:
            await update.message.reply_text("Пусто. Пришли ссылку:")
            return LINK_VALUE

    def _call():
        r = _req("GET", "/event", _user_headers(tg_id),
                 params={"kind": kind, "id": eid})
        if r.status_code != 200:
            return r.status_code, None
        ev = r.json()["event"]
        new_url = append_data_field(ev.get("url"), ftype, value)
        payload = {"action": "upsert", "kind": kind, "id": int(ev["id"]),
                   "title": ev.get("title") or "x", "url": new_url,
                   "type_id": int(ev.get("type_id")),
                   "version": int(ev.get("version", 0)) + 1, "is_deleted": False,
                   "start_date": None, "end_date": None, "day": None, "month": None}
        if kind == "annual":
            payload["start_date"] = ev.get("start_date")
            payload["end_date"] = ev.get("end_date")
        else:
            payload["day"] = int(ev.get("day"))
            payload["month"] = int(ev.get("month"))
        r2 = _req("POST", "/event", _user_headers(tg_id), json=payload)
        return r2.status_code, (r2.json() if r2.status_code == 200 else r2.text)

    code, body = await asyncio.to_thread(_call)
    ctx.user_data.clear()
    if code != 200:
        await update.message.reply_text(f"Не сохранилось: {body}")
        return ConversationHandler.END
    await update.message.reply_text("Добавлено. Карточка:")
    await show_card(update.message, tg_id, kind, eid)
    return ConversationHandler.END


# ---------------- delete ----------------

async def card_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        _, kind, eid = query.data.split(":")
    except ValueError:
        return
    code, body = await fetch_event(update.effective_user.id, kind, eid)
    if code != 200:
        await query.edit_message_text("Недоступно.")
        return
    ev = body["event"]
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("Да, удалить",
                             callback_data=f"evdely:{kind}:{eid}:{ev.get('version', 0)}"),
        InlineKeyboardButton("Нет", callback_data=f"evdelno:{kind}:{eid}"),
    ]])
    await query.edit_message_text(f"Удалить «{esc(ev.get('title') or '')}»?",
                                  reply_markup=kb, parse_mode="HTML")


async def card_delete_yes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        _, kind, eid, ver = query.data.split(":")
    except ValueError:
        return

    def _call():
        r = _req("GET", "/event", _user_headers(update.effective_user.id),
                 params={"kind": kind, "id": eid})
        if r.status_code != 200:
            return r.status_code, None
        ev = r.json()["event"]
        payload = {"action": "delete", "kind": kind, "id": int(ev["id"]),
                   "title": ev.get("title") or "x", "type_id": int(ev.get("type_id")),
                   "version": int(ev.get("version", 0)), "is_deleted": True,
                   "start_date": None, "end_date": None, "day": None,
                   "month": None, "url": None}
        r2 = _req("POST", "/event", _user_headers(update.effective_user.id), json=payload)
        return r2.status_code, None

    code, _ = await asyncio.to_thread(_call)
    await query.edit_message_text("Удалено." if code == 200 else f"Не удалилось: {code}")


async def card_delete_no(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        _, kind, eid = query.data.split(":")
    except ValueError:
        return
    await show_card(query, update.effective_user.id, kind, eid, edit=True)


def _run_update():
    if os.environ.get("UPDATE_SSH_HOST"):
        return _run_update_remote()
    import subprocess

    try:
        p = subprocess.run(["sh", UPDATE_SCRIPT], capture_output=True,
                           text=True, timeout=600)
        out = (p.stdout + "\n" + p.stderr).strip()
        return p.returncode, out[-3000:]
    except Exception as exc:
        return -1, str(exc)


def _run_update_remote():
    """Апдейт удалённого бокса по SSH (forced command, ключа хватает только на скрипт)."""
    import paramiko

    host = os.environ["UPDATE_SSH_HOST"]
    user = os.environ.get("UPDATE_SSH_USER", "updater")
    key_file = os.environ.get("UPDATE_SSH_KEY_FILE", "")
    if not key_file or not os.path.exists(key_file):
        return -1, "UPDATE_SSH_KEY_FILE missing"
    try:
        pkey = paramiko.Ed25519Key.from_private_key_file(key_file)
    except Exception:
        try:
            pkey = paramiko.RSAKey.from_private_key_file(key_file)
        except Exception as exc:
            return -1, f"bad key: {exc}"
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        cli.connect(host, username=user, pkey=pkey, timeout=30,
                    allow_agent=False, look_for_keys=False)
        _, stdout, _ = cli.exec_command("update", timeout=600)
        rc = stdout.channel.recv_exit_status()
        return rc, stdout.read().decode("utf-8", "replace").strip()[-3000:]
    except Exception as exc:
        return -1, str(exc)
    finally:
        cli.close()


# ---------------- self update (admin only) ----------------

async def cmd_update(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Только для админа.")
        return
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("Да, обновить", callback_data="upd:yes"),
        InlineKeyboardButton("Нет", callback_data="upd:no"),
    ]])
    await update.message.reply_text(
        "Обновить сервер с гита и перезапустить сервисы?", reply_markup=kb)


async def update_decision(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if update.effective_user.id != ADMIN_ID:
        await query.answer("Только для админа.")
        return
    await query.answer()
    if query.data == "upd:no":
        await query.edit_message_text("Отмена.")
        return

    def _version():
        try:
            r = _req("GET", "/version", _admin_headers())
            return r.json().get("build", "?") if r.status_code == 200 else "?"
        except Exception:
            return "?"

    before = await asyncio.to_thread(_version)
    await query.edit_message_text(f"Обновляю (было {before})...")

    def _run():
        import subprocess

        try:
            p = subprocess.run(["sh", UPDATE_SCRIPT], capture_output=True,
                               text=True, timeout=600)
            out = (p.stdout + "\n" + p.stderr).strip()
            return p.returncode, out[-3000:]
        except Exception as exc:
            return -1, str(exc)

    code, out = await asyncio.to_thread(_run_update)
    after = await asyncio.to_thread(_version)
    await query.message.reply_text(
        f"Готово (код {code}). Было {before}, стало {after}.\n```\n{out}\n```",
        parse_mode=None)
    if code == 0:
        await query.message.reply_text("Перезапускаю бота...")
        import subprocess

        subprocess.Popen(["systemctl", "--user", "restart", BOT_UNIT])


# ---------------- main ----------------

def build_app():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={ASK_LOGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_login)]},
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("week", cmd_week))
    app.add_handler(CommandHandler("update", cmd_update))
    app.add_handler(CallbackQueryHandler(update_decision, pattern="^upd:"))
    app.add_handler(MessageHandler(filters.Regex("^\U0001F4C5"), on_menu))
    app.add_handler(MessageHandler(filters.Regex("^\U0001F4E5"), on_menu))
    app.add_handler(CallbackQueryHandler(on_decision, pattern="^(ap|dn):"))

    add_conv = ConversationHandler(
        entry_points=[CommandHandler("add", add_start),
                      MessageHandler(filters.Regex("^\u2795"), add_start)],
        states={
            ADD_KIND: [CallbackQueryHandler(add_kind, pattern="^evkind:")],
            ADD_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_title)],
            ADD_TYPE: [CallbackQueryHandler(add_type, pattern="^evtype:")],
            ADD_DATES: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_dates)],
        },
        fallbacks=[CommandHandler("cancel", add_cancel)],
    )
    link_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(link_start, pattern="^evlink:")],
        states={LINK_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, linkgeo_value)]},
        fallbacks=[CommandHandler("cancel", add_cancel)],
    )
    geo_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(geo_start, pattern="^evgeo:")],
        states={GEO_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, linkgeo_value)]},
        fallbacks=[CommandHandler("cancel", add_cancel)],
    )
    app.add_handler(add_conv)
    app.add_handler(link_conv)
    app.add_handler(geo_conv)
    app.add_handler(CallbackQueryHandler(open_card, pattern=r"^ev:(annual|daily):\d+$"))
    app.add_handler(CallbackQueryHandler(card_delete, pattern=r"^evdel:(annual|daily):\d+$"))
    app.add_handler(CallbackQueryHandler(card_delete_yes, pattern=r"^evdely:(annual|daily):\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(card_delete_no, pattern=r"^evdelno:(annual|daily):\d+$"))
    return app


def main():
    if not BOT_TOKEN or not ADMIN_ID:
        raise SystemExit("TELEGRAM_BOT_TOKEN / TELEGRAM_ADMIN_ID не заданы (.env)")
    app = build_app()

    app.job_queue.run_once(lambda ctx: poll_pending(ctx), when=5)
    app.job_queue.run_repeating(lambda ctx: poll_pending(ctx), interval=20, first=25)

    log.info("bot polling, api=%s", API)
    app.run_polling()


if __name__ == "__main__":
    main()
