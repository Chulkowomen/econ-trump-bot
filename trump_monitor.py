"""
Моніторинг @realDonaldTrump на Truth Social → переклад → Telegram.
Джерело: RSS-фід https://www.trumpstruth.org/feed (незалежний архів,
перевіряє нові пости що кілька хвилин — не сам сайт truthsocial.com).
Запускається через GitHub Actions кожні 5 хвилин.
"""

import os
import json
import feedparser
import requests
from deep_translator import GoogleTranslator

FEED_URL = "https://www.trumpstruth.org/feed"
STATE_FILE = "state_trump.json"

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"seen_ids": [], "initialized": False}


def save_state(state: dict) -> None:
    state["seen_ids"] = state["seen_ids"][-300:]  # тримаємо тільки останні 300 ID
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def translate(text: str) -> str:
    if not text:
        return text
    try:
        return GoogleTranslator(source="en", target="uk").translate(text)
    except Exception as e:
        print(f"Переклад не вдався: {e}")
        return text


def send_telegram(text: str) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for i in range(0, len(text), 3500):
        chunk = text[i:i + 3500]
        r = requests.post(
            url,
            data={"chat_id": CHAT_ID, "text": chunk, "parse_mode": "Markdown"},
            timeout=20,
        )
        if not r.ok:
            print("Telegram API помилка:", r.text)
        r.raise_for_status()


def entry_key(entry) -> str:
    return entry.get("id") or entry.get("link") or entry.get("title", "")


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
        # Перший запуск: не шлемо весь архів постів, просто запам'ятовуємо
        # все, що є зараз, і почнемо сповіщати лише про НАСТУПНІ пости.
        for entry in feed.entries:
            seen.add(entry_key(entry))
        state["initialized"] = True
        state["seen_ids"] = list(seen)
        save_state(state)
        print(f"Перший запуск: позначено {len(seen)} існуючих постів як прочитані. "
              f"Сповіщення почнуться з наступного нового поста.")
        return

    new_entries = [e for e in feed.entries if entry_key(e) not in seen]
    new_entries.reverse()  # від найстарішого до найновішого — хронологічний порядок у Telegram

    for entry in new_entries:
        key = entry_key(entry)
        original = entry.get("summary") or entry.get("title") or ""
        translated = translate(original)
        published = entry.get("published", "")
        link = entry.get("link", "")
        msg = f"🇺🇸 *Новий пост Trump*\n🕐 {published}\n\n{translated}\n\n🔗 {link}"
        send_telegram(msg)
        seen.add(key)
        print(f"Надіслано: {key}")

    state["seen_ids"] = list(seen)
    save_state(state)

    if not new_entries:
        print("Нових постів немає.")


if __name__ == "__main__":
    main()
