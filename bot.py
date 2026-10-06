import base64
import colorsys
import glob
import html as htmllib
import io
import json
import os
import random
import re
import sys
import time

import requests
from PIL import Image
from playwright.sync_api import sync_playwright

POLL_KEY = os.environ["POLLINATIONS_API_KEY"]
TG_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TG_CHAT = os.environ["TELEGRAM_CHAT_ID"]
REVIEW_MODE = os.environ.get("REVIEW_MODE", "1") == "1"
COUNT = int(os.environ.get("COUNT", "1") or "1")

BASE = "https://raw.githubusercontent.com/AhmedBaset/hadith-json/v1.2.0/db/by_book/"
BOOKS = {
    "nawawi40": {"path": "forties/nawawi40.json", "name": "আন-নববীর ৪০ হাদিস", "weight": 2},
    "bukhari": {"path": "the_9_books/bukhari.json", "name": "সহীহ বুখারী", "weight": 3},
    "muslim": {"path": "the_9_books/muslim.json", "name": "সহীহ মুসলিম", "weight": 3},
}
CHAT_URL = "https://gen.pollinations.ai/v1/chat/completions"
STATE_FILE = "posted.json"
CARD_MAX_CHARS = 380
LABELS = ["আজকের হাদিস", "রাসূলুল্লাহ ﷺ বলেছেন", "হাদিসের বাণী"]

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

CARD_HTML = """
<html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@500;700&family=Amiri&display=swap" rel="stylesheet">
<style>
body { margin: 0; }
.card { width: 1080px; height: 1080px; position: relative; overflow: hidden;
        display: flex; align-items: center; justify-content: center;
        font-family: 'Hind Siliguri', 'Amiri', sans-serif; }
.bg { position: absolute; inset: 0; background-size: cover; background-position: center;
      background-image: url(data:image/jpeg;base64,__B64__); transform: __TRANSFORM__; }
.panel { position: relative; isolation: isolate; width: __W__px; box-sizing: border-box;
         padding: __PT__px 56px 40px; display: flex; flex-direction: column;
         align-items: center; text-align: center; background: __PANELBG__;
         border: 2px solid __BORDER__; border-radius: 30px;
         backdrop-filter: blur(__BLUR__); box-shadow: 0 16px 50px rgba(0,0,0,0.16); }
.s-soft { background: transparent; border: none; box-shadow: none; backdrop-filter: none; }
.s-soft::before { content: ""; position: absolute; inset: -60px; z-index: -1;
                  border-radius: 140px; background: __SOFT__; filter: blur(30px); }
.s-frame { border-radius: 12px; border: 2px solid __ACCENT__; box-shadow: none; }
.s-frame::after { content: ""; position: absolute; inset: 10px; border-radius: 6px;
                  border: 1px solid __ACCENT__88; pointer-events: none; }
.s-arch { border-radius: 260px 260px 26px 26px; }
.s-glass { border-radius: 48px; }
.label { font-size: 40px; font-weight: 700; color: __ACCENT__; }
.orn { display: flex; align-items: center; gap: 14px; margin: 16px 0 24px; }
.orn i { display: block; width: 90px; height: 2px; background: __ACCENT__; }
.orn b { display: block; width: 12px; height: 12px; background: __ACCENT__; transform: rotate(45deg); }
.text { color: __TEXTCOL__; font-weight: 500; line-height: 1.6; width: 100%; }
.nb { white-space: nowrap; }
.sal { font-family: 'Amiri', 'Hind Siliguri', serif; font-size: 1.1em; }
.ref { font-size: 26px; font-weight: 500; color: __ACCENT__; margin-top: 22px; }
</style></head>
<body><div class="card"><div class="bg"></div>
<div class="panel s-__STYLE__">
<div class="label">__LABEL__</div>
<div class="orn"><i></i><b></b><i></i></div>
<div class="text">__TEXT__</div>
<div class="ref">__REF__</div>
</div></div></body></html>
"""

FIT_JS = """
(n) => {
  const t = document.querySelector('.text');
  const p = document.querySelector('.panel');
  let s = n < 80 ? 72 : (n < 160 ? 60 : (n < 260 ? 50 : 42));
  t.style.fontSize = s + 'px';
  while (p.offsetHeight > 900 && s > 28) {
    s -= 2;
    t.style.fontSize = s + 'px';
  }
  return [s, p.offsetHeight];
}
"""


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


def lum(p):
    r, g, b = [v / 255 for v in p]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def hx(r, g, b):
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


def list_bases():
    files = []
    if os.path.isdir("bases"):
        for ext in ("jpg", "jpeg", "png", "webp"):
            files += glob.glob("bases/*." + ext)
            files += glob.glob("bases/*." + ext.upper())
    return sorted(set(files))


def load_base(path):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    s = min(w, h)
    left, top = (w - s) // 2, (h - s) // 2
    return im.crop((left, top, left + s, top + s)).resize((1080, 1080), Image.LANCZOS)


