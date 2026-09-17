# -*- coding: utf-8 -*-
"""
Робот-дайджест для Телеграм-канала «Технопульс · Образование». Версия 2.

Тематика: всё, что связано с ИИ и робототехникой, в пяти разрезах:
  🎓 образование (школа, СПО, вузы, корпоративное, взрослых) — как внедряют ИИ и роботов, новые методы обучения
  🏛 госуправление — ИИ в управлении городами, регионами, странами, субсидии и госпрограммы
  🏢 бизнес — ИИ в управлении компаниями, корпоративный сектор
  🤖 роботы — обучение роботов, роботы с ИИ
  🌍 развитие ИИ и его влияние на общество
Новости без ИИ или роботов не берутся вообще.

Формат публикации: шапка выпуска, затем каждая новость отдельным постом с картинкой.
Каждая новость — самостоятельная заметка: робот открывает полный текст статьи, и языковая модель
пишет по нему краткий аналитический пересказ на русском. Модель же отбирает новости в выпуск.

Настройки (переменные окружения):
  TELEGRAM_BOT_TOKEN — ключ бота от @BotFather
  TELEGRAM_CHAT_ID   — адрес канала, например @tehnopuls_edu, или его числовой id
  ANTHROPIC_API_KEY  — ключ Claude (Anthropic) для написания заметок
     либо OPENAI_API_KEY + OPENAI_BASE_URL + LLM_MODEL (+ OPENAI_PROJECT для YandexGPT) — любой OpenAI-совместимый сервис
Без ключа модели робот работает по-старому: машинный перевод и обрывок из RSS.
Без ключа бота робот печатает выпуск на экран (режим проверки).
"""

import json, os, re, sys, time, html, io
from datetime import datetime, timedelta, timezone
import requests, feedparser

# ============================================================
# НАСТРОЙКИ — можно менять без знания программирования
# ============================================================

MAX_ITEMS = 8            # сколько новостей максимум в одном выпуске
MAX_PER_SECTION = 3      # сколько максимум в одной рубрике
MAX_PER_SOURCE = 2       # не больше N новостей от одного издания
LOOKBACK_HOURS = 30      # брать новости не старше N часов
CHANNEL_TITLE = "Технопульс · Образование"
SUMMARY_LEN = 260        # длина описания из RSS (используется при отборе и как запасной вариант)
CANDIDATES = 28          # сколько лучших по ключевым словам новостей показать модели для отбора
BODY_MIN, BODY_MAX = 450, 700   # длина заметки, знаков (подпись к фото в Телеграме — не больше 1024)
CLAUDE_MODEL = "claude-sonnet-4-6"      # модель Claude по умолчанию
ARTICLE_CHARS = 7000     # сколько знаков статьи отдавать модели

CHANNEL_ABOUT = ("Телеграм-канал о том, как искусственный интеллект и робототехника меняют образование всех уровней "
                 "(школа, СПО, вузы, корпоративное обучение, обучение взрослых), государственное управление "
                 "(города, регионы, страны, госпрограммы и субсидии), управление компаниями и общество в целом, "
                 "а также об обучении роботов и развитии ИИ. Аудитория — руководители образовательных организаций, "
                 "чиновники, преподаватели, HR и руководители компаний в России.")

