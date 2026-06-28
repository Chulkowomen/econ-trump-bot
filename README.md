# Econ News & Trump Alerts — Telegram-бот

Безкоштовний мультикористувацький Telegram-бот:
1. 📅 **Щоденний економічний календар** — о 8:00 за локальним часом КОЖНОГО користувача
2. ⏰ **Попередження за 15 хвилин** до виходу важливих економічних новин
3. 🇺🇸 **Миттєвий переклад постів Трампа** з Truth Social (українською або англійською — за вибором)

Будь-хто може написати боту /start, обрати мову / часовий пояс / тип
сповіщень через інтерактивне меню — і одразу почати отримувати
персоналізовані сповіщення. Без лімітів на кількість користувачів.

## Архітектура

Два незалежні безкоштовні компоненти:

### 1. GitHub Actions — розсилка за розкладом
Python-скрипти, які запускаються по cron і надсилають повідомлення:
- economic_calendar.py — щогодини, сам перевіряє чи зараз 8:00 у поясі кожного користувача
- economic_alerts.py — кожні 5 хв, попередження за 15 хв до новин Medium/High impact
- trump_monitor.py — кожні 5 хв, перевіряє RSS-фід trumpstruth.org/feed

Кожен скрипт тягне актуальний список користувачів (мова/пояс/тип сповіщень)
з Cloudflare Worker і надсилає кожному персоналізовано.

### 2. Cloudflare Worker — миттєва обробка команд
Окремий безкоштовний сервіс (Cloudflare Workers + KV), на який вказує
Telegram-вебхук. Обробляє /start, /settings, /stop та натискання кнопок
миттєво, без затримок (на відміну від GitHub Actions, які перевіряють
оновлення лише раз на кілька хвилин).

Дані користувачів (мова, часовий пояс, тип сповіщень, ім'я, опційно
телефон/локація) зберігаються в Cloudflare KV — не в Git, тому лишаються
приватними навіть у публічному репозиторії.

## Налаштування з нуля

### Крок 1 — Telegram-бот
1. Напиши [@BotFather](https://t.me/BotFather) → /newbot → отримай токен

### Крок 2 — Репозиторій
1. Завантаж усі файли цього проєкту в новий GitHub-репозиторій
2. **Обов'язково Public** (безкоштовний безліміт хвилин Actions; приватним репо дають лише 2000 хв/міс)

### Крок 3 — Cloudflare Worker
1. Зареєструйся на [dash.cloudflare.com](https://dash.cloudflare.com) (безкоштовно)
2. Workers & Pages → Create → Hello World → вибери назву
3. Створи KV namespace (Storage & Databases → Workers KV) і прив'яжи його до Worker'а під назвою BOT_USERS
4. Settings → Variables and secrets → додай TELEGRAM_BOT_TOKEN і API_SECRET (придумай свій рандомний рядок)
5. Встанови вебхук:
   https://api.telegram.org/bot<ТОКЕН>/setWebhook?url=https://<твій-worker>.workers.dev/

> Якщо дашборд Cloudflare зависає при редагуванні коду (відомий періодичний
> баг на їхній стороні) — використовуй workflow deploy_worker.yml із цього
> репозиторію: він деплоїть cf_worker/worker.js напряму через Cloudflare API
> (GitHub Actions → Run workflow), обходячи дашборд повністю.

### Крок 4 — Секрети GitHub Actions
Settings → Secrets and variables → Actions → додай:

| Секрет | Значення |
|---|---|
| TELEGRAM_BOT_TOKEN | токен від @BotFather |
| CF_USERS_ENDPOINT | https://<твій-worker>.workers.dev/users |
| CF_API_SECRET | той самий API_SECRET, що в кроці 3.4 |
| CF_API_TOKEN | Cloudflare API-токен з правами "Edit Cloudflare Workers" (My Profile → API Tokens) |
| CF_ACCOUNT_ID | Account ID (видно в правій панелі дашборду Cloudflare) |

### Крок 5 — Права на запис
Settings → Actions → General → "Workflow permissions" → **Read and write permissions** → Save
(без цього скрипти не зможуть комітити свій стан між запусками).

## Флоу /start

1. 🇺🇦 Українська / 🇬🇧 English
2. Часовий пояс: Kyiv / Madrid-Berlin / London / New York / Dubai
3. Тип сповіщень: 📅 Тільки календар / 🇺🇸 Тільки Trump / 📅🇺🇸 Обидва
4. (Необов'язково) 📞 Поділитися номером телефону / 📍 Локацією / ⏭ Пропустити

Команди: /start, /settings (запускає той самий цикл заново), /stop (відписка).

## Тихий режим

Сповіщення з 22:00 до 07:00 за **локальним часом кожного користувача**
надсилаються беззвучно (disable_notification), а не повністю блокуються.

## Як подивитись список користувачів

GET https://<твій-worker>.workers.dev/users
Header: X-Api-Secret: <твій API_SECRET>

Поверне JSON-масив усіх активних користувачів з їхніми налаштуваннями.

## Відомі обмеження

- **ForexFactory-фід неофіційний.** Використовується усією трейдерською спільнотою, але може змінитись без попередження.
- **Truth Social RSS** (trumpstruth.org/feed) — незалежний архів, не офіційний API.
- **Переклад** через deep-translator (Google Translate без ключа) — безкоштовний, але може зрідка лагати на пікових навантаженнях.
- **Дашборд Cloudflare** періодично зависає при редагуванні Worker'а напряму — використовуй deploy_worker.yml.
