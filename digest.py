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

Формат публикации: шапка выпуска, затем каждая новость отдельным постом: картинка сверху, под ней
самостоятельная заметка на 1200–2000 знаков. Робот сначала читает полные тексты статей-кандидатов,
затем языковая модель отбирает лучшие и пишет по каждой краткий аналитический пересказ на русском.

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

MAX_ITEMS = 8            # размер выпуска; пересчитывается из QUOTAS ниже
MAX_PER_SECTION = 4      # сколько максимум в одной рубрике
MAX_PER_SOURCE = 2       # не больше N новостей от одного издания
LOOKBACK_HOURS = 30      # брать новости не старше N часов
CHANNEL_TITLE = "Технопульс · Образование"
SUMMARY_LEN = 260        # длина описания из RSS (используется при отборе и как запасной вариант)
BODY_MIN, BODY_MAX = 1200, 2000 # длина заметки, знаков (пост в Телеграме — до 4096)
MIN_ARTICLE = 600        # если со страницы не удалось прочитать хотя бы столько знаков, новость не берётся
CLAUDE_MODEL = "claude-sonnet-4-6"      # модель Claude по умолчанию
ARTICLE_CHARS = 7000     # сколько знаков статьи отдавать модели

CHANNEL_ABOUT = ("Телеграм-канал о том, как искусственный интеллект и робототехника меняют образование всех уровней "
                 "(школа, СПО, вузы, корпоративное обучение, обучение взрослых), государственное управление "
                 "(города, регионы, страны, госпрограммы и субсидии), управление компаниями и общество в целом, "
                 "а также об обучении роботов и развитии ИИ. Аудитория — руководители образовательных организаций, "
                 "чиновники, преподаватели, HR и руководители компаний в России.")