# Ленты. lang: ru/en. Все ленты фильтруются одинаково: нужна связь с ИИ или роботами.
FEEDS = [
    # --- Русскоязычные: образование ---
    {"name": "Учительская газета",  "url": "https://ug.ru/feed/",                                                  "lang": "ru"},
    {"name": "Педсовет",            "url": "https://pedsovet.org/rss",                                             "lang": "ru"},
    {"name": "Вести образования",   "url": "https://vogazeta.ru/rss",                                              "lang": "ru"},
    {"name": "Хабр · Образование",  "url": "https://habr.com/ru/rss/hubs/edu/articles/all/?fl=ru",                 "lang": "ru"},
    # --- Русскоязычные: ИИ, ИТ, госцифровизация, бизнес ---
    {"name": "Хабр · ИИ",           "url": "https://habr.com/ru/rss/hubs/artificial_intelligence/articles/all/?fl=ru", "lang": "ru"},
    {"name": "Хабр · ML",           "url": "https://habr.com/ru/rss/hubs/machine_learning/articles/all/?fl=ru",    "lang": "ru"},
    {"name": "D-Russia",            "url": "https://d-russia.ru/feed",                                             "lang": "ru"},
    {"name": "TAdviser",            "url": "https://www.tadviser.ru/xml/tadviser.xml",                             "lang": "ru"},
    {"name": "ComNews",             "url": "https://www.comnews.ru/rss",                                           "lang": "ru"},
    {"name": "CNews",               "url": "https://www.cnews.ru/inc/rss/news.xml",                                "lang": "ru"},
    {"name": "Ведомости",           "url": "https://www.vedomosti.ru/rss/rubric/technology",                       "lang": "ru"},
    {"name": "Хайтек",              "url": "https://hightech.fm/feed",                                             "lang": "ru"},
    {"name": "Naked Science",       "url": "https://naked-science.ru/feed",                                        "lang": "ru"},
    {"name": "РБК",                 "url": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",                    "lang": "ru"},
    {"name": "ТАСС",                "url": "https://tass.ru/rss/v2.xml",                                           "lang": "ru"},
    {"name": "РИА Новости",         "url": "https://ria.ru/export/rss2/archive/index.xml",                         "lang": "ru"},
    {"name": "Российская газета",   "url": "https://rg.ru/xml/index.xml",                                          "lang": "ru"},
    {"name": "Известия",            "url": "https://iz.ru/xml/rss/all.xml",                                        "lang": "ru"},
    {"name": "Интерфакс",           "url": "https://www.interfax.ru/rss.asp",                                      "lang": "ru"},
    {"name": "Коммерсантъ",         "url": "https://www.kommersant.ru/RSS/news.xml",                               "lang": "ru"},
    # --- Зарубежные: образование ---
    {"name": "EdSurge",             "url": "https://www.edsurge.com/articles_rss",                                 "lang": "en"},
    {"name": "eSchool News",        "url": "https://www.eschoolnews.com/feed/",                                    "lang": "en"},
    {"name": "EdTech Magazine",     "url": "https://edtechmagazine.com/k12/rss.xml",                               "lang": "en"},
    {"name": "EdTech Magazine",     "url": "https://edtechmagazine.com/higher/rss.xml",                            "lang": "en"},
    {"name": "Inside Higher Ed",    "url": "https://www.insidehighered.com/rss.xml",                               "lang": "en"},
    {"name": "Hechinger Report",    "url": "https://hechingerreport.org/feed/",                                    "lang": "en"},
    {"name": "EdTech Innovation Hub", "url": "https://www.edtechinnovationhub.com/news?format=rss",                "lang": "en"},
    {"name": "The Conversation",    "url": "https://theconversation.com/us/education/articles.atom",               "lang": "en"},
    {"name": "The Conversation",    "url": "https://theconversation.com/us/technology/articles.atom",              "lang": "en"},
    {"name": "Google for Education", "url": "https://blog.google/outreach-initiatives/education/rss/",            "lang": "en"},
    {"name": "Training Industry",   "url": "https://trainingindustry.com/feed/",                                   "lang": "en"},
    {"name": "Chief Learning Officer", "url": "https://www.chieflearningofficer.com/feed/",                        "lang": "en"},
    # --- Зарубежные: госуправление ---
    {"name": "Nextgov",             "url": "https://www.nextgov.com/rss/all/",                                     "lang": "en"},
    {"name": "FedScoop",            "url": "https://fedscoop.com/feed/",                                           "lang": "en"},
    {"name": "StateScoop",          "url": "https://statescoop.com/feed/",                                         "lang": "en"},
    {"name": "UKAuthority",         "url": "https://www.ukauthority.com/rss",                                      "lang": "en"},
    {"name": "Cities Today",        "url": "https://cities-today.com/feed/",                                       "lang": "en"},
    # --- Зарубежные: ИИ, роботы, бизнес ---
    {"name": "TechCrunch",          "url": "https://techcrunch.com/category/artificial-intelligence/feed/",        "lang": "en"},
    {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/feed/",                             "lang": "en"},
    {"name": "MIT News",            "url": "https://news.mit.edu/topic/mitartificial-intelligence2-rss.xml",       "lang": "en"},
    {"name": "IEEE Spectrum",       "url": "https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss",    "lang": "en"},
    {"name": "IEEE Spectrum",       "url": "https://spectrum.ieee.org/feeds/topic/robotics.rss",                   "lang": "en"},
    {"name": "The Robot Report",    "url": "https://www.therobotreport.com/feed/",                                 "lang": "en"},
    {"name": "Robohub",             "url": "https://robohub.org/feed/",                                            "lang": "en"},
    {"name": "Google AI",           "url": "https://blog.google/technology/ai/rss/",                               "lang": "en"},
    {"name": "BBC",                 "url": "https://feeds.bbci.co.uk/news/technology/rss.xml",                     "lang": "en"},
    {"name": "HR Dive",             "url": "https://www.hrdive.com/feeds/news/",                                   "lang": "en"},
]

# Ключевые слова. Ищутся по началу слова: «робот» найдёт «роботы», «робототехника».
# Слово с «!» в конце ищется целиком: «ии!» найдёт «ИИ», но не «России».

# ОБЯЗАТЕЛЬНОЕ условие: в новости должен быть ИИ или роботы. Иначе новость не берётся.
CORE_WORDS = ["ии!", "ии-", "искусственн", "нейросет", "нейронн", "машинн обучен", "машинного обучен", "chatgpt", "gpt",
              "gigachat", "yandexgpt", "deepseek", "языков модел", "llm", "робот", "гуманоид", "генеративн", "чат-бот", "чатбот",
              "openai", "anthropic", "claude", "gemini",
              "copilot", "midjourney", "sora",
              "ai!", "ai-", "artificial intelligence", "machine learning", "deep learning", "neural", "generative",
              "chatbot", "language model", "robot", "humanoid", "agentic", "genai"]
# Дроны и беспилотники намеренно не входят в CORE_WORDS: в новостях это почти всегда военные сводки.

# Рубрики. Порядок важен: новость попадает в первую рубрику, чьи слова в ней найдены.
SECTIONS = [
    {"id": "edu", "name": "ИИ и роботы в образовании", "emoji": "🎓",
     "words": ["образован", "школ", "вуз", "университет", "студент", "учител", "учащ", "ученик", "обучени", "обучающ", "обучать",
               "преподават", "педагог", "колледж", "спо!", "егэ", "урок", "лекци", "кафедр", "академи", "курс!", "курсы", "курсов",
               "edtech", "минпросвещ", "минобрнаук", "просвещени", "профессионалитет", "школьник", "переподготов", "повышени квалификац",
               "навык", "компетенц", "грамотност",
               "education", "school", "universit", "college", "student", "teacher", "classroom", "campus", "learning", "learner",
               "curricul", "k-12", "k12", "higher ed", "tutor", "mooc", "faculty", "academic", "pedagog", "literacy", "training",
               "upskill", "reskill", "workforce development", "skills"]},
    {"id": "gov", "name": "ИИ в госуправлении", "emoji": "🏛",
     "words": ["правительств", "госуправлен", "госуслуг", "министерств", "минцифр", "мэри", "губернатор", "региональн", "муниципал",
               "город!", "города", "городск", "умный город", "субсиди", "грант", "госпрограмм", "нацпроект", "госдум", "закон", "регулир",
               "стратеги", "власт", "ведомств", "чиновник", "бюджет", "оон", "ес!", "евросоюз",
               "government", "governance", "public sector", "federal", "ministry", "minister", "parliament", "congress", "senate",
               "regulat", "legislat", "policy", "policies", "mayor", "city", "cities", "municipal", "smart city", "subsid", "grant",
               "national strategy", "agency", "agencies", "white house", "european commission", "eu!", "un!", "oecd", "unesco"]},
    {"id": "biz", "name": "ИИ в бизнесе и управлении", "emoji": "🏢",
     "words": ["компани", "бизнес", "корпорат", "предприяти", "сотрудник", "менеджмент", "руководител", "топ-менедж", "hr!", "кадр",
               "производств", "банк", "ритейл", "промышлен", "внедрил", "внедрен", "рынок труда", "заменит", "автоматизац",
               "company", "companies", "business", "enterprise", "corporate", "employee", "employer", "management", "manager",
               "executive", "ceo!", "workforce", "workplace", "hr!", "industry", "productivity", "automation", "job!", "jobs", "labor market"]},
    {"id": "robots", "name": "Роботы и их обучение", "emoji": "🤖",
     "words": ["робот", "дрон!", "дроны", "дронов", "беспилотн", "бпла", "гуманоид", "манипулятор",
               "robot", "drone", "humanoid", "autonomous", "manipulat"]},
    {"id": "world", "name": "Развитие ИИ и общество", "emoji": "🌍", "words": []},  # всё остальное с ИИ
]

# Слова-стоп: новости с ними не берём (реклама курсов, спорт, происшествия, военные сводки).
STOP_WORDS = ["футбол", "хоккей", "погиб", "убий", "дтп", "пожар", "приговор", "casino", "betting", "атак", "удар", "обстрел",
              "всу", "ранен", "взрыв", "теракт", "погод", "казино", "сбит", "сбил", "пво!", "ксир", "нато", "минобороны", "ракет",
              "перехват", "боев", "фронт", "shot down", "air defense", "pentagon", "army", "navy", "warfare", "роботакси", "robotaxi", "скидк", "промокод", "распродаж", "черная пятница", "видеокарт",
              "смартфон", "iphone", "игр!", "игры", "геймер", "military", "missile", "weapon", "strike!", "war!", "porn", "crypto",
              "bitcoin", "stock price", "акции выросли", "котировк"]

# ============================================================
# ДАЛЬШЕ — МЕХАНИКА
# ============================================================

STATE_FILE = "posted.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128 TechnopulsDigest/2.0"}
MSK = timezone(timedelta(hours=3))
_rx = {}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def has(text, words):
    if not words:
        return False
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


def clean(html_text, limit=300):
    t = re.sub(r"<[^>]+>", " ", html_text or "")
    t = html.unescape(re.sub(r"[ \t\r]+", " ", t)).strip()
    t = re.sub(r"\n\s*\n+", "\n\n", t)
    if len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0].rstrip(",;:—-") + "…"
    return t