def analyze(im):
    small = im.resize((60, 60))
    px = small.load()
    total, n = 0.0, 0
    edge = []
    for y in range(60):
        for x in range(60):
            p = px[x, y]
            total += lum(p)
            n += 1
            if x < 9 or x >= 51 or y < 9 or y >= 51:
                edge.append(p)
    avg_lum = total / n
    er = sum(p[0] for p in edge) / len(edge) / 255
    eg = sum(p[1] for p in edge) / len(edge) / 255
    eb = sum(p[2] for p in edge) / len(edge) / 255
    h, l, s = colorsys.rgb_to_hls(er, eg, eb)
    if s < 0.08:
        h = 0.11
    s = min(max(s, 0.35), 0.75)
    dark = avg_lum < 0.42
    accent = colorsys.hls_to_rgb(h, 0.78 if dark else 0.30, s)
    textcol = (1, 1, 1) if dark else colorsys.hls_to_rgb(h, 0.14, 0.35)
    return dark, hx(*accent), hx(*textcol)


def jpeg_b64(im):
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def prep(s):
    s = htmllib.escape(s)
    s = re.sub(r"(\S+-\S+)", r'<span class="nb">\1</span>', s)
    return s.replace("ﷺ", '<span class="sal">ﷺ</span>')


def render_card(text, ref, path="card.png"):
    files = list_bases()
    if files:
        chosen = random.choice(files)
        im = load_base(chosen)
        print("Base image:", os.path.basename(chosen))
    else:
        print("No base images found, using plain background")
        im = Image.new("RGB", (1080, 1080), (236, 226, 210))
    dark, accent, textcol = analyze(im)
    style = random.choice(["soft", "frame", "arch", "glass", "soft", "frame"])
    n = len(text)
    width = 900 if n > 260 else random.choice([740, 800])
    pt = 110 if style == "arch" else 52
    panelbg = "rgba(10,18,30,0.66)" if dark else "rgba(255,255,255,0.86)"
    soft = "rgba(10,18,30,0.74)" if dark else "rgba(255,255,255,0.88)"
    transform = "scaleX(%d) scale(%s)" % (random.choice([1, -1]), random.choice([1.0, 1.05, 1.1]))
    page_html = (
        CARD_HTML.replace("__B64__", jpeg_b64(im))
        .replace("__TRANSFORM__", transform)
        .replace("__W__", str(width))
        .replace("__PT__", str(pt))
        .replace("__PANELBG__", panelbg)
        .replace("__SOFT__", soft)
        .replace("__BORDER__", accent + "66")
        .replace("__BLUR__", "8px" if dark else "0px")
        .replace("__STYLE__", style)
        .replace("__ACCENT__", accent)
        .replace("__TEXTCOL__", textcol)
        .replace("__LABEL__", prep(random.choice(LABELS)))
        .replace("__TEXT__", prep(text))
        .replace("__REF__", htmllib.escape(ref))
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1080})
        page.set_content(page_html, wait_until="networkidle")
        page.evaluate("document.fonts.ready.then(() => true)")
        size, height = page.evaluate(FIT_JS, n)
        page.screenshot(path=path)
        browser.close()
    print("Card style:", style, "| chars:", n, "| font:", size, "| panel height:", height)


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


def make_one(posted):
    for attempt in range(1, 9):
        print("Attempt", attempt)
        picked = pick_hadith(posted)
        if not picked:
            print("No hadith available")
            return False
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
        print(uid, "| verdict:", verdict)
        if not verdict.startswith("OK"):
            continue

        ref = BOOKS[key]["name"] + ", হাদিস " + bn_digits(h["idInBook"])
        try:
            if len(bengali) <= CARD_MAX_CHARS:
                render_card(bengali, ref)
                full_caption = bengali + "\n\n📚 " + ref
                if len(full_caption) <= 1024:
                    tg_photo("card.png", full_caption)
                else:
                    tg_photo("card.png", "📚 " + ref)
                    tg_text(full_caption)
            else:
                hook = clean(ask_ai(SYS_HOOK, "Bengali hadith:\n" + bengali))
                hook = hook.replace("—", ",").strip("\"“”")
                render_card(hook, ref)
                tg_photo("card.png", hook + "\n\n📚 " + ref)
                tg_text(bengali + "\n\n📚 " + ref)

            if REVIEW_MODE:
                tg_text(
                    "🔎 যাচাই (শুধু রিভিউয়ের জন্য)\n"
                    "AI check: " + verdict + "\n"
                    "Link: https://sunnah.com/" + key + ":" + str(h["idInBook"]) + "\n\n"
                    "Arabic:\n" + arabic + "\n\nEnglish:\n" + english
                )
        except Exception as e:
            print("Post failed:", type(e).__name__, str(e)[:200])
            continue

        posted.append(uid)
        save_state(posted)
        print("Posted", uid)
        return True
    return False


def main():
    posted = load_state()
    done = 0
    for i in range(COUNT):
        print("=== Post", i + 1, "of", COUNT, "===")
        if make_one(posted):
            done += 1
        time.sleep(4)
    print("Posted this run:", done)
    if done == 0:
        sys.exit(1)


main()
