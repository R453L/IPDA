import base64
import html as htmllib
import json
import os
import random
import re
import sys
import time
import urllib.parse

import requests
from playwright.sync_api import sync_playwright

POLL_KEY = os.environ["POLLINATIONS_API_KEY"]
TG_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TG_CHAT = os.environ["TELEGRAM_CHAT_ID"]
REVIEW_MODE = os.environ.get("REVIEW_MODE", "1") == "1"

BASE = "https://raw.githubusercontent.com/AhmedBaset/hadith-json/v1.2.0/db/by_book/"
BOOKS = {
    "nawawi40": {"path": "forties/nawawi40.json", "name": "আন-নববীর ৪০ হাদিস", "weight": 2},
    "bukhari": {"path": "the_9_books/bukhari.json", "name": "সহীহ বুখারী", "weight": 3},
    "muslim": {"path": "the_9_books/muslim.json", "name": "সহীহ মুসলিম", "weight": 3},
}
CHAT_URL = "https://gen.pollinations.ai/v1/chat/completions"
STATE_FILE = "posted.json"
CARD_MAX_CHARS = 380

SCENES = [
    "peaceful mosque silhouette at dawn, soft golden light, deep blue sky",
    "desert dunes under a starry night sky, calm and serene",
    "quiet garden with a stone path at sunrise, soft mist",
    "calm sea at sunset, golden reflections, peaceful",
    "misty mountains at dawn, soft light, tranquil",
    "glowing lantern on a wooden table at night, warm light, dark blue background",
    "minaret and crescent moon in a twilight sky, serene",
    "green fields after rain, soft morning light, peaceful",
]

SYS_TRANSLATE = (
    "You are a careful Islamic translator. Translate the given hadith into "
    "natural, simple Bengali. Rules: translate faithfully, never add, remove "
    "or explain anything. Write the Prophet as 'রাসূলুল্লাহ ﷺ'. Write (রাঃ) "
    "after the names of companions. Do not use dash symbols; use commas or "
    "full stops instead. Output ONLY the Bengali translation, with no notes "
    "or extra text."
)
SYS_VERIFY = (
    "You are a strict reviewer of Bengali translations of hadith. Compare the "
    "Bengali with the Arabic and English. Reply with exactly one line: 'OK' if "
    "the Bengali is faithful, complete, adds nothing, changes no meaning and "
    "reads naturally; otherwise 'BAD: <short reason in English>'."
)
SYS_HOOK = (
    "Write ONE short Bengali headline (maximum 9 words) for a social media "
    "card based on the given hadith. It must only reflect what the hadith "
    "actually says. Do not quote the Prophet, do not add any claim, no "
    "question marks, no emojis, no dash symbols. Output only the headline."
)


def clean(s):
    return " ".join(str(s).split())


def bn_digits(n):
    return str(n).translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯"))


def ask_ai(system, user):
    payload = {
        "model": "openai",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    headers = {
        "Authorization": "Bearer " + POLL_KEY,
        "User-Agent": "Mozilla/5.0",
    }
    for i in range(3):
        try:
            r = requests.post(CHAT_URL, json=payload, headers=headers, timeout=120)
            if r.ok:
                return r.json()["choices"][0]["message"]["content"].strip()
            print("AI error", r.status_code, r.text[:200])
        except Exception as e:
            print("AI exception", type(e).__name__)
        time.sleep(5)
    raise RuntimeError("AI request failed")


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_state(posted):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(posted, f, ensure_ascii=False, indent=1)


CACHE = {}


def load_book(key):
    if key in CACHE:
        return CACHE[key]
    try:
        r = requests.get(BASE + BOOKS[key]["path"], timeout=120)
        r.raise_for_status()
        items = r.json()["hadiths"]
    except Exception as e:
        print("Could not load book", key, type(e).__name__)
        items = []
    CACHE[key] = items
    return items


def pick_hadith(posted):
    keys = list(BOOKS.keys())
    weights = [BOOKS[k]["weight"] for k in keys]
    for _ in range(60):
        key = random.choices(keys, weights=weights)[0]
        items = load_book(key)
        if not items:
            continue
        h = random.choice(items)
        uid = key + ":" + str(h.get("idInBook"))
        if uid in posted:
            continue
        eng = clean(h.get("english", {}).get("text", ""))
        if not (40 <= len(eng) <= 1400) or not h.get("arabic"):
            continue
        return key, h, uid
    return None


def fetch_bg():
    scene = random.choice(SCENES)
    prompt = scene + ", cinematic, no text, no people"
    url = (
        "https://gen.pollinations.ai/image/"
        + urllib.parse.quote(prompt)
        + "?model=flux&width=1080&height=1080&nologo=true"
    )
    try:
        r = requests.get(
            url,
            headers={"Authorization": "Bearer " + POLL_KEY, "User-Agent": "Mozilla/5.0"},
            timeout=180,
        )
        if r.ok and r.headers.get("content-type", "").startswith("image"):
            return r.content
        print("Image error", r.status_code)
    except Exception as e:
        print("Image exception", type(e).__name__)
    return None


HTML = """
<html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@500;700&family=Amiri&family=Noto+Naskh+Arabic&display=swap" rel="stylesheet">
<style>
  body { margin: 0; }
  .card { width: 1080px; height: 1080px; position: relative; __BGCSS__ }
  .overlay { position: absolute; inset: 0; background: rgba(0, 10, 30, 0.62); }
  .content { position: absolute; inset: 0; display: flex; flex-direction: column;
             align-items: center; padding: 80px 90px; box-sizing: border-box;
             text-align: center;
             font-family: 'Hind Siliguri', 'Amiri', 'Noto Naskh Arabic', sans-serif; }
  .textbox { width: 100%; height: 740px; display: flex; align-items: center;
             justify-content: center; }
  .text { color: #ffffff; font-weight: 500; line-height: 1.6; }
  .nb { white-space: nowrap; }
  .line { width: 160px; height: 4px; background: #e8c872; margin: 36px 0 28px 0; }
  .ref { color: #e8c872; font-size: 34px; font-weight: 500; }
</style></head>
<body><div class="card"><div class="overlay"></div>
<div class="content">
  <div class="textbox"><div class="text" data-max="__MAX__">__TEXT__</div></div>
  <div class="line"></div>
  <div class="ref">__REF__</div>
</div></div></body></html>
"""

FIT_JS = """
() => {
  const box = document.querySelector('.textbox');
  const t = document.querySelector('.text');
  let s = parseInt(t.dataset.max);
  t.style.fontSize = s + 'px';
  while (t.offsetHeight > box.clientHeight && s > 26) {
    s -= 2;
    t.style.fontSize = s + 'px';
  }
  return s;
}
"""


def render_card(bg, main_text, ref, max_font, path="card.png"):
    if bg:
        b64 = base64.b64encode(bg).decode("ascii")
        bgcss = (
            "background-image: url(data:image/jpeg;base64," + b64 + ");"
            "background-size: cover; background-position: center;"
        )
    else:
        bgcss = "background: linear-gradient(160deg, #0b1d3a, #1c4a5e);"
    safe = htmllib.escape(main_text)
    safe = re.sub(r"(\S+-\S+)", r'<span class="nb">\1</span>', safe)
    page_html = (
        HTML.replace("__BGCSS__", bgcss)
        .replace("__TEXT__", safe)
        .replace("__REF__", htmllib.escape(ref))
        .replace("__MAX__", str(max_font))
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1080})
        page.set_content(page_html, wait_until="networkidle")
        page.evaluate("document.fonts.ready.then(() => true)")
        size = page.evaluate(FIT_JS)
        print("Final font size:", size)
        page.screenshot(path=path)
        browser.close()