def entry_date(e):
    for k in ("published_parsed", "updated_parsed"):
        if e.get(k):
            try:
                return datetime(*e[k][:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return datetime.now(timezone.utc)


def entry_image(e):
    """Картинка из самой ленты, если издание её отдаёт."""
    for m in (e.get("media_content") or []) + (e.get("media_thumbnail") or []):
        u = m.get("url", "")
        if u and (m.get("type", "").startswith("image") or re.search(r"\.(jpe?g|png|webp|gif)(\?|$)", u, re.I) or "type" not in m):
            return u
    for enc in e.get("enclosures") or []:
        if enc.get("type", "").startswith("image") and enc.get("href"):
            return enc["href"]
    raw = (e.get("summary") or "") + "".join(c.get("value", "") for c in (e.get("content") or []))
    m = re.search(r'<img[^>]+src="([^"]+)"', raw)
    return m.group(1) if m else ""


def page_image(link):
    """Главная картинка со страницы статьи (og:image), если в ленте её не было."""
    try:
        r = requests.get(link, headers=UA, timeout=12)
        m = re.search(r'<meta[^>]+property="og:image(?::url)?"[^>]+content="([^"]+)"', r.text, re.I) or \
            re.search(r'<meta[^>]+content="([^"]+)"[^>]+property="og:image(?::url)?"', r.text, re.I) or \
            re.search(r'<meta[^>]+name="twitter:image"[^>]+content="([^"]+)"', r.text, re.I)
        return html.unescape(m.group(1)) if m else ""
    except Exception:
        return ""


def download_image(url):
    """Скачивает картинку и приводит к JPEG приемлемого размера. Возвращает байты или None."""
    if not url or not url.startswith("http"):
        return None
    try:
        from PIL import Image
        r = requests.get(url, headers=UA, timeout=20)
        if not r.ok or len(r.content) < 3000 or len(r.content) > 15_000_000:
            return None
        im = Image.open(io.BytesIO(r.content))
        if getattr(im, "n_frames", 1) > 1:
            im.seek(0)
        im = im.convert("RGB")
        if im.width < 240 or im.height < 160:
            return None
        if im.width > 1600:
            im = im.resize((1600, int(im.height * 1600 / im.width)))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=85, optimize=True)
        return out.getvalue()
    except Exception as ex:
        log(f"  картинка не скачалась ({url[:60]}): {ex}")
        return None


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
        return feedparser.parse(r.content).entries
    except Exception as ex:
        log(f"  не ответил: {feed['name']} ({ex})")
        return []


def classify(text):
    for s in SECTIONS:
        if not s["words"] or has(text, s["words"]):
            return s["id"]
    return "world"


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
            summary = clean(e.get("summary") or (e.get("content") or [{}])[0].get("value", ""), SUMMARY_LEN)
            if summary.lower().startswith(title.lower()[:40]):
                summary = clean(summary[len(title):].strip(" .:-—"), SUMMARY_LEN)
            summary = re.sub(r"^[\w.@… ]{0,40}?(Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d\d/\d\d/\d{4} - \d\d:\d\d [AP]M\s*", "", summary)
            text = f" {title} {summary} "
            if not has(text, CORE_WORDS) or has(text, STOP_WORDS):
                continue
            section = classify(text)
            # Оценка: свежее выше; тематические рубрики выше общей; новость, где ИИ уже в заголовке, — выше
            score = (date - since).total_seconds() / 3600
            score += 10 if section in ("edu", "gov") else 6 if section in ("biz", "robots") else 0
            score += 5 if has(f" {title} ", CORE_WORDS) else 0
            items.append({"title": title, "link": link, "summary": summary, "source": f["name"], "lang": f["lang"],
                          "section": section, "date": date, "score": score, "img": entry_image(e)})
            seen_titles.add(key)
            kept += 1
        log(f"{f['name']}: {len(entries)} в ленте, подошло {kept}")
    return items


def select(items, limit=None, per_section=None, per_source=None):
    limit, per_section, per_source = limit or MAX_ITEMS, per_section or MAX_PER_SECTION, per_source or MAX_PER_SOURCE
    items.sort(key=lambda i: -i["score"])
    chosen, per, per_src = [], {}, {}

    def ok(i):
        return i not in chosen and per.get(i["section"], 0) < per_section and per_src.get(i["source"], 0) < per_source

    def take(i):
        chosen.append(i)
        per[i["section"]] = per.get(i["section"], 0) + 1
        per_src[i["source"]] = per_src.get(i["source"], 0) + 1

    for s in SECTIONS:  # по одной из каждой рубрики для разнообразия
        for i in items:
            if i["section"] == s["id"] and ok(i):
                take(i)
                break
    for i in items:
        if len(chosen) >= limit:
            break
        if ok(i):
            take(i)
    order = {s["id"]: n for n, s in enumerate(SECTIONS)}
    chosen.sort(key=lambda i: (order[i["section"]], -i["score"]))
    return chosen[:limit]


def translate(text):
    """Перевод с английского: Google, при сбое — MyMemory, иначе оригинал."""
    if not text:
        return text
    try:
        r = requests.get("https://translate.googleapis.com/translate_a/single",
                         params={"client": "gtx", "sl": "en", "tl": "ru", "dt": "t", "q": text}, headers=UA, timeout=20)
        if r.ok:
            out = "".join(p[0] for p in r.json()[0] if p and p[0]).strip()
            if out:
                return out
    except Exception:
        pass
    try:
        params = {"q": text[:500], "langpair": "en|ru"}
        if os.environ.get("MYMEMORY_EMAIL", "").strip():
            params["de"] = os.environ["MYMEMORY_EMAIL"].strip()
        r = requests.get("https://api.mymemory.translated.net/get", params=params, headers=UA, timeout=20)
        out = r.json().get("responseData", {}).get("translatedText", "")
        if out and "MYMEMORY WARNING" not in out:
            return out
    except Exception:
        pass
    log("  перевод не удался, оставляю оригинал")
    return text



# ---------- языковая модель ----------

def llm_available():
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip() or os.environ.get("OPENAI_API_KEY", "").strip())


