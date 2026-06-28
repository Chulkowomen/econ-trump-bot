"""
Щоденний економічний календар → Telegram, кожному користувачу окремо.
Список користувачів (мова, часовий пояс, тип сповіщень) тягнемо з Cloudflare Worker.
Запускається через GitHub Actions щогодини; кожному користувачу надсилається
рівно о 8:00 ЙОГО місцевого часу (не Мадрида).
"""

import os
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from deep_translator import GoogleTranslator

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
REFERENCE_TZ = ZoneInfo("Europe/Madrid")
TARGET_HOUR = 8
QUIET_START, QUIET_END = 22, 7

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
USERS_ENDPOINT = os.environ["CF_USERS_ENDPOINT"]
CF_API_SECRET = os.environ["CF_API_SECRET"]

IMPACT_EMOJI = {"High": "🔴", "Medium": "🟠", "Low": "🟡", "Holiday": "⚪"}
_translate_cache = {}


def fetch_users() -> list:
    resp = requests.get(USERS_ENDPOINT, headers={"X-Api-Secret": CF_API_SECRET}, timeout=20)
    resp.raise_for_status()
    users = resp.json()
    return [u for u in users if u.get("step") == "done" and u.get("active", True)
            and u.get("notif_type") in ("calendar", "both")]


def safe_tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Europe/Madrid")


def is_quiet_hours(tz: ZoneInfo) -> bool:
    h = datetime.now(tz).hour
    return h >= QUIET_START or h < QUIET_END

def fetch_events() -> list:
    resp = requests.get(FF_URL, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return resp.json()


def parse_event_time(raw_date: str) -> datetime:
    return datetime.fromisoformat(raw_date)


def translate_cached(text: str) -> str:
    if text in _translate_cache:
        return _translate_cache[text]
    try:
        result = GoogleTranslator(source="en", target="uk").translate(text)
    except Exception as e:
        print(f"Переклад не вдався для '{text}': {e}")
        result = text
    _translate_cache[text] = result
    return result


def build_message(events_today: list, user_tz: ZoneInfo, lang: str) -> str:
    date_str = datetime.now(user_tz).strftime("%a, %d %b %Y")
    if lang == "en":
        header = f"📅 *Today's Economic Calendar*\n🕐 {date_str}"
        empty = "\n\nNo significant (Medium/High impact) events today."
        f_label, p_label = "Forecast", "Previous"
    else:
        header = f"📅 *Економічний календар на сьогодні*\n🕐 {date_str}"
        empty = "\n\nСьогодні значущих подій (Medium/High impact) не очікується."
        f_label, p_label = "Прогноз", "Попереднє"

    if not events_today:
        return header + empty

    lines = [header, ""]
    for ev in sorted(events_today, key=lambda e: e["dt_utc"]):
        local_dt = ev["dt_utc"].astimezone(user_tz)
        emoji = IMPACT_EMOJI.get(ev["impact"], "⚪")
        title = ev["title"] if lang == "en" else translate_cached(ev["title"])
        line = f"{emoji} {local_dt.strftime('%H:%M')} | {ev['country']} | {title}"
        forecast = ev.get("forecast") or "—"
        previous = ev.get("previous") or "—"
        if forecast != "—" or previous != "—":
            line += f"\n     {f_label}: {forecast} | {p_label}: {previous}"
        lines.append(line)
    return "\n".join(lines)


def send_telegram(chat_id, text: str, quiet: bool) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for i in range(0, len(text), 3500):
        chunk = text[i:i + 3500]
        data = {"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"}
        if quiet:
            data["disable_notification"] = "true"
        r = requests.post(url, data=data, timeout=20)
        if not r.ok:
            print(f"Telegram API помилка для {chat_id}:", r.text)


def main() -> None:
    users = fetch_users()
    if not users:
        print("Немає користувачів з підпискою на календар.")
        return

    raw_events = fetch_events()
    today_ref = datetime.now(REFERENCE_TZ).date()

    events_today = []
    parse_errors = 0
    for ev in raw_events:
        try:
            dt = parse_event_time(ev["date"])
        except Exception:
            parse_errors += 1
            continue
        if dt.astimezone(REFERENCE_TZ).date() == today_ref and ev.get("impact") in ("High", "Medium"):
            events_today.append({
                "dt_utc": dt,
                "country": ev.get("country", "?"),
                "title": ev.get("title", "?"),
                "impact": ev.get("impact", "Low"),
                "forecast": ev.get("forecast"),
                "previous": ev.get("previous"),
            })
    if parse_errors:
        print(f"⚠️ Не вдалось розпарсити дату у {parse_errors} подіях.")

    sent = 0
    for user in users:
        tz = safe_tz(user.get("timezone", "Europe/Madrid"))
        if datetime.now(tz).hour != TARGET_HOUR:
            continue
        lang = "en" if user.get("lang") == "en" else "uk"
        message = build_message(events_today, tz, lang)
        send_telegram(user["chat_id"], message, is_quiet_hours(tz))
        sent += 1

    print(f"Надіслано {sent} користувачам. Подій сьогодні: {len(events_today)}")

    with open("last_run.json", "w", encoding="utf-8") as f:
        json.dump(
            {"last_run": datetime.now(REFERENCE_TZ).isoformat(), "sent": sent, "events_count": len(events_today)},
            f, ensure_ascii=False, indent=2,
        )


if __name__ == "__main__":
    main()
