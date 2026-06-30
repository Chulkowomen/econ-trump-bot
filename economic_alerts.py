"""
Попередження за 15 хвилин до виходу новини → кожному користувачу окремо.
"""

import os
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from deep_translator import GoogleTranslator

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
REFERENCE_TZ = ZoneInfo("Europe/Madrid")
LEAD_MINUTES = 15
QUIET_START, QUIET_END = 22, 7
STATE_FILE = "state_calendar_alerts.json"

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


def load_state(today_str: str) -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            if state.get("date") == today_str and "alerted_keys" in state:
                return state
        except Exception as e:
            print(f"⚠️ Файл стану пошкоджений, починаємо з чистого: {e}")
    return {"date": today_str, "alerted_keys": []}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def build_alert(events: list, user_tz: ZoneInfo, lang: str) -> str:
    header = f"⏰ *In {LEAD_MINUTES} minutes:*" if lang == "en" else f"⏰ *За {LEAD_MINUTES} хвилин:*"
    f_label, p_label = ("Forecast", "Previous") if lang == "en" else ("Прогноз", "Попереднє")
    lines = [header, ""]
    for ev in events:
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
    current = datetime.now(REFERENCE_TZ)
    today_str = current.date().isoformat()
    state = load_state(today_str)
    alerted = set(state.get("alerted_keys", []))

    users = fetch_users()
    if not users:
        print("Немає користувачів з підпискою на календар.")
        return

    raw_events = fetch_events()
    today_ref = current.date()

    groups = {}
    for ev in raw_events:
        try:
            dt = datetime.fromisoformat(ev["date"])
        except Exception:
            continue
        if dt.astimezone(REFERENCE_TZ).date() != today_ref or ev.get("impact") not in ("High", "Medium"):
            continue
        key = dt.isoformat()
        groups.setdefault(key, {"dt_utc": dt, "events": []})
        groups[key]["events"].append({
            "dt_utc": dt,
            "country": ev.get("country", "?"),
            "title": ev.get("title", "?"),
            "impact": ev.get("impact", "Low"),
            "forecast": ev.get("forecast"),
            "previous": ev.get("previous"),
        })

    now_utc = datetime.now(ZoneInfo("UTC"))
    sent_any = False
    for key, group in sorted(groups.items()):
        if key in alerted:
            continue
        minutes_until = (group["dt_utc"] - now_utc).total_seconds() / 60
        if not (0 < minutes_until <= LEAD_MINUTES):
            continue

        for user in users:
            tz = safe_tz(user.get("timezone", "Europe/Madrid"))
            lang = "en" if user.get("lang") == "en" else "uk"
            message = build_alert(group["events"], tz, lang)
            send_telegram(user["chat_id"], message, is_quiet_hours(tz))

        alerted.add(key)
        sent_any = True
        print(f"Надіслано попередження за {key} для {len(users)} користувачів")

    state["alerted_keys"] = sorted(alerted)
    state["date"] = today_str
    save_state(state)

    if not sent_any:
        print("Найближчих подій (0-15 хв) немає — нічого надсилати.")


if __name__ == "__main__":
    main()
"""
Попередження за 15 хвилин до виходу новини → кожному користувачу окремо.
"""

import os
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from deep_translator import GoogleTranslator

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
REFERENCE_TZ = ZoneInfo("Europe/Madrid")
LEAD_MINUTES = 15
QUIET_START, QUIET_END = 22, 7
STATE_FILE = "state_calendar_alerts.json"

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

def load_state(today_str: str) -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        if state.get("date") == today_str:
            return state
    return {"date": today_str, "alerted_keys": []}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def build_alert(events: list, user_tz: ZoneInfo, lang: str) -> str:
    header = f"⏰ *In {LEAD_MINUTES} minutes:*" if lang == "en" else f"⏰ *За {LEAD_MINUTES} хвилин:*"
    f_label, p_label = ("Forecast", "Previous") if lang == "en" else ("Прогноз", "Попереднє")
    lines = [header, ""]
    for ev in events:
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
    current = datetime.now(REFERENCE_TZ)
    today_str = current.date().isoformat()
    state = load_state(today_str)
    alerted = set(state["alerted_keys"])

    users = fetch_users()
    if not users:
        print("Немає користувачів з підпискою на календар.")
        return

    raw_events = fetch_events()
    today_ref = current.date()

    groups = {}
    for ev in raw_events:
        try:
            dt = datetime.fromisoformat(ev["date"])
        except Exception:
            continue
        if dt.astimezone(REFERENCE_TZ).date() != today_ref or ev.get("impact") not in ("High", "Medium"):
            continue
        key = dt.isoformat()
        groups.setdefault(key, {"dt_utc": dt, "events": []})
        groups[key]["events"].append({
            "dt_utc": dt,
            "country": ev.get("country", "?"),
            "title": ev.get("title", "?"),
            "impact": ev.get("impact", "Low"),
            "forecast": ev.get("forecast"),
            "previous": ev.get("previous"),
        })

    now_utc = datetime.now(ZoneInfo("UTC"))
    sent_any = False
    for key, group in sorted(groups.items()):
        if key in alerted:
            continue
        minutes_until = (group["dt_utc"] - now_utc).total_seconds() / 60
        if not (0 < minutes_until <= LEAD_MINUTES):
            continue

        for user in users:
            tz = safe_tz(user.get("timezone", "Europe/Madrid"))
            lang = "en" if user.get("lang") == "en" else "uk"
            message = build_alert(group["events"], tz, lang)
            send_telegram(user["chat_id"], message, is_quiet_hours(tz))

        alerted.add(key)
        sent_any = True
        print(f"Надіслано попередження за {key} для {len(users)} користувачів")

    state["alerted_keys"] = sorted(alerted)
    save_state(state)

    if not sent_any:
        print("Найближчих подій (0-15 хв) немає — нічого надсилати.")


if __name__ == "__main__":
    main()