def llm(system, user, max_tokens=1200):
    """Один запрос к модели. Claude, если задан ANTHROPIC_API_KEY, иначе OpenAI-совместимый сервис."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        r = requests.post("https://api.anthropic.com/v1/messages",
                          headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                          json={"model": os.environ.get("LLM_MODEL", "").strip() or CLAUDE_MODEL, "max_tokens": max_tokens,
                                "system": system, "messages": [{"role": "user", "content": user}]}, timeout=120)
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json()["content"])
    key = os.environ["OPENAI_API_KEY"].strip()
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    headers = {"Authorization": "Bearer " + key, "content-type": "application/json"}
    if os.environ.get("OPENAI_PROJECT", "").strip():      # для YandexGPT сюда передаётся ID каталога
        headers["OpenAI-Project"] = os.environ["OPENAI_PROJECT"].strip()
    r = requests.post(base + "/chat/completions", headers=headers,
                      json={"model": os.environ.get("LLM_MODEL", "gpt-4o-mini").strip(), "max_tokens": max_tokens,
                            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}, timeout=120)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def parse_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)


def llm_select(items):
    """Модель выбирает новости в выпуск из списка кандидатов и назначает рубрику."""
    cands = items[:CANDIDATES]
    sec_list = "\n".join(f'  "{s["id"]}" — {s["name"]}' for s in SECTIONS)
    listing = "\n\n".join(f"[{n}] {i['title']}\n{i['summary']}\n(Источник: {i['source']}, {i['date'].astimezone(MSK):%d.%m %H:%M})"
                          for n, i in enumerate(cands, 1))
    system = ("Ты выпускающий редактор. " + CHANNEL_ABOUT + " Отвечай только JSON без пояснений.")
    user = (f"Ниже {len(cands)} новостей-кандидатов. Выбери не больше {MAX_ITEMS} самых значимых для аудитории канала.\n"
            "Правила отбора:\n"
            "1. Берём только новости, где ИИ или роботы — суть события, а не упоминание вскользь.\n"
            "2. Приоритет: внедрение ИИ и роботов в образование любого уровня, в госуправление (любые страны), в управление компаниями; "
            "государственные программы и субсидии; новые методы обучения людей и роботов; заметные сдвиги в развитии ИИ.\n"
            "3. Не брать: рекламу курсов и продуктов, релизы гаджетов, военные новости, слухи, мелкие корпоративные пресс-релизы без общественного значения, "
            "инструкции и туториалы для программистов.\n"
            f"4. Не больше {MAX_PER_SECTION} новостей в одной рубрике, не больше {MAX_PER_SOURCE} от одного источника, без дублей одной темы.\n"
            f"5. Каждой выбранной новости назначь рубрику из списка:\n{sec_list}\n\n"
            'Формат ответа: {"picks": [{"n": номер, "section": "id рубрики", "why": "3-6 слов"}]}\n\n' + listing)
    try:
        data = parse_json(llm(system, user, 800))
        out = []
        for p in data.get("picks", []):
            n = int(p["n"]) - 1
            if 0 <= n < len(cands) and cands[n] not in out:
                i = cands[n]
                if p.get("section") in {s["id"] for s in SECTIONS}:
                    i["section"] = p["section"]
                out.append(i)
                log(f"  выбрано: {i['title'][:60]} — {p.get('why', '')}")
        return out[:MAX_ITEMS]
    except Exception as ex:
        log(f"  отбор моделью не удался ({ex}), отбираю по ключевым словам")
        return []


def article_text(link):
    """Полный текст статьи со страницы."""
    try:
        import trafilatura
        r = requests.get(link, headers=UA, timeout=20)
        t = trafilatura.extract(r.text, include_comments=False, include_tables=False) or ""
        return t[:ARTICLE_CHARS]
    except Exception as ex:
        log(f"  текст статьи не получен ({ex})")
        return ""


def llm_write(item):
    """Модель пишет самостоятельную заметку по полному тексту статьи. Возвращает (заголовок, текст) или None."""
    body_src = article_text(item["link"]) or item["summary"]
    if len(body_src) < 200:
        body_src = item["title"] + "\n" + item["summary"]
    system = ("Ты журналист и редактор. " + CHANNEL_ABOUT +
              " Пишешь по-русски: ясно, точно, без канцелярита, без рекламных интонаций и без англицизмов там, где есть русское слово. "
              "Стиль — деловая аналитическая заметка, как в хорошем отраслевом издании. Отвечай только JSON без пояснений.")
    user = (f"Напиши самостоятельную заметку для канала по материалу ниже. Заметка должна быть понятна без перехода по ссылке.\n"
            "Требования:\n"
            "- заголовок: до 80 знаков, информативный, по-русски, без кликбейта и без точки в конце;\n"
            f"- текст: {BODY_MIN}–{BODY_MAX} знаков, 2–3 абзаца, разделённых пустой строкой. Первый абзац — что произошло: кто, что, где, "
            "цифры и названия из материала. Второй — почему это важно и что это меняет для образования, госуправления или бизнеса; "
            "контекст, если он есть в материале. Третий (если нужен) — что дальше, ограничения, спорные моменты;\n"
            "- только факты из материала, ничего не додумывать; если материал на английском — не переводить дословно, а пересказать "
            "как русский журналист: имена и названия передавать по устоявшейся практике (Google, OpenAI, Microsoft остаются латиницей);\n"
            "- без фраз «читайте по ссылке», «подробнее на сайте», без обращения к читателю, без эмодзи, без markdown.\n"
            'Формат ответа: {"title": "...", "body": "..."}\n\n'
            f"Источник: {item['source']}\nЗаголовок оригинала: {item['title']}\n\nМатериал:\n{body_src}")
    try:
        data = parse_json(llm(system, user, 1500))
        title, body = data["title"].strip().rstrip("."), data["body"].strip()
        if len(title) < 10 or len(body) < 200:
            raise ValueError("слишком короткий ответ")
        return title, body
    except Exception as ex:
        log(f"  заметка не написана ({ex}), беру запасной вариант")
        return None


def build_posts(chosen):
    """Возвращает список постов: первый — шапка (текст), остальные — новости (текст + картинка)."""
    now = datetime.now(MSK)
    when = "Утренний" if now.hour < 14 else "Вечерний"
    months = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
    sec = {s["id"]: s for s in SECTIONS}
    counts = {}
    for i in chosen:
        counts[i["section"]] = counts.get(i["section"], 0) + 1
    head = f"<b>{html.escape(CHANNEL_TITLE)}</b>\n{when} выпуск, {now.day} {months[now.month - 1]} — {len(chosen)} {plural(len(chosen))}\n\n"
    head += "\n".join(f"{sec[k]['emoji']} {sec[k]['name']} — {counts[k]}" for k in [s["id"] for s in SECTIONS] if k in counts)
    posts = [{"text": head, "photo": None}]

    for i in chosen:
        written = llm_write(i) if llm_available() else None
        if written:
            title, body = written
        else:
            title, body = i["title"], i["summary"]
            if i["lang"] == "en":
                title, body = translate(title), translate(body)
        s = sec[i["section"]]
        link = html.escape(i["link"])
        caption = f"{s['emoji']} <b>{html.escape(title)}</b>\n\n"
        tail = f"\n<i>Источник: <a href=\"{link}\">{html.escape(i['source'])}</a></i>"
        room = 1024 - len(caption) - len(tail) - 8
        if body:
            caption += html.escape(clean(body, room) if len(body) > room else body) + "\n"
        caption += tail
        # Картинка: из ленты, иначе со страницы статьи
        photo = download_image(i["img"]) or download_image(page_image(i["link"]))
        if not photo:
            log(f"  без картинки: {i['title'][:60]}")
        posts.append({"text": caption, "photo": photo, "link": i["link"]})
    return posts


def plural(n):
    if n % 10 == 1 and n % 100 != 11:
        return "новость"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "новости"
    return "новостей"


def send(posts):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        log("Ключ бота или адрес канала не заданы — режим проверки, печатаю выпуск:\n")
        for p in posts:
            print(("[ФОТО] " if p.get("photo") else "[без фото] ") + p["text"] + "\n\n-----\n")
        return False
    api = f"https://api.telegram.org/bot{token}/"
    for p in posts:
        if p.get("photo"):
            r = requests.post(api + "sendPhoto", data={"chat_id": chat, "caption": p["text"], "parse_mode": "HTML"},
                              files={"photo": ("news.jpg", p["photo"], "image/jpeg")}, timeout=60)
            if not r.ok:
                log("  sendPhoto не прошёл, отправляю текстом:", r.text[:200])
        if not p.get("photo") or not r.ok:
            opts = {"is_disabled": False, "prefer_large_media": True, "show_above_text": True}
            if p.get("link"):
                opts["url"] = p["link"]
            else:
                opts = {"is_disabled": True}
            r = requests.post(api + "sendMessage", json={"chat_id": chat, "text": p["text"], "parse_mode": "HTML",
                                                         "link_preview_options": opts}, timeout=30)
            if not r.ok:
                log("Телеграм ответил ошибкой:", r.text)
                r.raise_for_status()
        time.sleep(3)  # чтобы не упереться в лимит Телеграма на частоту постов
    return True


def main():
    state = load_state()
    items = collect(state)
    log(f"\nВсего подходящих новостей: {len(items)}")
    chosen = []
    if llm_available():
        # Сначала грубый отбор по ключевым словам (широкий), потом модель выбирает лучшее
        wide = select(items, limit=CANDIDATES, per_section=CANDIDATES, per_source=4)
        chosen = llm_select(wide)
    if not chosen:
        chosen = select(items)
    if not chosen:
        log("Нечего публиковать.")
        return
    order = {s["id"]: n for n, s in enumerate(SECTIONS)}
    chosen.sort(key=lambda i: order[i["section"]])
    posts = build_posts(chosen)
    if send(posts):
        state["posted"].extend(i["link"] for i in chosen)
        save_state(state)
        log(f"Опубликовано новостей: {len(chosen)}")


if __name__ == "__main__":
    main()
