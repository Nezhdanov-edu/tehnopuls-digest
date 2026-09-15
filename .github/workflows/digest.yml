# -*- coding: utf-8 -*-
"""
Робот-дайджест для Телеграм-канала «Технопульс · Образование».

Что делает:
  1. Собирает новости из RSS-лент (список ниже).
  2. Оставляет только те, что касаются роботов, ИИ и EdTech в образовании.
  3. Переводит зарубежные заголовки и описания на русский.
  4. Публикует дайджест в канал через Telegram Bot API.
  5. Запоминает опубликованные ссылки в файле posted.json, чтобы не повторяться.

Настройки (переменные окружения):
  TELEGRAM_BOT_TOKEN — ключ бота от @BotFather
  TELEGRAM_CHAT_ID   — адрес канала, например @tehnopuls_edu, или его числовой id
Если ключ не задан, робот просто печатает дайджест на экран (режим проверки).
"""

import json, os, re, sys, time, html, hashlib
from datetime import datetime, timedelta, timezone
import requests, feedparser

# ============================================================
# НАСТРОЙКИ — можно менять без знания программирования
# ============================================================

MAX_ITEMS = 10           # сколько новостей максимум в одном дайджесте
MAX_PER_SECTION = 4      # сколько максимум в одной рубрике
LOOKBACK_HOURS = 36      # брать новости не старше N часов
CHANNEL_TITLE = "Технопульс · Образование"

