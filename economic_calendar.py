"""
Щоденний економічний календар → Telegram.
Джерело: неофіційний публічний JSON-фід ForexFactory (nfs.faireconomy.media).
Запускається через GitHub Actions щогодини, але реально працює лише о TARGET_HOUR
за Мадридом (так розклад автоматично враховує перехід на літній/зимовий час).
"""

import os
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from deep_translator import GoogleTranslator

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
TZ = ZoneInfo("Europe/Madrid")
TARGET_HOUR = 8  # о котрій годині за місцевим часом Мадрида відправляти

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
    # У фіді дата зазвичай у форматі ISO 8601 зі зсувом, напр. "2026-06-27T12:30:00-04:00"
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


def build_message(events_today: list, current: datetime) -> str:
    date_str = current.strftime("%a, %d %b %Y")
    header = f"📅 *Економічний календар на сьогодні*\n🕐 {date_str}"

    if not events_today:
        return header + "\n\nСьогодні значущих подій (Medium/High impact) не очікується."

    lines = [header, ""]
    for ev in events_today:
        emoji = IMPACT_EMOJI.get(ev["impact"], "⚪")
        time_str = ev["time_local"].strftime("%H:%M")
        title_uk = translate(ev["title"])
        line = f"{emoji} {time_str} | {ev['country']} | {title_uk}"
        forecast = ev.get("forecast") or "—"
        previous = ev.get("previous") or "—"
        if forecast != "—" or previous != "—":
            line += f"\n     Прогноз: {forecast} | Попереднє: {previous}"
        lines.append(line)
    return "\n".join(lines)


def send_telegram(text: str) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    # Telegram обмежує повідомлення ~4096 символами — розбиваємо про всяк випадок
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

    if current.hour != TARGET_HOUR:
        print(f"Зараз {current.strftime('%H:%M')} за Мадридом, чекаємо {TARGET_HOUR}:00 — пропускаємо запуск.")
        return

    raw_events = fetch_events()
    today = current.date()
    events_today = []

    parse_errors = 0
    for ev in raw_events:
        try:
            local_dt = parse_event_time(ev["date"])
        except Exception:
            parse_errors += 1
            continue
        if local_dt.date() == today and ev.get("impact") in ("High", "Medium"):
            events_today.append({
                "time_local": local_dt,
                "country": ev.get("country", "?"),
                "title": ev.get("title", "?"),
                "impact": ev.get("impact", "Low"),
                "forecast": ev.get("forecast"),
                "previous": ev.get("previous"),
            })

    if parse_errors:
        print(f"⚠️ Не вдалось розпарсити дату у {parse_errors} подіях — перевір структуру JSON-фіда.")

    events_today.sort(key=lambda e: e["time_local"])
    message = build_message(events_today, current)
    send_telegram(message)
    print(f"Надіслано. Подій сьогодні: {len(events_today)}")

    # heartbeat-файл — потрібен лише щоб у репозиторії була щоденна активність
    # (інакше GitHub може вимкнути розклад через 60 днів "тиші")
    with open("last_run.json", "w", encoding="utf-8") as f:
        json.dump({"last_run": current.isoformat(), "events_count": len(events_today)}, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
