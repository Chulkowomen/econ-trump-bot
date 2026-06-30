export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/users") {
      const auth = request.headers.get("X-Api-Secret");
      if (auth !== env.API_SECRET) {
        return new Response("Unauthorized", { status: 401 });
      }
      const list = await env.BOT_USERS.list();
      const users = [];
      for (const key of list.keys) {
        const value = await env.BOT_USERS.get(key.name);
        if (value) {
          const data = JSON.parse(value);
          if (data.step === "done") {
            users.push(Object.assign({ chat_id: key.name }, data));
          }
        }
      }
      return new Response(JSON.stringify(users), {
        headers: { "Content-Type": "application/json" },
      });
    }

    if (request.method === "POST") {
      let update;
      try {
        update = await request.json();
      } catch (e) {
        return new Response("Bad Request", { status: 400 });
      }
      await handleUpdate(update, env);
      return new Response("OK");
    }

    if (request.method === "GET" && url.pathname === "/debug-trigger") {
      const auth = request.headers.get("X-Api-Secret");
      if (auth !== env.API_SECRET) {
        return new Response("Unauthorized", { status: 401 });
      }
      const diag = {
        hasGHPAT: !!env.GH_PAT,
        ghPatLen: (env.GH_PAT || "").length,
        ghOwner: env.GH_OWNER || null,
        ghRepo: env.GH_REPO || null,
      };
      try {
        const ghUrl = `https://api.github.com/repos/${env.GH_OWNER}/${env.GH_REPO}/actions/workflows/economic_calendar.yml/dispatches`;
        const resp = await fetch(ghUrl, {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${env.GH_PAT}`,
            "Accept": "application/vnd.github+json",
            "User-Agent": "econ-trump-bot-cron",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ ref: "main" }),
        });
        diag.status = resp.status;
        diag.body = await resp.text();
      } catch (e) {
        diag.error = String(e);
      }
      return new Response(JSON.stringify(diag, null, 2), {
        headers: { "Content-Type": "application/json" },
      });
    }

    return new Response("econ-trump-bot webhook is running", { status: 200 });
  },

  // Cloudflare Cron Trigger
  async scheduled(event, env, ctx) {
    const workflows = ["economic_calendar.yml", "economic_alerts.yml", "trump_monitor.yml"];
    for (const wf of workflows) {
      ctx.waitUntil(triggerWorkflow(env, wf));
    }
  },
};

async function triggerWorkflow(env, workflowFile) {
  const url = `https://api.github.com/repos/${env.GH_OWNER}/${env.GH_REPO}/actions/workflows/${workflowFile}/dispatches`;
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.GH_PAT}`,
      "Accept": "application/vnd.github+json",
      "User-Agent": "econ-trump-bot-cron",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref: "main" }),
  });
  if (!resp.ok) {
    console.log(`Trigger failed for ${workflowFile}: ${resp.status} ${await resp.text()}`);
  }
}

async function tgCall(env, method, params) {
  const url = "https://api.telegram.org/bot" + env.TELEGRAM_BOT_TOKEN + "/" + method;
  await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
}

async function getUser(env, chatId) {
  const raw = await env.BOT_USERS.get(String(chatId));
  return raw ? JSON.parse(raw) : { step: "new" };
}

async function setUser(env, chatId, data) {
  await env.BOT_USERS.put(String(chatId), JSON.stringify(data));
}

function extractProfile(from) {
  const profile = {};
  if (!from) return profile;
  if (from.first_name) profile.first_name = from.first_name;
  if (from.last_name) profile.last_name = from.last_name;
  if (from.username) profile.username = from.username;
  return profile;
}

function langKeyboard() {
  return {
    inline_keyboard: [
      [{ text: "🇺🇦 Українська", callback_data: "lang_uk" }],
      [{ text: "🇬🇧 English", callback_data: "lang_en" }],
    ],
  };
}

const TZ_OPTIONS = [
  ["Kyiv (GMT+2/+3)", "Europe/Kyiv"],
  ["Madrid / Berlin (GMT+1/+2)", "Europe/Madrid"],
  ["London (GMT+0/+1)", "Europe/London"],
  ["New York (GMT-5/-4)", "America/New_York"],
  ["Dubai (GMT+4)", "Asia/Dubai"],
];

function tzKeyboard() {
  return {
    inline_keyboard: TZ_OPTIONS.map(function (item) {
      return [{ text: item[0], callback_data: "tz_" + item[1] }];
    }),
  };
}

function notifKeyboard(lang) {
  const labels = lang === "en"
    ? ["Calendar only", "Trump posts only", "Both"]
    : ["Тільки календар", "Тільки Trump", "Обидва"];
  return {
    inline_keyboard: [
      [{ text: "📅 " + labels[0], callback_data: "notif_calendar" }],
      [{ text: "🇺🇸 " + labels[1], callback_data: "notif_trump" }],
      [{ text: "📅🇺🇸 " + labels[2], callback_data: "notif_both" }],
    ],
  };
}

function contactKeyboard(lang) {
  const phoneLabel = lang === "en" ? "📞 Share phone number" : "📞 Поділитися номером телефону";
  const locLabel = lang === "en" ? "📍 Share location" : "📍 Поділитися локацією";
  const skipLabel = lang === "en" ? "⏭ Skip" : "⏭ Пропустити";
  return {
    keyboard: [
      [{ text: phoneLabel, request_contact: true }],
      [{ text: locLabel, request_location: true }],
      [{ text: skipLabel }],
    ],
    resize_keyboard: true,
    one_time_keyboard: true,
  };
}

function skipLabelFor(lang) {
  return lang === "en" ? "⏭ Skip" : "⏭ Пропустити";
}

const TEXTS = {
  start: "Привіт! Налаштуємо бота за 3 кроки.\n\nКрок 1/3 — обери мову сповіщень:\n\n— — —\nHi! Let's set up the bot in 3 steps.\n\nStep 1/3 - choose your notification language:",
  askTz: {
    uk: "Крок 2/3 — обери свій часовий пояс:",
    en: "Step 2/3 - choose your timezone:",
  },
  askNotif: {
    uk: "Крок 3/3 — які сповіщення надсилати?",
    en: "Step 3/3 - which notifications to send?",
  },
  askContact: {
    uk: "Останній (необов'язковий) крок — бажаєш поділитися номером телефону чи локацією? Можеш просто пропустити.",
    en: "Last (optional) step — want to share your phone number or location? You can just skip.",
  },
  done: {
    uk: "Готово! ✅ Налаштування збережено.\n\nЗмінити будь-коли: /settings\nВідписатись: /stop",
    en: "Done! ✅ Settings saved.\n\nChange anytime: /settings\nUnsubscribe: /stop",
  },
  stopped: {
    uk: "Сповіщення вимкнено. Щоб увімкнути знову — напиши /start.",
    en: "Notifications turned off. To turn back on, send /start.",
  },
};

async function handleUpdate(update, env) {
  if (update.message) {
    const msg = update.message;
    const chatId = msg.chat.id;
    const text = (msg.text || "").trim();
    const profile = extractProfile(msg.from);

    if (text === "/start" || text === "/settings") {
      await setUser(env, chatId, Object.assign({ step: "lang", active: true }, profile));
      await tgCall(env, "sendMessage", {
        chat_id: chatId,
        text: TEXTS.start,
        reply_markup: langKeyboard(),
      });
      return;
    }

    if (text === "/stop") {
      const user = await getUser(env, chatId);
      user.active = false;
      user.step = "stopped";
      Object.assign(user, profile);
      await setUser(env, chatId, user);
      const lang = user.lang === "en" ? "en" : "uk";
      await tgCall(env, "sendMessage", {
        chat_id: chatId,
        text: TEXTS.stopped[lang],
        reply_markup: { remove_keyboard: true },
      });
      return;
    }

    const user = await getUser(env, chatId);
    if (user.step === "contact") {
      const lang = user.lang === "en" ? "en" : "uk";
      let gotSomething = false;

      if (msg.contact) {
        user.phone = msg.contact.phone_number;
        gotSomething = true;
      }
      if (msg.location) {
        user.location = { lat: msg.location.latitude, lon: msg.location.longitude };
        gotSomething = true;
      }
      if (text === skipLabelFor(lang)) {
        gotSomething = true;
      }
      Object.assign(user, profile);

      if (gotSomething) {
        user.step = "done";
        await setUser(env, chatId, user);
        await tgCall(env, "sendMessage", {
          chat_id: chatId,
          text: TEXTS.done[lang],
          reply_markup: { remove_keyboard: true },
        });
      }
      return;
    }

    return;
  }

  if (update.callback_query) {
    const cb = update.callback_query;
    const chatId = cb.message.chat.id;
    const data = cb.data || "";
    const profile = extractProfile(cb.from);
    const user = await getUser(env, chatId);
    Object.assign(user, profile);

    if (data.indexOf("lang_") === 0) {
      user.lang = data.slice(5);
      user.step = "tz";
      user.active = true;
      await setUser(env, chatId, user);
      await tgCall(env, "sendMessage", {
        chat_id: chatId,
        text: TEXTS.askTz[user.lang],
        reply_markup: tzKeyboard(),
      });
    } else if (data.indexOf("tz_") === 0) {
      user.timezone = data.slice(3);
      user.step = "notif";
      await setUser(env, chatId, user);
      const lang = user.lang === "en" ? "en" : "uk";
      await tgCall(env, "sendMessage", {
        chat_id: chatId,
        text: TEXTS.askNotif[lang],
        reply_markup: notifKeyboard(lang),
      });
    } else if (data.indexOf("notif_") === 0) {
      user.notif_type = data.slice(6);
      user.step = "contact";
      await setUser(env, chatId, user);
      const lang = user.lang === "en" ? "en" : "uk";
      await tgCall(env, "sendMessage", {
        chat_id: chatId,
        text: TEXTS.askContact[lang],
        reply_markup: contactKeyboard(lang),
      });
    }

    await tgCall(env, "answerCallbackQuery", { callback_query_id: cb.id });
  }
}