# Ленты. type:
#   "edu"  — издание про образование: берём новости, где есть технологии
#   "tech" — издание про технологии: берём новости, где есть образование
#   "news" — общие СМИ: нужно и образование, и технологии
FEEDS = [
    # --- Русскоязычные ---
    {"name": "Учительская газета",  "url": "https://ug.ru/feed/",                                                   "lang": "ru", "type": "edu"},
    {"name": "Педсовет",            "url": "https://pedsovet.org/rss",                                              "lang": "ru", "type": "edu"},
    {"name": "Вести образования",   "url": "https://vogazeta.ru/rss",                                               "lang": "ru", "type": "edu"},
    {"name": "Хабр · Образование",  "url": "https://habr.com/ru/rss/hubs/edu/articles/all/?fl=ru",                  "lang": "ru", "type": "edu"},
    {"name": "Хабр · ИИ",           "url": "https://habr.com/ru/rss/hubs/artificial_intelligence/articles/all/?fl=ru", "lang": "ru", "type": "tech"},
    {"name": "Хайтек",              "url": "https://hightech.fm/feed",                                              "lang": "ru", "type": "tech"},
    {"name": "Naked Science",       "url": "https://naked-science.ru/feed",                                         "lang": "ru", "type": "tech"},
    {"name": "3DNews",              "url": "https://3dnews.ru/news/rss/",                                           "lang": "ru", "type": "tech"},
    {"name": "CNews",               "url": "https://www.cnews.ru/inc/rss/news.xml",                                 "lang": "ru", "type": "tech"},
    {"name": "ТАСС",                "url": "https://tass.ru/rss/v2.xml",                                            "lang": "ru", "type": "news"},
    {"name": "РИА Новости",         "url": "https://ria.ru/export/rss2/archive/index.xml",                          "lang": "ru", "type": "news"},
    {"name": "Российская газета",   "url": "https://rg.ru/xml/index.xml",                                           "lang": "ru", "type": "news"},
    {"name": "Известия",            "url": "https://iz.ru/xml/rss/all.xml",                                         "lang": "ru", "type": "news"},
    {"name": "Интерфакс",           "url": "https://www.interfax.ru/rss.asp",                                       "lang": "ru", "type": "news"},
    {"name": "Коммерсантъ",         "url": "https://www.kommersant.ru/RSS/news.xml",                                "lang": "ru", "type": "news"},
    {"name": "РБК",                 "url": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",                     "lang": "ru", "type": "news"},
    # --- Зарубежные ---
    {"name": "EdSurge",             "url": "https://www.edsurge.com/articles_rss",                                  "lang": "en", "type": "edu"},
    {"name": "eSchool News",        "url": "https://www.eschoolnews.com/feed/",                                     "lang": "en", "type": "edu"},
    {"name": "EdTech Magazine",     "url": "https://edtechmagazine.com/k12/rss.xml",                                "lang": "en", "type": "edu"},
    {"name": "EdTech Magazine",     "url": "https://edtechmagazine.com/higher/rss.xml",                             "lang": "en", "type": "edu"},
    {"name": "Inside Higher Ed",    "url": "https://www.insidehighered.com/rss.xml",                                "lang": "en", "type": "edu"},
    {"name": "Hechinger Report",    "url": "https://hechingerreport.org/feed/",                                     "lang": "en", "type": "edu"},
    {"name": "EdTech Innovation Hub", "url": "https://www.edtechinnovationhub.com/news?format=rss",                 "lang": "en", "type": "edu"},
    {"name": "The Conversation",    "url": "https://theconversation.com/us/education/articles.atom",                "lang": "en", "type": "edu"},
    {"name": "Google for Education", "url": "https://blog.google/outreach-initiatives/education/rss/",             "lang": "en", "type": "edu"},
    {"name": "MIT News",            "url": "https://news.mit.edu/rss/topic/education",                              "lang": "en", "type": "edu"},
    {"name": "MIT News · AI",       "url": "https://news.mit.edu/topic/mitartificial-intelligence2-rss.xml",        "lang": "en", "type": "tech"},
    {"name": "The Robot Report",    "url": "https://www.therobotreport.com/feed/",                                  "lang": "en", "type": "tech"},
    {"name": "IEEE Spectrum",       "url": "https://spectrum.ieee.org/feeds/topic/robotics.rss",                    "lang": "en", "type": "tech"},
    {"name": "TechCrunch",          "url": "https://techcrunch.com/feed/",                                          "lang": "en", "type": "tech"},
    {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/feed/",                              "lang": "en", "type": "tech"},
    {"name": "BBC",                 "url": "https://feeds.bbci.co.uk/news/technology/rss.xml",                      "lang": "en", "type": "tech"},
    {"name": "The Verge",           "url": "https://www.theverge.com/rss/tech/index.xml",                           "lang": "en", "type": "tech"},
    {"name": "Wired",               "url": "https://www.wired.com/feed/rss",                                        "lang": "en", "type": "tech"},
]

# Ключевые слова. Ищутся по началу слова: «робот» найдёт «роботы», «робототехника».
# Слово с восклицательным знаком в конце ищется целиком: «ии!» найдёт «ИИ», но не «России».
EDU_WORDS = ["образован", "школ", "вуз", "университет", "студент", "учител", "учащ", "ученик", "обучени", "обучающ",
             "преподават", "педагог", "колледж", "спо!", "егэ", "огэ", "урок", "класс!", "классы", "классов", "лекци",
             "кафедр", "академи", "курс!", "курсы", "курсов", "edtech", "минпросвещ", "минобрнаук", "рособрнадзор",
             "просвещени", "профессионалитет", "олимпиад", "школьник", "первоклас",
             "education", "school", "universit", "college", "student", "teacher", "classroom", "campus",
             "learning", "learner", "curricul", "k-12", "k12", "higher ed", "edtech", "tutor", "mooc", "faculty",
             "academic", "pedagog", "literacy", "stem!"]
TECH_WORDS = ["ии!", "искусственн", "нейросет", "нейронн", "робот", "дрон!", "дроны", "дронов", "дрон-", "беспилотн", "бпла", "chatgpt", "gpt",
              "gigachat", "yandexgpt", "цифров", "онлайн", "платформ", "edtech", "виртуальн", "vr!", "дистанцион",
              "электронн", "алгоритм", "программирован", "it-", "ит-", "технолог", "приложени", "ии-", "чат-бот",
              "ai!", "ai-", "artificial intelligence", "machine learning", "chatbot", "robot", "drone", "humanoid",
              "digital", "online", "platform", "software", "app!", "apps", "virtual", "algorithm", "coding",
              "computer science", "technolog", "automation", "generative", "llm", "openai", "gemini", "copilot", "claude"]
ROBOT_WORDS = ["робот", "дрон!", "дроны", "дронов", "дрона!", "дронам", "дронах", "дрон-", "беспилотн", "бпла", "гуманоид", "манипулятор", "robot", "drone", "humanoid", "uav"]
AI_WORDS = ["ии!", "ии-", "искусственн", "нейросет", "нейронн", "chatgpt", "gpt", "gigachat", "yandexgpt", "ai!", "ai-",
            "artificial intelligence", "machine learning", "chatbot", "чат-бот", "generative", "llm", "openai", "gemini",
            "copilot", "claude", "языков", "language model", "deepseek"]
# Слова-стоп: новости с ними не берём (спорт, происшествия, военные сводки и т.п.)
STOP_WORDS = ["футбол", "хоккей", "погиб", "убий", "дтп", "пожар", "приговор", "casino", "betting", "атак", "удар",
              "обстрел", "всу", "ранен", "взрыв", "теракт", "alcohol", "proof of age", "погод", "казино"]

MAX_PER_SOURCE = 2       # не больше N новостей от одного издания в дайджесте

SECTIONS = [  # порядок рубрик в дайджесте
    ("robots", "🤖 Роботы и образование"),
    ("ai",     "🧠 ИИ и образование"),
    ("edtech", "💻 EdTech"),
]

# ============================================================
# ДАЛЬШЕ — МЕХАНИКА
# ============================================================

STATE_FILE = "posted.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128 TechnopulsDigest/1.0"}
MSK = timezone(timedelta(hours=3))


def log(*a):
    print(*a, file=sys.stderr, flush=True)


_rx = {}
def has(text, words):
    key = id(words)
    if key not in _rx:
        parts = []
        for w in words:
            w = w.lower()
            if w.endswith("!"):
                parts.append(r"(?<![\w-])" + re.escape(w[:-1]) + r"(?![\w-])")
            else:
                parts.append(r"(?<![\w-])" + re.escape(w))
        _rx[key] = re.compile("|".join(parts), re.IGNORECASE)
    return bool(_rx[key].search(text))


def clean(html_text, limit=220):
    t = re.sub(r"<[^>]+>", " ", html_text or "")
    t = html.unescape(re.sub(r"\s+", " ", t)).strip()
    if len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0] + "…"
    return t


