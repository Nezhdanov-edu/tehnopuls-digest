# -*- coding: utf-8 -*-
"""
Публикация во ВКонтакте. Робот зеркалит в сообщество ВК всё, что публикует в Телеграм:
новостные заметки с картинками, афишу и праздничные открытки.

Настройки (секреты GitHub):
  VK_TOKEN    — ключ доступа сообщества (Управление → Работа с API → Ключи доступа), с правами «Стена» и «Фотографии»
  VK_GROUP_ID — числовой ID сообщества, без минуса (например 123456789)
Если ключи не заданы, модуль ничего не делает, Телеграм продолжает работать как обычно.
"""

import os, re, io, html, time, sys
import requests

VK_MODE = "single"        # "single" — один пост на выпуск (галерея картинок + все заметки);
                          # "separate" — каждая заметка отдельным постом, как в Телеграме
API = "https://api.vk.com/method/"
V = "5.199"
UA = {"User-Agent": "Mozilla/5.0 TechnopulsDigest/2.0"}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def enabled():
    return bool(os.environ.get("VK_TOKEN", "").strip() and os.environ.get("VK_GROUP_ID", "").strip())


def call(method, **params):
    params.update({"access_token": os.environ["VK_TOKEN"].strip(), "v": V})
    r = requests.post(API + method, data=params, timeout=60)
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"{method}: {data['error'].get('error_msg')} (код {data['error'].get('error_code')})")
    return data["response"]


def plain(text_html):
    """Превращает HTML-разметку Телеграма в обычный текст для ВК: ссылки — в скобках после текста."""
    t = re.sub(r'<a href="([^"]+)">([^<]*)</a>', lambda m: f"{m.group(2)} ({html.unescape(m.group(1))})", text_html)
    t = re.sub(r"<[^>]+>", "", t)
    return html.unescape(t).strip()


def upload_photo(photo_bytes):
    gid = os.environ["VK_GROUP_ID"].strip()
    server = call("photos.getWallUploadServer", group_id=gid)["upload_url"]
    r = requests.post(server, files={"photo": ("news.jpg", photo_bytes, "image/jpeg")}, timeout=120).json()
    saved = call("photos.saveWallPhoto", group_id=gid, server=r["server"], photo=r["photo"], hash=r["hash"])[0]
    return f"photo{saved['owner_id']}_{saved['id']}"


def fetch_image(url):
    try:
        from digest import download_image
        return download_image(url)
    except Exception:
        return None


def wall_post(message, attachments=None):
    gid = os.environ["VK_GROUP_ID"].strip()
    kw = {"owner_id": f"-{gid}", "from_group": 1, "message": message[:15000]}
    if attachments:
        kw["attachments"] = ",".join(attachments)
    return call("wall.post", **kw)["post_id"]


def publish(posts):
    """posts — тот же список, что уходит в Телеграм: [{"text": html, "image": url|None, "photo_bytes": bytes|None}, ...]"""
    if not enabled():
        return False
    try:
        items = []
        for p in posts:
            photo = p.get("photo_bytes") or (fetch_image(p["image"]) if p.get("image") else None)
            att = None
            if photo:
                try:
                    att = upload_photo(photo)
                except Exception as ex:
                    log(f"  ВК: картинка не загрузилась ({ex})")
            items.append((plain(p["text"]), att))

        if VK_MODE == "separate" or len(items) == 1:
            for text, att in items:
                wall_post(text, [att] if att else None)
                time.sleep(2)
        else:
            # Первый пост — шапка выпуска; остальные — заметки. Собираем в один пост.
            head = items[0][0]
            body = "\n\n— — —\n\n".join(text for text, _ in items[1:])
            atts = [att for _, att in items[1:] if att][:10]   # ВК разрешает до 10 вложений
            wall_post(head + "\n\n" + body, atts or None)
        log(f"ВК: опубликовано ({'отдельными постами' if VK_MODE == 'separate' else 'одним постом'})")
        return True
    except Exception as ex:
        log(f"ВК: публикация не удалась ({ex})")
        return False