# Ленты. lang: ru/en; country — страна издания (для квот и подписи).
# Квоты выпуска считаются по стране издания: ru — Россия, us — США, всё остальное — «другие страны».
FEEDS = [
    # --- Россия ---
    {"name": "Учительская газета",  "url": "https://ug.ru/feed/",                                                  "lang": "ru", "country": "Россия"},
    {"name": "Педсовет",            "url": "https://pedsovet.org/rss",                                             "lang": "ru", "country": "Россия"},
    {"name": "Вести образования",   "url": "https://vogazeta.ru/rss",                                              "lang": "ru", "country": "Россия"},
    {"name": "Хабр · Образование",  "url": "https://habr.com/ru/rss/hubs/edu/articles/all/?fl=ru",                 "lang": "ru", "country": "Россия"},
    {"name": "Хабр · ИИ",           "url": "https://habr.com/ru/rss/hubs/artificial_intelligence/articles/all/?fl=ru", "lang": "ru", "country": "Россия"},
    {"name": "D-Russia",            "url": "https://d-russia.ru/feed",                                             "lang": "ru", "country": "Россия"},
    {"name": "TAdviser",            "url": "https://www.tadviser.ru/xml/tadviser.xml",                             "lang": "ru", "country": "Россия"},
    {"name": "ComNews",             "url": "https://www.comnews.ru/rss",                                           "lang": "ru", "country": "Россия"},
    {"name": "CNews",               "url": "https://www.cnews.ru/inc/rss/news.xml",                                "lang": "ru", "country": "Россия"},
    {"name": "Ведомости",           "url": "https://www.vedomosti.ru/rss/rubric/technology",                       "lang": "ru", "country": "Россия"},
    {"name": "Хайтек",              "url": "https://hightech.fm/feed",                                             "lang": "ru", "country": "Россия"},
    {"name": "Naked Science",       "url": "https://naked-science.ru/feed",                                        "lang": "ru", "country": "Россия"},
    {"name": "РБК",                 "url": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",                    "lang": "ru", "country": "Россия"},
    {"name": "ТАСС",                "url": "https://tass.ru/rss/v2.xml",                                           "lang": "ru", "country": "Россия"},
    {"name": "РИА Новости",         "url": "https://ria.ru/export/rss2/archive/index.xml",                         "lang": "ru", "country": "Россия"},
    {"name": "Российская газета",   "url": "https://rg.ru/xml/index.xml",                                          "lang": "ru", "country": "Россия"},
    {"name": "Известия",            "url": "https://iz.ru/xml/rss/all.xml",                                        "lang": "ru", "country": "Россия"},
    {"name": "Интерфакс",           "url": "https://www.interfax.ru/rss.asp",                                      "lang": "ru", "country": "Россия"},
    {"name": "Коммерсантъ",         "url": "https://www.kommersant.ru/RSS/news.xml",                               "lang": "ru", "country": "Россия"},
    # --- США ---
    {"name": "EdSurge",             "url": "https://www.edsurge.com/articles_rss",                                 "lang": "en", "country": "США"},
    {"name": "eSchool News",        "url": "https://www.eschoolnews.com/feed/",                                    "lang": "en", "country": "США"},
    {"name": "EdTech Magazine",     "url": "https://edtechmagazine.com/k12/rss.xml",                               "lang": "en", "country": "США"},
    {"name": "EdTech Magazine",     "url": "https://edtechmagazine.com/higher/rss.xml",                            "lang": "en", "country": "США"},
    {"name": "Inside Higher Ed",    "url": "https://www.insidehighered.com/rss.xml",                               "lang": "en", "country": "США"},
    {"name": "Hechinger Report",    "url": "https://hechingerreport.org/feed/",                                    "lang": "en", "country": "США"},
    {"name": "The Conversation US", "url": "https://theconversation.com/us/education/articles.atom",               "lang": "en", "country": "США"},
    {"name": "Google for Education", "url": "https://blog.google/outreach-initiatives/education/rss/",            "lang": "en", "country": "США"},
    {"name": "Training Industry",   "url": "https://trainingindustry.com/feed/",                                   "lang": "en", "country": "США"},
    {"name": "Chief Learning Officer", "url": "https://www.chieflearningofficer.com/feed/",                        "lang": "en", "country": "США"},
    {"name": "Nextgov",             "url": "https://www.nextgov.com/rss/all/",                                     "lang": "en", "country": "США"},
    {"name": "FedScoop",            "url": "https://fedscoop.com/feed/",                                           "lang": "en", "country": "США"},
    {"name": "StateScoop",          "url": "https://statescoop.com/feed/",                                         "lang": "en", "country": "США"},
    {"name": "TechCrunch",          "url": "https://techcrunch.com/category/artificial-intelligence/feed/",        "lang": "en", "country": "США"},
    {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/feed/",                             "lang": "en", "country": "США"},
    {"name": "MIT News",            "url": "https://news.mit.edu/topic/mitartificial-intelligence2-rss.xml",       "lang": "en", "country": "США"},
    {"name": "IEEE Spectrum",       "url": "https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss",    "lang": "en", "country": "США"},
    {"name": "IEEE Spectrum",       "url": "https://spectrum.ieee.org/feeds/topic/robotics.rss",                   "lang": "en", "country": "США"},
    {"name": "The Robot Report",    "url": "https://www.therobotreport.com/feed/",                                 "lang": "en", "country": "США"},
    {"name": "Google AI",           "url": "https://blog.google/technology/ai/rss/",                               "lang": "en", "country": "США"},
    {"name": "HR Dive",             "url": "https://www.hrdive.com/feeds/news/",                                   "lang": "en", "country": "США"},
    # --- Другие страны ---
    {"name": "BBC",                 "url": "https://feeds.bbci.co.uk/news/technology/rss.xml",                     "lang": "en", "country": "Великобритания"},
    {"name": "UKAuthority",         "url": "https://www.ukauthority.com/rss",                                      "lang": "en", "country": "Великобритания"},
    {"name": "FE News",             "url": "https://www.fenews.co.uk/feed/",                                       "lang": "en", "country": "Великобритания"},
    {"name": "Cities Today",        "url": "https://cities-today.com/feed/",                                       "lang": "en", "country": "Великобритания"},
    {"name": "EdTech Innovation Hub", "url": "https://www.edtechinnovationhub.com/news?format=rss",                "lang": "en", "country": "Великобритания"},
    {"name": "The Conversation UK", "url": "https://theconversation.com/uk/education/articles.atom",               "lang": "en", "country": "Великобритания"},
    {"name": "The Conversation UK", "url": "https://theconversation.com/uk/technology/articles.atom",              "lang": "en", "country": "Великобритания"},
    {"name": "Euronews",            "url": "https://www.euronews.com/rss?level=vertical&name=next",                "lang": "en", "country": "ЕС"},
    {"name": "France 24",           "url": "https://www.france24.com/en/rss",                                      "lang": "en", "country": "Франция"},
    {"name": "Robohub",             "url": "https://robohub.org/feed/",                                            "lang": "en", "country": "Швейцария"},
    {"name": "The Conversation AU", "url": "https://theconversation.com/au/education/articles.atom",               "lang": "en", "country": "Австралия"},
    {"name": "The Conversation AU", "url": "https://theconversation.com/au/technology/articles.atom",              "lang": "en", "country": "Австралия"},
    {"name": "ABC News",            "url": "https://www.abc.net.au/news/feed/2942460/rss.xml",                     "lang": "en", "country": "Австралия"},
    {"name": "The Conversation CA", "url": "https://theconversation.com/ca/education/articles.atom",               "lang": "en", "country": "Канада"},
    {"name": "CBC",                 "url": "https://www.cbc.ca/webfeed/rss/rss-technology",                        "lang": "en", "country": "Канада"},
    {"name": "The Conversation Africa", "url": "https://theconversation.com/africa/education/articles.atom",       "lang": "en", "country": "Африка"},
    {"name": "TechCabal",           "url": "https://techcabal.com/feed/",                                          "lang": "en", "country": "Нигерия"},
    {"name": "South China Morning Post", "url": "https://www.scmp.com/rss/36/feed",                                "lang": "en", "country": "Гонконг"},
    {"name": "Global Times",        "url": "https://www.globaltimes.cn/rss/outbrain.xml",                          "lang": "en", "country": "Китай"},
    {"name": "Nikkei Asia",         "url": "https://asia.nikkei.com/rss/feed/nar",                                 "lang": "en", "country": "Япония"},
    {"name": "The Japan Times",     "url": "https://www.japantimes.co.jp/feed/",                                   "lang": "en", "country": "Япония"},
    {"name": "The Korea Herald",    "url": "https://www.koreaherald.com/rss/newsAll",                              "lang": "en", "country": "Южная Корея"},
    {"name": "Al Jazeera",          "url": "https://www.aljazeera.com/xml/rss/all.xml",                            "lang": "en", "country": "Катар"},
    {"name": "Anadolu",             "url": "https://www.aa.com.tr/en/rss/default?cat=science-technology",          "lang": "en", "country": "Турция"},
    {"name": "Mexico News Daily",   "url": "https://mexiconewsdaily.com/feed/",                                    "lang": "en", "country": "Мексика"},
    {"name": "Tengrinews",          "url": "https://tengrinews.kz/news.rss",                                       "lang": "ru", "country": "Казахстан"},
    {"name": "Kazinform",           "url": "https://www.inform.kz/rss/rus.xml",                                    "lang": "ru", "country": "Казахстан"},
    {"name": "Gazeta.uz",           "url": "https://www.gazeta.uz/ru/rss/",                                        "lang": "ru", "country": "Узбекистан"},
    # --- БРИКС+ ---
    {"name": "Business Standard",   "url": "https://www.business-standard.com/rss/technology-108.rss",             "lang": "en", "country": "Индия"},
    {"name": "NDTV",                "url": "https://feeds.feedburner.com/gadgets360-latest",                       "lang": "en", "country": "Индия"},
    {"name": "Scroll.in",           "url": "https://feeds.feedburner.com/ScrollinArticles.rss",                    "lang": "en", "country": "Индия"},
    {"name": "Inc42",               "url": "https://inc42.com/feed/",                                              "lang": "en", "country": "Индия"},
    {"name": "Medianama",           "url": "https://www.medianama.com/feed/",                                      "lang": "en", "country": "Индия"},
    {"name": "TechNode",            "url": "https://technode.com/feed/",                                           "lang": "en", "country": "Китай"},
    {"name": "Pandaily",            "url": "https://pandaily.com/feed/",                                           "lang": "en", "country": "Китай"},
    {"name": "Sixth Tone",          "url": "https://www.sixthtone.com/rss",                                        "lang": "en", "country": "Китай"},
    {"name": "Brazil Reports",      "url": "https://brazilreports.com/feed/",                                      "lang": "en", "country": "Бразилия"},
    {"name": "The Rio Times",       "url": "https://www.riotimesonline.com/feed/",                                 "lang": "en", "country": "Бразилия"},
    {"name": "TechCentral",         "url": "https://techcentral.co.za/feed/",                                      "lang": "en", "country": "ЮАР"},
    {"name": "IOL",                 "url": "https://www.iol.co.za/rss",                                            "lang": "en", "country": "ЮАР"},
    {"name": "Egypt Independent",   "url": "https://egyptindependent.com/feed/",                                   "lang": "en", "country": "Египет"},
    {"name": "Nairametrics",        "url": "https://nairametrics.com/feed/",                                       "lang": "en", "country": "Нигерия"},
    {"name": "Saudi Gazette",       "url": "https://saudigazette.com.sa/rssFeed/74",                               "lang": "en", "country": "Саудовская Аравия"},
    {"name": "Antara",              "url": "https://en.antaranews.com/rss/news.xml",                               "lang": "en", "country": "Индонезия"},
    {"name": "VnExpress",           "url": "https://e.vnexpress.net/rss/news.rss",                                 "lang": "en", "country": "Вьетнам"},
    {"name": "New Straits Times",   "url": "https://www.nst.com.my/feed",                                          "lang": "en", "country": "Малайзия"},
    {"name": "Free Malaysia Today", "url": "https://www.freemalaysiatoday.com/feed/",                              "lang": "en", "country": "Малайзия"},
    # --- СНГ ---
    {"name": "Kursiv",              "url": "https://kz.kursiv.media/feed/",                                        "lang": "ru", "country": "Казахстан"},
    {"name": "Digital Business",    "url": "https://digitalbusiness.kz/feed/",                                     "lang": "ru", "country": "Казахстан"},
    {"name": "Podrobno.uz",         "url": "https://podrobno.uz/rss/",                                             "lang": "ru", "country": "Узбекистан"},
    {"name": "24.kg",               "url": "https://24.kg/rss/",                                                   "lang": "ru", "country": "Киргизия"},
    {"name": "News.am",             "url": "https://news.am/rus/rss/",                                             "lang": "ru", "country": "Армения"},
    {"name": "Trend",               "url": "https://www.trend.az/feeds/index.rss",                                 "lang": "en", "country": "Азербайджан"},
    {"name": "БелТА",               "url": "https://www.belta.by/rss",                                             "lang": "ru", "country": "Белоруссия"},
    {"name": "Onliner",             "url": "https://www.onliner.by/feed",                                          "lang": "ru", "country": "Белоруссия"},
]

# Квоты выпуска по странам изданий. Сумма — это и есть размер выпуска.
QUOTAS = {"ru": 2, "us": 1, "uk": 1, "world": 4}
# Внутри группы «world» приоритет: БРИКС+ → СНГ → остальные страны.
BRICS = {"Бразилия", "Индия", "Китай", "Гонконг", "ЮАР", "Египет", "Эфиопия", "Иран", "ОАЭ", "Индонезия", "Саудовская Аравия",
         "Нигерия", "Турция", "Казахстан", "Узбекистан", "Белоруссия", "Малайзия", "Таиланд", "Вьетнам", "Куба", "Боливия", "Уганда"}
CIS = {"Казахстан", "Узбекистан", "Белоруссия", "Киргизия", "Таджикистан", "Армения", "Азербайджан", "Туркмения", "Молдавия"}
GROUP_BONUS = {"БРИКС+": 10, "СНГ": 5, "другие": 0}
CANDIDATES_PER_REGION = {"ru": 10, "us": 8, "uk": 8, "world": 18}   # сколько кандидатов из каждой группы показать модели
MAX_ITEMS = sum(QUOTAS.values())


def region(feed):
    return {"Россия": "ru", "США": "us", "Великобритания": "uk"}.get(feed.get("country", ""), "world")


def group(country):
    return "БРИКС+" if country in BRICS else "СНГ" if country in CIS else "другие"


REGION_NAME = {"ru": "Россия", "us": "США", "uk": "Великобритания", "world": "остальной мир"}

# Слова-приоритеты: внедрение ИИ (а не просто разговоры о нём) поднимает новость в отборе.
FOCUS_WORDS = ["внедр", "запуст", "запущен", "пилот", "внедрен", "переход", "стартовал", "начал использ", "начала использ",
               "применя", "интегрир", "оснаст", "оснащ", "развёрн", "разверн",
               "implement", "deploy", "rollout", "roll out", "rolled out", "adopt", "launch", "pilot", "introduc",
               "integrat", "equip", "in use", "put to use", "goes live", "brings ai", "bringing ai"]

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
            score += 12 if section == "edu" else 8 if section == "gov" else 5 if section in ("biz", "robots") else 0
            score += 5 if has(f" {title} ", CORE_WORDS) else 0
            score += 8 if has(text, FOCUS_WORDS) else 0          # внедрение — в приоритете
            grp = group(f.get("country", ""))
            if region(f) == "world":
                score += GROUP_BONUS[grp]                            # БРИКС+ и СНГ — выше остальных стран
            items.append({"title": title, "link": link, "summary": summary, "source": f["name"], "lang": f["lang"],
                          "country": f.get("country", ""), "region": region(f), "group": grp,
                          "section": section, "date": date, "score": score, "img": entry_image(e)})
            seen_titles.add(key)
            kept += 1
        log(f"{f['name']}: {len(entries)} в ленте, подошло {kept}")
    return items


def select(items, limit=None, per_section=None, per_source=None, quotas=None):
    """Отбор по очкам с учётом квот по странам, рубрик и источников."""
    limit, per_section, per_source = limit or MAX_ITEMS, per_section or MAX_PER_SECTION, per_source or MAX_PER_SOURCE
    quotas = quotas or QUOTAS
    items.sort(key=lambda i: -i["score"])
    chosen, per, per_src, per_reg = [], {}, {}, {}

    def ok(i):
        return (i not in chosen and per.get(i["section"], 0) < per_section and per_src.get(i["source"], 0) < per_source
                and per_reg.get(i["region"], 0) < quotas.get(i["region"], 0))

    def take(i):
        chosen.append(i)
        per[i["section"]] = per.get(i["section"], 0) + 1
        per_src[i["source"]] = per_src.get(i["source"], 0) + 1
        per_reg[i["region"]] = per_reg.get(i["region"], 0) + 1

    for i in items:
        if len(chosen) >= limit:
            break
        if ok(i):
            take(i)
    order = {s["id"]: n for n, s in enumerate(SECTIONS)}
    chosen.sort(key=lambda i: (order[i["section"]], -i["score"]))
    return chosen[:limit]


def candidates(items):
    """Широкий список кандидатов: по CANDIDATES_PER_REGION лучших из каждой группы стран."""
    q = CANDIDATES_PER_REGION
    return select(items, limit=sum(q.values()), per_section=sum(q.values()), per_source=3, quotas=q)


def enforce_quotas(picked, pool):
    """Приводит выбор модели к квотам: лишнее убирает, недостающее добирает из кандидатов по очкам."""
    out, per_reg, per_src, per_sec = [], {}, {}, {}

    def fits(i):
        return (per_reg.get(i["region"], 0) < QUOTAS[i["region"]] and per_src.get(i["source"], 0) < MAX_PER_SOURCE
                and per_sec.get(i["section"], 0) < MAX_PER_SECTION)

    def add(i):
        out.append(i)
        per_reg[i["region"]] = per_reg.get(i["region"], 0) + 1
        per_src[i["source"]] = per_src.get(i["source"], 0) + 1
        per_sec[i["section"]] = per_sec.get(i["section"], 0) + 1

    for i in picked:
        if fits(i):
            add(i)
    for i in sorted(pool, key=lambda i: -i["score"]):
        if i not in out and fits(i):
            add(i)
            log(f"  добрано по квоте ({i['region']}, {i['country']}): {i['title'][:60]}")
    return out


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
                                "system": system, "messages": [{"role": "user", "content": user}]}, timeout=180)
        if not r.ok:
            raise RuntimeError(f"{r.status_code}: {r.text[:300]}")
        return "".join(b.get("text", "") for b in r.json()["content"])
    key = os.environ["OPENAI_API_KEY"].strip()
    base = (os.environ.get("OPENAI_BASE_URL", "").strip() or "https://api.openai.com/v1").rstrip("/")
    headers = {"Authorization": "Bearer " + key, "content-type": "application/json"}
    if os.environ.get("OPENAI_PROJECT", "").strip():      # для YandexGPT сюда передаётся ID каталога
        headers["OpenAI-Project"] = os.environ["OPENAI_PROJECT"].strip()
    model = os.environ.get("LLM_MODEL", "").strip() or "gpt-4.1"
    body = {"model": model, "max_completion_tokens": max_tokens + 6000, "reasoning_effort": "low",
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    r = requests.post(base + "/chat/completions", headers=headers, json=body, timeout=240)
    if r.status_code == 400 and "reasoning" in r.text:               # модель без режима размышлений (gpt-4.1 и т.п.)
        body.pop("reasoning_effort", None)
        r = requests.post(base + "/chat/completions", headers=headers, json=body, timeout=240)
    if r.status_code == 400 and "max_completion_tokens" in r.text:   # старые OpenAI-совместимые сервисы знают только max_tokens
        body["max_tokens"] = body.pop("max_completion_tokens")
        body.pop("reasoning_effort", None)
        r = requests.post(base + "/chat/completions", headers=headers, json=body, timeout=240)
    if not r.ok:
        raise RuntimeError(f"{r.status_code}: {r.text[:300]}")
    return r.json()["choices"][0]["message"]["content"] or ""


def parse_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)


