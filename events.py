# -*- coding: utf-8 -*-
"""
Афиша недели для канала «Технопульс · Образование».

По пятницам в вечернем выпуске публикует один пост: крупные очные и гибридные форумы и конференции
по ИИ, образованию, ИТ и робототехнике, которые пройдут на следующей неделе в России и странах БРИКС+.

Как работает:
  1. Модель с поиском по интернету ищет события на следующую неделю (плюс открытые календари конференций).
  2. Робот открывает страницу каждого события и проверяет, что оно там действительно есть. Что не подтвердилось — выбрасывает.
  3. Пост собирается из проверенного списка; модель пишет только короткое описание главного события.

Запуск: сам решает, что сегодня пятница и вечер (по Москве), иначе ничего не делает.
Для ручной проверки задайте переменную окружения FORCE_EVENTS=1.
Ключи те же, что у digest.py (TELEGRAM_*, OPENAI_* / ANTHROPIC_API_KEY, LLM_MODEL).
"""

import json, os, re, sys, html
from datetime import datetime, timedelta, date
import requests

import digest  # берём общие детали у основного робота
from digest import log, UA, MSK, parse_json, llm, page_image, download_image, article_text, send, CLAUDE_MODEL, is_day_off

# ============================================================
# НАСТРОЙКИ
# ============================================================

MAX_EVENTS = 12          # сколько событий максимум в афише
MIN_EVENTS = 3           # если подтверждённых событий меньше — афиша не публикуется
TOPICS = {"ai": "🧠", "edu": "🎓", "it": "💻", "robots": "🤖"}
COUNTRIES_TEXT = ("Россия и страны БРИКС+: Бразилия, Индия, Китай (включая Гонконг), ЮАР, Египет, Эфиопия, Иран, ОАЭ, Индонезия, "
                  "Саудовская Аравия, а также страны-партнёры: Казахстан, Узбекистан, Белоруссия, Турция, Нигерия, Малайзия, "
                  "Таиланд, Вьетнам, Куба, Боливия, Уганда")

# Открытые календари конференций — читаются как дополнительный материал.
CALENDARS = [
    "https://events.cnews.ru/",
    "https://ict2go.ru/events/",
    "https://www.tadviser.ru/index.php/Конференции",
    "https://conferenceindex.org/conferences/artificial-intelligence",
]

MONTHS_RU = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
MONTHS_SHORT = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
MONTHS_EN = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]


# ============================================================
# МЕХАНИКА
# ============================================================

def next_week():
    """Понедельник и воскресенье следующей недели (по Москве)."""
    today = datetime.now(MSK).date()
    monday = today + timedelta(days=(7 - today.weekday()) % 7 or 7)
    return monday, monday + timedelta(days=6)


def should_run():
    if os.environ.get("FORCE_EVENTS", "").strip():
        return True
    now = datetime.now(MSK)
    if is_day_off():
        log("Сегодня в России выходной или праздник — афиша не публикуется.")
        return False
    return now.weekday() == 4 and now.hour >= 14


def week_label(a, b):
    if a.month == b.month:
        return f"{a.day}–{b.day} {MONTHS_RU[a.month - 1]}"
    return f"{a.day} {MONTHS_RU[a.month - 1]} – {b.day} {MONTHS_RU[b.month - 1]}"


def date_label(start, end):
    try:
        a = date.fromisoformat(start[:10]); b = date.fromisoformat((end or start)[:10])
    except Exception:
        return start
    if a == b:
        return f"{a.day} {MONTHS_SHORT[a.month - 1]}"
    if a.month == b.month:
        return f"{a.day}–{b.day} {MONTHS_SHORT[a.month - 1]}"
    return f"{a.day} {MONTHS_SHORT[a.month - 1]} – {b.day} {MONTHS_SHORT[b.month - 1]}"


# ---------- поиск ----------

def web_search_available():
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()) or \
        (os.environ.get("OPENAI_API_KEY", "").strip() and not os.environ.get("OPENAI_BASE_URL", "").strip())


