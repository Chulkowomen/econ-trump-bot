"""
Попередження за 15 хвилин до виходу економічної новини → Telegram.
Запускається кожні 5 хвилин. Якщо до події Medium/High impact лишилось
0–15 хвилин і про неї ще не попереджали сьогодні — надсилає алерт.
Кілька подій з однаковим часом групуються в одне повідомлення.
"""

import os
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from deep_translator import GoogleTranslator

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
TZ = ZoneInfo("Europe/Madrid")
LEAD_MINUTES = 15  # за скільки хвилин до події попереджати
STATE_FILE = "state_calendar_alerts.json"

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

IMPACT_EMOJI = {
    "High": "🔴",
    "Medium": "🟠",
    "Low": "🟡",
    "Holiday": "⚪",
}


def now_madrid() -> datetime:
    return datetime.now(TZ)


def fetch_events() -> list:
    resp = requests.get(FF_URL, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return resp.json()


def parse_event_time(raw_date: str) -> datetime:
    dt = datetime.fromisoformat(raw_date)
    return dt.astimezone(TZ)


def translate(text: str) -> str:
    if not text:
        return text
    try:
        return GoogleTranslator(source="en", target="uk").translate(text)
    except Exception as e:
        print(f"Переклад не вдався для '{text}': {e}")
        return text


def load_state(today_str: str) -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        if state.get("date") == today_str:
            return state
    # новий день — починаємо зі свіжим списком сповіщених часів
    return {"date": today_str, "alerted_times": []}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


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


def main() -> None:
    current = now_madrid()
    today = current.date()
    today_str = today.isoformat()

    state = load_state(today_str)
    alerted = set(state["alerted_times"])

    raw_events = fetch_events()

    # групуємо сьогоднішні Medium/High події за часом (HH:MM)
    groups = {}
    for ev in raw_events:
        try:
            local_dt = parse_event_time(ev["date"])
        except Exception:
            continue
        if local_dt.date() != today or ev.get("impact") not in ("High", "Medium"):
            continue
        time_key = local_dt.strftime("%H:%M")
        groups.setdefault(time_key, {"dt": local_dt, "events": []})
        groups[time_key]["events"].append({
            "country": ev.get("country", "?"),
            "title": ev.get("title", "?"),
            "impact": ev.get("impact", "Low"),
            "forecast": ev.get("forecast"),
            "previous": ev.get("previous"),
        })

    sent_any = False
    for time_key, group in sorted(groups.items()):
        if time_key in alerted:
            continue
        minutes_until = (group["dt"] - current).total_seconds() / 60
        if 0 < minutes_until <= LEAD_MINUTES:
            lines = [f"⏰ *За {LEAD_MINUTES} хвилин:*", ""]
            for ev in group["events"]:
                emoji = IMPACT_EMOJI.get(ev["impact"], "⚪")
                title_uk = translate(ev["title"])
                line = f"{emoji} {time_key} | {ev['country']} | {title_uk}"
                forecast = ev.get("forecast") or "—"
                previous = ev.get("previous") or "—"
                if forecast != "—" or previous != "—":
                    line += f"\n     Прогноз: {forecast} | Попереднє: {previous}"
                lines.append(line)
            send_telegram("\n".join(lines))
            alerted.add(time_key)
            sent_any = True
            print(f"Надіслано попередження за {time_key}")

    state["alerted_times"] = sorted(alerted)
    save_state(state)

    if not sent_any:
        print("Найближчих подій (0-15 хв) немає — нічого надсилати.")


if __name__ == "__main__":
    main()