def llm_select(items):
    """Модель выбирает новости в выпуск из списка кандидатов и назначает рубрику."""
    cands = items
    sec_list = "\n".join(f'  "{s["id"]}" — {s["name"]}' for s in SECTIONS)
    reg_name = REGION_NAME
    def tag(i):
        return f"{i['country']}, {i['source']}" + (f", группа {i['group']}" if i["region"] == "world" else "")
    listing = "\n\n".join(f"[{n}] ({reg_name[i['region']]}: {tag(i)}) {i['title']}\n{(i.get('text') or i['summary'])[:500]}"
                          for n, i in enumerate(cands, 1))
    system = ("Ты выпускающий редактор. " + CHANNEL_ABOUT + " Отвечай только JSON без пояснений.")
    quota_text = ", ".join(f"{reg_name[r]} — {n}" for r, n in QUOTAS.items())
    user = (f"Ниже {len(cands)} новостей-кандидатов, у каждой указана страна издания. Собери выпуск ровно из {MAX_ITEMS} новостей.\n"
            f"Жёсткие квоты по стране ИЗДАНИЯ (не по стране события): {quota_text}. Квоты обязательны.\n"
            "Внутри группы «остальной мир» приоритет стран: сначала БРИКС+ (Китай, Индия, Бразилия, ЮАР, Египет, ОАЭ, Иран, Индонезия, "
            "Саудовская Аравия, Турция, Нигерия и др.), затем СНГ (Казахстан, Узбекистан, Белоруссия, Киргизия, Армения, Азербайджан и др.), "
            "затем все прочие страны. При равной значимости новости бери из более приоритетной группы.\n"
            "Приоритеты отбора (по убыванию):\n"
            "1. Внедрение ИИ в образование: конкретные школы, колледжи, вузы, ведомства, компании, которые запустили ИИ-инструменты "
            "в обучении, новые учебные программы и методы с ИИ, результаты и оценки таких внедрений.\n"
            "2. Внедрение ИИ в госуправление и в управление компаниями: запущенные системы, госпрограммы, субсидии, регулирование с "
            "практическими последствиями.\n"
            "3. Обучение роботов и роботы в образовании.\n"
            "4. Значимые сдвиги в развитии ИИ и его влиянии на общество.\n"
            "Конкретное внедрение ценнее общих рассуждений, исследований мнений и прогнозов.\n"
            "Не брать: рекламу курсов и продуктов, релизы гаджетов, военные новости, слухи, мелкие пресс-релизы без общественного значения, "
            "инструкции для программистов.\n"
            f"Не больше {MAX_PER_SECTION} новостей в одной рубрике, не больше {MAX_PER_SOURCE} от одного источника, без дублей одной темы.\n"
            f"Каждой выбранной новости назначь рубрику из списка:\n{sec_list}\n\n"
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
                log(f"  выбрано ({i['region']}, {i['country']}, {i['source']}): {i['title'][:60]} — {p.get('why', '')}")
        return enforce_quotas(out, cands)
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
    """Модель пишет самостоятельную статью по полному тексту материала. Возвращает (заголовок, текст) или None."""
    body_src = item.get("text") or ""
    if len(body_src) < MIN_ARTICLE:
        log("  текста статьи нет, пропускаю")
        return None
    system = ("Ты журналист и редактор. " + CHANNEL_ABOUT +
              " Пишешь по-русски: ясно, точно, живым деловым языком, без канцелярита, без рекламных интонаций и без англицизмов там, "
              "где есть русское слово. Стиль — аналитическая заметка хорошего отраслевого издания, которую читают целиком в Телеграме. "
              "Отвечай только JSON без пояснений.")
    user = (f"Напиши по материалу ниже самостоятельную краткую статью для канала. Читатель должен полностью понять суть, "
            "не открывая первоисточник.\n"
            "Требования:\n"
            "- заголовок: до 80 знаков, информативный, по-русски, без кликбейта и без точки в конце;\n"
            f"- текст: {BODY_MIN}–{BODY_MAX} знаков, 4–6 абзацев, разделённых пустой строкой, без подзаголовков и списков.\n"
            "  1) Лид: суть события в двух-трёх предложениях — кто, что, где, когда.\n"
            "  2) Подробности: конкретика из материала — цифры, названия, механика решения, сроки, участники, цитаты (в пересказе).\n"
            "  3) Контекст и значение: почему это важно, что это меняет для образования, госуправления или бизнеса, "
            "как соотносится с тем, что уже известно из материала.\n"
            "  4) Что дальше: планы, ограничения, риски, спорные моменты — только если они есть в материале;\n"
            "- только факты из материала, ничего не додумывать и не добавлять извне; если чего-то в материале нет — не писать об этом;\n"
            "- если материал на английском — не переводить дословно, а пересказать как русский журналист: имена и названия передавать "
            "по устоявшейся практике (Google, OpenAI, Microsoft остаются латиницей, должности и организации — по-русски);\n"
            "- без фраз «читайте по ссылке», «подробнее на сайте», «в статье говорится», без обращения к читателю, без эмодзи, без markdown.\n"
            'Формат ответа: {"title": "...", "body": "..."}\n\n'
            f"Источник: {item['source']}\nЗаголовок оригинала: {item['title']}\n\nМатериал:\n{body_src}")
    try:
        data = parse_json(llm(system, user, 2500))
        title, body = data["title"].strip().rstrip("."), data["body"].strip()
        if len(title) < 10 or len(body) < 500:
            raise ValueError("слишком короткий ответ")
        return title, body
    except Exception as ex:
        log(f"  заметка не написана ({ex})")
        return None


def read_articles(items):
    """Читает полные тексты статей у кандидатов (параллельно) и оставляет только те, где текст удалось получить."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as ex:
        texts = list(ex.map(lambda i: article_text(i["link"]), items))
    ok = []
    for i, t in zip(items, texts):
        if len(t) >= MIN_ARTICLE:
            i["text"] = t
            ok.append(i)
    log(f"Прочитано полных текстов: {len(ok)} из {len(items)}")
    return ok


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
    posts = [{"text": head, "image": None}]

    written_n = 0
    for i in chosen:
        written = llm_write(i) if llm_available() else None
        if written:
            title, body = written
            written_n += 1
        else:
            if llm_available():
                continue  # без нормальной заметки новость в выпуск не идёт
            title, body = i["title"], i["summary"]
            if i["lang"] == "en":
                title, body = translate(title), translate(body)
        i["done"] = True
        s = sec[i["section"]]
        link = html.escape(i["link"])
        tail = f"\n\n<i>Источник: <a href=\"{link}\">{html.escape(i['source'])}</a> ({html.escape(i['country'])})</i>"
        text = f"{s['emoji']} <b>{html.escape(title)}</b>\n\n"
        room = 4000 - len(text) - len(tail)
        text += html.escape(clean(body, room) if len(body) > room else body) + tail
        # Картинка: из ленты, иначе со страницы статьи. Проверяем, что она скачивается и это нормальное фото.
        img_url = i["img"] if download_image(i["img"]) else ""
        if not img_url:
            og = page_image(i["link"])
            img_url = og if download_image(og) else ""
        if not img_url:
            log(f"  без картинки: {i['title'][:60]}")
        posts.append({"text": text, "image": img_url, "link": i["link"]})
    log(f"Заметок написано моделью: {written_n} из {len(chosen)}")
    chosen[:] = [i for i in chosen if i.get("done")]
    # Пересобираем шапку по фактическому составу выпуска
    counts = {}
    for i in chosen:
        counts[i["section"]] = counts.get(i["section"], 0) + 1
    head = f"<b>{html.escape(CHANNEL_TITLE)}</b>\n{when} выпуск, {now.day} {months[now.month - 1]} — {len(chosen)} {plural(len(chosen))}\n\n"
    head += "\n".join(f"{sec[k]['emoji']} {sec[k]['name']} — {counts[k]}" for k in [s["id"] for s in SECTIONS] if k in counts)
    posts[0]["text"] = head
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
            print(("[ФОТО] " if p.get("image") else "[без фото] ") + p["text"] + "\n\n-----\n")
        return False
    api = f"https://api.telegram.org/bot{token}/"
    for p in posts:
        if p.get("image"):
            opts = {"is_disabled": False, "url": p["image"], "prefer_large_media": True, "show_above_text": True}
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
        prov = "Claude " + (os.environ.get("LLM_MODEL", "").strip() or CLAUDE_MODEL) if os.environ.get("ANTHROPIC_API_KEY", "").strip() \
            else "OpenAI-совместимый " + (os.environ.get("LLM_MODEL", "").strip() or "gpt-4.1")
        log(f"Модель: {prov}")
        # Грубый отбор по ключевым словам, чтение полных текстов, затем модель выбирает лучшее из прочитанного
        wide = candidates(items)
        wide = read_articles(wide)
        chosen = llm_select(wide)
    else:
        log("Ключ модели не задан — работаю в упрощённом режиме (машинный перевод, обрывки RSS)")
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