def llm_with_search(prompt, max_tokens=6000):
    """Запрос к модели со встроенным поиском по интернету (OpenAI или Claude)."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        r = requests.post("https://api.anthropic.com/v1/messages",
                          headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                          json={"model": os.environ.get("LLM_MODEL", "").strip() or CLAUDE_MODEL, "max_tokens": max_tokens,
                                "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}],
                                "messages": [{"role": "user", "content": prompt}]}, timeout=300)
        if not r.ok:
            raise RuntimeError(f"{r.status_code}: {r.text[:300]}")
        return "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text")
    key = os.environ["OPENAI_API_KEY"].strip()
    model = os.environ.get("LLM_MODEL", "").strip() or "gpt-4.1"
    body = {"model": model, "input": prompt, "tools": [{"type": "web_search"}], "max_output_tokens": max_tokens}
    if not model.startswith("gpt-4"):
        body["reasoning"] = {"effort": "low"}
    r = requests.post("https://api.openai.com/v1/responses",
                      headers={"Authorization": "Bearer " + key, "content-type": "application/json"}, json=body, timeout=300)
    if not r.ok:
        raise RuntimeError(f"{r.status_code}: {r.text[:300]}")
    out = []
    for item in r.json().get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    out.append(c.get("text", ""))
    return "".join(out)


def calendars_text():
    parts = []
    for u in CALENDARS:
        t = article_text(u)
        if t:
            parts.append(f"--- {u} ---\n{t[:6000]}")
    return "\n\n".join(parts)


def find_events(monday, sunday):
    period = f"с {monday.isoformat()} по {sunday.isoformat()} (понедельник–воскресенье)"
    schema = ('{"events": [{"name": "...", "start": "ГГГГ-ММ-ДД", "end": "ГГГГ-ММ-ДД", "city": "...", "country": "...", '
              '"format": "очно|гибрид", "topic": "ai|edu|it|robots", "url": "https://...", "blurb": "одна фраза до 160 знаков: для кого и о чём", '
              '"scale": "почему крупное: организатор, число участников, статус"}]}')
    rules = (f"Нужны только КРУПНЫЕ форумы, конференции, выставки, саммиты, которые проходят {period}, ОЧНО или в гибридном формате "
             f"(чисто онлайн-вебинары не нужны), в странах: {COUNTRIES_TEXT}. Темы: искусственный интеллект, образование и EdTech, "
             "информационные технологии и цифровизация, робототехника. Крупное — это федеральный или национальный уровень, "
             "международный статус, известный организатор (министерство, крупная компания, отраслевая ассоциация, ведущий вуз), "
             "сотни и тысячи участников. Митапы, вебинары, курсы, локальные встречи — не брать.\n"
             "Для каждого события нужна ссылка на официальную страницу события (не на новость о нём). Даты — точные. "
             "Если не уверен в датах или в существовании события — не включай. Лучше меньше, но точно.\n"
             f"Верни ТОЛЬКО JSON вида {schema} без пояснений.")
    events = []
    if web_search_available():
        for scope in ("в России", "в странах БРИКС+ за пределами России (в первую очередь Китай, Индия, ОАЭ, Казахстан, Бразилия, ЮАР, Турция, Индонезия)"):
            prompt = f"Найди через поиск в интернете крупные очные форумы и конференции по ИИ, образованию, ИТ и робототехнике {scope}, которые пройдут {period}.\n{rules}"
            try:
                data = parse_json(llm_with_search(prompt))
                found = data.get("events", [])
                log(f"Поиск ({scope[:20]}…): найдено {len(found)}")
                events += found
            except Exception as ex:
                log(f"  поиск не удался: {ex}")
    else:
        log("У этого провайдера нет поиска по интернету — работаю только по календарям")
    cal = calendars_text()
    if cal:
        prompt = (f"Ниже выдержки из открытых календарей конференций. Выбери из них события, которые проходят {period}.\n{rules}\n\n{cal}")
        try:
            data = parse_json(llm(("Ты редактор афиши. Отвечай только JSON."), prompt, 4000))
            found = data.get("events", [])
            log(f"Календари: найдено {len(found)}")
            events += found
        except Exception as ex:
            log(f"  разбор календарей не удался: {ex}")
    return events


# ---------- проверка ----------

def in_window(ev, monday, sunday):
    try:
        a = date.fromisoformat(ev["start"][:10]); b = date.fromisoformat((ev.get("end") or ev["start"])[:10])
    except Exception:
        return False
    return a <= sunday and b >= monday


def verify(ev):
    """Открывает страницу события и проверяет, что название на ней есть. Возвращает текст страницы или None."""
    url = (ev.get("url") or "").strip()
    if not url.startswith("http"):
        return None
    try:
        r = requests.get(url, headers=UA, timeout=25)
        if not r.ok:
            log(f"  не подтверждено ({r.status_code}): {ev['name'][:50]}")
            return None
        raw = r.text
        try:
            import trafilatura
            text = trafilatura.extract(raw, include_comments=False) or ""
        except Exception:
            text = ""
        low = (text + " " + re.sub(r"<[^>]+>", " ", raw[:200000])).lower()
        words = [w for w in re.findall(r"[\w-]{4,}", ev["name"].lower()) if w not in {"2026", "2027", "форум", "конференция", "conference", "forum", "summit", "international", "международный", "международная"}]
        hits = sum(1 for w in words if w in low)
        need = 1 if len(words) <= 2 else 2
        if hits < need:
            log(f"  не подтверждено (название не найдено): {ev['name'][:50]}")
            return None
        try:
            a = date.fromisoformat(ev["start"][:10])
            m_ok = MONTHS_EN[a.month - 1] in low or MONTHS_RU[a.month - 1][:4] in low or f"{a.day:02d}.{a.month:02d}" in low or f"-{a.month:02d}-" in low
            if not m_ok:
                log(f"  месяц на странице не найден, оставляю с осторожностью: {ev['name'][:50]}")
        except Exception:
            pass
        return text or low[:5000]
    except Exception as ex:
        log(f"  не подтверждено ({ex}): {ev['name'][:50]}")
        return None


def dedupe(events):
    seen, out = set(), []
    for ev in events:
        key = re.sub(r"\W+", "", (ev.get("name") or "").lower())[:40]
        if key and key not in seen:
            seen.add(key); out.append(ev)
    return out


# ---------- пост ----------

def main_event_blurb(ev, page_text):
    system = "Ты редактор афиши делового телеграм-канала об ИИ и образовании. Пишешь по-русски, ясно и без рекламных интонаций. Отвечай только JSON."
    user = (f"По странице события ниже напиши 2–3 предложения (до 400 знаков): что это за событие, кто организует и кто выступает, "
            f"почему на него стоит обратить внимание руководителям в образовании, госуправлении и бизнесе. Только факты со страницы.\n"
            f'Формат: {{"text": "..."}}\n\nСобытие: {ev["name"]}, {ev.get("city", "")}, {ev.get("country", "")}\n\n{page_text[:6000]}')
    try:
        return parse_json(llm(system, user, 800))["text"].strip()
    except Exception as ex:
        log(f"  описание главного события не написано ({ex})")
        return ev.get("blurb", "")


def build_post(events, monday, sunday):
    ru = [e for e in events if e.get("country", "").strip().lower() in ("россия", "russia", "рф")]
    world = [e for e in events if e not in ru]
    for lst in (ru, world):
        lst.sort(key=lambda e: e["start"])
    main = events[0]
    text = f"📅 <b>Афиша недели: ИИ, образование, ИТ и роботы</b>\n{week_label(monday, sunday)}\n\n"
    text += f"⭐ <b>Главное событие</b>\n<b>{html.escape(main['name'])}</b> — {date_label(main['start'], main.get('end'))}, {html.escape(main.get('city', ''))}"
    text += f" ({html.escape(main['country'])})" if main not in ru else ""
    text += f"\n{html.escape(main['_blurb'])}\n<a href=\"{html.escape(main['url'])}\">Страница события</a>\n"

    def line(e):
        emoji = TOPICS.get(e.get("topic", "it"), "💻")
        where = html.escape(e.get("city", ""))
        if e not in ru:
            where += f" ({html.escape(e.get('country', ''))})"
        fmt = " (гибрид)" if "гибрид" in (e.get("format") or "").lower() else ""
        return (f"{emoji} <b>{date_label(e['start'], e.get('end'))}</b> — <a href=\"{html.escape(e['url'])}\">{html.escape(e['name'])}</a>, "
                f"{where}{fmt}. {html.escape(e.get('blurb', ''))}\n")

    if ru:
        text += "\n🇷🇺 <b>Россия</b>\n" + "".join(line(e) for e in ru)
    if world:
        text += "\n🌍 <b>БРИКС+</b>\n" + "".join(line(e) for e in world)
    text += "\n<i>Даты и ссылки проверены по официальным страницам событий на момент публикации.</i>"
    return text[:4000]


def main():
    if not should_run():
        log("Не пятница-вечер, афиша не нужна.")
        return
    monday, sunday = next_week()
    log(f"Афиша на {monday} – {sunday}")
    found = dedupe(find_events(monday, sunday))
    log(f"Всего найдено: {len(found)}")
    verified = []
    for ev in found:
        if not all(ev.get(k) for k in ("name", "start", "url")):
            continue
        if not in_window(ev, monday, sunday):
            log(f"  вне недели: {ev['name'][:50]} ({ev.get('start')})")
            continue
        if "онлайн" in (ev.get("format") or "").lower() and "гибрид" not in (ev.get("format") or "").lower():
            continue
        page = verify(ev)
        if page:
            ev["_page"] = page
            verified.append(ev)
        if len(verified) >= MAX_EVENTS:
            break
    log(f"Подтверждено: {len(verified)}")
    if len(verified) < MIN_EVENTS:
        log("Подтверждённых событий мало, афишу не публикую.")
        return
    # Главное — первое по важности: сначала Россия, крупнее по описанию масштаба; оставляем порядок модели, но Россия впереди
    verified.sort(key=lambda e: 0 if e.get("country", "").lower() in ("россия", "russia", "рф") else 1)
    verified[0]["_blurb"] = main_event_blurb(verified[0], verified[0]["_page"])
    text = build_post(verified, monday, sunday)
    img = page_image(verified[0]["url"])
    img = img if img and download_image(img) else ""
    send([{"text": text, "image": img or None}])
    log("Афиша опубликована." if os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() else "")


if __name__ == "__main__":
    main()