def entry_date(e):
    for k in ("published_parsed", "updated_parsed"):
        if e.get(k):
            try:
                return datetime(*e[k][:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return datetime.now(timezone.utc)


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"posted": []}


def save_state(state):
    state["posted"] = state["posted"][-3000:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=0)


def fetch(feed):
    try:
        r = requests.get(feed["url"], headers=UA, timeout=30)
        d = feedparser.parse(r.content)
        return d.entries
    except Exception as ex:
        log(f"  не ответил: {feed['name']} ({ex})")
        return []


def collect(state):
    posted = set(state["posted"])
    since = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    items, seen_titles = [], set()
    for f in FEEDS:
        entries = fetch(f)
        kept = 0
        for e in entries:
            link = re.sub(r"[?&]utm_[^&#]*", "", (e.get("link") or "").strip()).replace("/?&", "/?").rstrip("?&")
            title = clean(e.get("title", ""), 300)
            if not link or not title or link in posted:
                continue
            key = re.sub(r"\W+", "", title.lower())[:80]
            if key in seen_titles:
                continue
            date = entry_date(e)
            if date < since:
                continue
            summary = clean(e.get("summary") or (e.get("content") or [{}])[0].get("value", ""))
            if summary.lower().startswith(title.lower()[:40]):
                summary = summary[len(title):].strip(" .:-—")
            summary = re.sub(r"^[\w.@… ]{0,40}?(Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d\d/\d\d/\d{4} - \d\d:\d\d [AP]M\s*", "", summary)
            text = f" {title} {summary} ".lower()
            if has(text, STOP_WORDS):
                continue
            edu, tech = has(text, EDU_WORDS), has(text, TECH_WORDS)
            ok = {"edu": tech, "tech": edu, "news": edu and tech}[f["type"]]
            if not ok:
                continue
            section = "robots" if has(text, ROBOT_WORDS) else "ai" if has(text, AI_WORDS) else "edtech"
            # Оценка: свежее и из профильных изданий — выше
            score = (date - since).total_seconds() / 3600
            score += 12 if f["type"] == "edu" else 0
            score += 6 if section != "edtech" else 0
            items.append({"title": title, "link": link, "summary": summary, "source": f["name"],
                          "lang": f["lang"], "section": section, "date": date, "score": score})
            seen_titles.add(key)
            kept += 1
        log(f"{f['name']}: {len(entries)} в ленте, подошло {kept}")
    return items


def select(items):
    items.sort(key=lambda i: -i["score"])
    chosen, per, per_src = [], {}, {}
    # Сначала по одной из каждой рубрики, чтобы дайджест был разнообразным
    for sec, _ in SECTIONS:
        for i in items:
            if i["section"] == sec and i not in chosen:
                chosen.append(i); per[sec] = 1; per_src[i["source"]] = 1
                break
    for i in items:
        if len(chosen) >= MAX_ITEMS:
            break
        if i in chosen or per.get(i["section"], 0) >= MAX_PER_SECTION or per_src.get(i["source"], 0) >= MAX_PER_SOURCE:
            continue
        chosen.append(i); per[i["section"]] = per.get(i["section"], 0) + 1; per_src[i["source"]] = per_src.get(i["source"], 0) + 1
    return chosen


def translate(text):
    """Переводит с английского. Сначала Google, если он не отвечает — MyMemory, иначе оставляет как есть."""
    if not text:
        return text
    try:
        r = requests.get("https://translate.googleapis.com/translate_a/single",
                         params={"client": "gtx", "sl": "en", "tl": "ru", "dt": "t", "q": text},
                         headers=UA, timeout=20)
        if r.ok:
            out = "".join(p[0] for p in r.json()[0] if p and p[0]).strip()
            if out:
                return out
    except Exception:
        pass
    try:
        params = {"q": text[:500], "langpair": "en|ru"}
        if os.environ.get("MYMEMORY_EMAIL"):
            params["de"] = os.environ["MYMEMORY_EMAIL"]
        r = requests.get("https://api.mymemory.translated.net/get", params=params, headers=UA, timeout=20)
        out = r.json().get("responseData", {}).get("translatedText", "")
        if out and "MYMEMORY WARNING" not in out:
            return out
    except Exception:
        pass
    log("  перевод не удался, оставляю оригинал")
    return text


def build_messages(chosen):
    now = datetime.now(MSK)
    when = "утренний" if now.hour < 14 else "вечерний"
    months = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
    head = f"<b>{html.escape(CHANNEL_TITLE)}</b>\n{when.capitalize()} дайджест, {now.day} {months[now.month - 1]}\n"
    blocks = [head]
    for sec, name in SECTIONS:
        rows = [i for i in chosen if i["section"] == sec]
        if not rows:
            continue
        block = f"\n<b>{name}</b>\n"
        for i in rows:
            title, summary = i["title"], i["summary"]
            if i["lang"] == "en":
                title = translate(title)
                summary = translate(summary)
            block += f"\n▪️ <a href=\"{html.escape(i['link'])}\">{html.escape(title)}</a>\n"
            if summary:
                block += f"{html.escape(summary)}\n"
            block += f"<i>{html.escape(i['source'])}</i>\n"
        blocks.append(block)
    # Телеграм ограничивает сообщение 4096 символами — режем по рубрикам
    messages, cur = [], ""
    for b in blocks:
        if len(cur) + len(b) > 3900 and cur:
            messages.append(cur); cur = ""
        cur += b
    if cur:
        messages.append(cur)
    return messages


def send(messages):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        log("Ключ бота или адрес канала не заданы — режим проверки, печатаю дайджест:\n")
        print("\n\n-----\n\n".join(messages))
        return False
    for m in messages:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": m, "parse_mode": "HTML",
                                "link_preview_options": {"is_disabled": True}}, timeout=30)
        if not r.ok:
            log("Телеграм ответил ошибкой:", r.text)
            r.raise_for_status()
        time.sleep(1)
    return True


def main():
    state = load_state()
    items = collect(state)
    log(f"\nВсего подходящих новостей: {len(items)}")
    chosen = select(items)
    if not chosen:
        log("Нечего публиковать.")
        return
    messages = build_messages(chosen)
    if send(messages):
        state["posted"].extend(i["link"] for i in chosen)
        save_state(state)
        log(f"Опубликовано новостей: {len(chosen)}")


if __name__ == "__main__":
    main()