def tg(method, data, files=None):
    r = requests.post(
        "https://api.telegram.org/bot" + TG_TOKEN + "/" + method,
        data=data,
        files=files,
        timeout=120,
    )
    if not r.ok:
        raise RuntimeError("Telegram error: " + r.text[:300])


def tg_text(text):
    tg("sendMessage", {"chat_id": TG_CHAT, "text": text[:4096]})


def tg_photo(path, caption):
    with open(path, "rb") as f:
        tg(
            "sendPhoto",
            {"chat_id": TG_CHAT, "caption": caption[:1024]},
            files={"photo": f},
        )


def main():
    posted = load_state()
    for attempt in range(1, 9):
        print("Attempt", attempt)
        picked = pick_hadith(posted)
        if not picked:
            print("No hadith available")
            break
        key, h, uid = picked
        arabic = clean(h["arabic"])
        if arabic.endswith(" ."):
            arabic = arabic[:-2] + "."
        narrator = clean(h["english"].get("narrator", ""))
        english = clean(h["english"]["text"])
        try:
            user_text = (
                "Arabic:\n" + arabic + "\n\nEnglish narrator: " + narrator
                + "\nEnglish text:\n" + english
            )
            bengali = ask_ai(SYS_TRANSLATE, user_text)
            bengali = clean(bengali.replace("—", ", ").replace("–", ", "))
            verdict = ask_ai(
                SYS_VERIFY,
                "Arabic:\n" + arabic + "\n\nEnglish:\n" + english
                + "\n\nBengali:\n" + bengali,
            ).strip()
        except Exception as e:
            print("Skipping, AI failed:", type(e).__name__)
            continue
        print("Verdict:", verdict)
        if not verdict.startswith("OK"):
            continue

        ref = BOOKS[key]["name"] + ", হাদিস " + bn_digits(h["idInBook"])
        bg = fetch_bg()
        short = len(bengali) <= CARD_MAX_CHARS
        hook = ""
        if short:
            render_card(bg, bengali, ref, 64)
            full_caption = bengali + "\n\n📚 " + ref
            if len(full_caption) <= 1024:
                tg_photo("card.png", full_caption)
            else:
                tg_photo("card.png", "📚 " + ref)
                tg_text(full_caption)
        else:
            hook = clean(ask_ai(SYS_HOOK, "Bengali hadith:\n" + bengali))
            hook = hook.replace("—", ",").strip("\"“”")
            render_card(bg, hook, ref, 88)
            tg_photo("card.png", hook + "\n\n📚 " + ref)
            tg_text(bengali + "\n\n📚 " + ref)

        if REVIEW_MODE:
            tg_text(
                "🔎 যাচাই (শুধু রিভিউয়ের জন্য)\n"
                "AI check: " + verdict + "\n"
                "Link: https://sunnah.com/" + key + ":" + str(h["idInBook"]) + "\n\n"
                "Arabic:\n" + arabic + "\n\nEnglish:\n" + english
            )

        posted.append(uid)
        save_state(posted)
        print("Posted", uid)
        return
    print("Nothing posted this run")
    sys.exit(1)


main()

