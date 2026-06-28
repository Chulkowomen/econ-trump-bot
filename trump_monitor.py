"""
Моніторинг @realDonaldTrump на Truth Social → переклад → Telegram, кожному
користувачу окремо (мова, тихий режим за його часовим поясом).
"""

import os
import json
import feedparser
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from deep_translator import GoogleTranslator

FEED_URL = "https://www.trumpstruth.org/feed"
STATE_FILE = "state_trump.json"
QUIET_START, QUIET_END = 22, 7

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
USERS_ENDPOINT = os.environ["CF_USERS_ENDPOINT"]
CF_API_SECRET = os.environ["CF_API_SECRET"]

_translate_cache = {}


def fetch_users() -> list:
    resp = requests.get(USERS_ENDPOINT, headers={"X-Api-Secret": CF_API_SECRET}, timeout=20)
    resp.raise_for_status()
    users = resp.json()
    return [u for u in users if u.get("step") == "done" and u.get("active", True)
            and u.get("notif_type") in ("trump", "both")]


def safe_tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Europe/Madrid")


def is_quiet_hours(tz: ZoneInfo) -> bool:
    h = datetime.now(tz).hour
    return h >= QUIET_START or h < QUIET_END


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"seen_ids": [], "initialized": False}


def save_state(state: dict) -> None:
    state["seen_ids"] = state["seen_ids"][-300:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def translate_cached(text: str) -> str:
    if text in _translate_cache:
        return _translate_cache[text]
    try:
        result = GoogleTranslator(source="en", target="uk").translate(text)
    except Exception as e:
        print(f"Переклад не вдався: {e}")
        result = text
    _translate_cache[text] = result
    return result


def send_telegram(chat_id, text: str, quiet: bool) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for i in range(0, len(text), 3500):
        chunk = text[i:i + 3500]
        data = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "Markdown",
            "disable_web_page_preview": "true",
        }
        if quiet:
            data["disable_notification"] = "true"
        r = requests.post(url, data=data, timeout=20)
        if not r.ok:
            print(f"Telegram API помилка для {chat_id}:", r.text)


def entry_key(entry) -> str:
    return entry.get("id") or entry.get("link") or entry.get("title", "")


def get_full_text(entry):
    title = (entry.get("title") or "").strip()
    if not title or title.startswith("[No Title]"):
        return None
    return title


def get_original_url(entry) -> str:
    for key in entry.keys():
        if "originalurl" in key.lower():
            value = entry.get(key)
            if value:
                return value
    return entry.get("link", "")


def main() -> None:
    state = load_state()
    seen = set(state.get("seen_ids", []))
    first_run = not state.get("initialized", False)

    feed = feedparser.parse(FEED_URL)
    if feed.bozo:
        print(f"⚠️ Проблема з парсингом фіда: {feed.bozo_exception}")

    if not feed.entries:
        print("Фід порожній або недоступний — нічого робити.")
        return

    if first_run:
        for entry in feed.entries:
            seen.add(entry_key(entry))
        state["initialized"] = True
        state["seen_ids"] = list(seen)
        save_state(state)
        print(f"Перший запуск: позначено {len(seen)} існуючих постів як прочитані.")
        return

    new_entries = [e for e in feed.entries if entry_key(e) not in seen]
    new_entries.reverse()

    if not new_entries:
        print("Нових постів немає.")
        return

    users = fetch_users()
    if not users:
        print("Немає користувачів з підпискою на Trump-сповіщення.")

    for entry in new_entries:
        key = entry_key(entry)
        original = get_full_text(entry)
        published = entry.get("published", "")
        link = get_original_url(entry)

        for user in users:
            lang = "en" if user.get("lang") == "en" else "uk"
            tz = safe_tz(user.get("timezone", "Europe/Madrid"))

            if original:
                text_body = original if lang == "en" else translate_cached(original)
                header = "🇺🇸 *New Trump post*" if lang == "en" else "🇺🇸 *Новий пост Trump*"
                msg = f"{header}\n🕐 {published}\n\n{text_body}\n\n🔗 {link}"
            else:
                header = ("🇺🇸 *New Trump post* (photo/video, no text)" if lang == "en"
                          else "🇺🇸 *Новий пост Trump* (фото/відео без тексту)")
                msg = f"{header}\n🕐 {published}\n\n🔗 {link}"

            send_telegram(user["chat_id"], msg, is_quiet_hours(tz))

        seen.add(key)
        print(f"Надіслано: {key} для {len(users)} користувачів")

    state["seen_ids"] = list(seen)
    save_state(state)


if __name__ == "__main__":
    main()
