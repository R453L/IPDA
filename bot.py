import json
import os
import random
import re
import sys
import time

import requests

import cards

sys.stdout.reconfigure(line_buffering=True)

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
# Only books/chapters about character, faith, remembrance and the heart.
# None means every hadith of that book is allowed.
ALLOWED_CHAPTERS = {
    "nawawi40": None,
    "bukhari": {2, 3, 53, 66, 69, 75, 78, 79, 80, 81},
    "muslim": {1, 38, 39, 45, 47, 48, 49, 50, 55},
}
CHAT_URL = "https://gen.pollinations.ai/v1/chat/completions"
STATE_FILE = "posted.json"
CARD_MAX_CHARS = 260
MAX_ATTEMPTS = 14


SYS_ANALYZE = (
    "You help prepare Bengali social media cards from hadith. You receive the "
    "full English text of a hadith, the quoted words (English, and Arabic when "
    "available) and the narrator. Reply with ONE JSON object and nothing else, "
    "with exactly these keys:\n"
    '"speaker_is_prophet": true only if the quoted words were spoken by Prophet '
    "Muhammad (peace be upon him) himself, including him reporting the words of "
    "Allah. false if the words belong to a Companion, a follower or anyone else.\n"
    '"suitable": true if the quoted words form a complete thought that a general '
    "Muslim reader can understand and benefit from on their own. false only if "
    "the words are incomplete or meaningless without the rest of the hadith, are "
    "a purely technical procedure (exact steps of prayer or purification, "
    "zakat calculations, inheritance shares, contract details), or depend on a "
    "specific named event or dispute. Also false if the Arabic and English "
    "quoted words are clearly not the same statement. When unsure, true.\n"
    '"reason": a short English reason.\n'
    '"bengali": a faithful, natural, simple Bengali translation of ONLY the quoted '
    "words. Never add, remove or explain anything. Do not include the narrator "
    "chain and do not start with 'রাসূলুল্লাহ ﷺ বলেছেন'. Write the Prophet as "
    "'রাসূলুল্লাহ ﷺ', Allah as 'আল্লাহ', and put (রাঃ) after companions' names. "
    "Do not use dash symbols; use commas or full stops instead.\n"
    '"narrator_bn": the Bengali name of the Companion narrator with (রাঃ), for '
    "example 'আবূ হুরাইরাহ (রাঃ)', or an empty string if unclear.\n"
    '"highlights": a list of 1 to 3 key words or short phrases (at most 3 words '
    "each) copied EXACTLY as they appear inside your Bengali translation.\n"
    '"hook": one complete sentence copied EXACTLY from your Bengali translation, '
    "at most 14 words, that works as a headline, or an empty string if there is "
    "no such sentence."
)
SYS_VERIFY = (
    "You are a strict reviewer of Bengali translations of hadith. Compare the "
    "Bengali with the English quoted words and, when the Arabic quoted words are "
    "provided, also with the Arabic. If the Arabic is not provided, judge against "
    "the English only and do NOT fail the translation for that reason. Also check "
    "that the Bengali narrator refers to the same person as the English narrator "
    "(different spellings or a shorter form of the name are fine). Reply with "
    "exactly one line: 'OK' if the Bengali is faithful, complete, adds nothing, "
    "changes no meaning, turns no supplication into a narration and no command "
    "into a description, and the narrator is right; otherwise "
    "'BAD: <short reason in English>'."
)
SYS_BACK = (
    "Translate the given Bengali text into plain, literal English. Output only "
    "the English translation, with no notes."
)
SYS_COMPARE = (
    "You compare two English texts. Text A is the original and text B is a "
    "back-translation. Reply with exactly one line: 'SAME' if both convey the "
    "same meaning (ignore wording and small style differences), or "
    "'DIFFERENT: <short reason>' if B adds, drops or changes any meaning, "
    "changes who does or says what, or turns a request or prayer into a "
    "statement or the reverse."
)


def clean(s):
    return " ".join(str(s).split())


def bn_digits(n):
    return str(n).translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯"))


def strip_marks(s):
    return re.sub("[\u200e\u200f\u202a-\u202e\u2066-\u2069]", "", s)


def _nested(s, op, cl):
    out, depth, start = [], 0, None
    for i, ch in enumerate(s):
        if ch == op:
            if depth == 0:
                start = i + 1
            depth += 1
        elif ch == cl and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                out.append(s[start:i])
                start = None
    return out


def quotes(s):
    s = strip_marks(s)
    found = _nested(s, "\u201c", "\u201d") + _nested(s, "\u00ab", "\u00bb")
    if s.count('"') >= 2 and s.count('"') % 2 == 0:
        parts = s.split('"')
        found += [p for k, p in enumerate(parts) if k % 2 == 1]
    return [clean(q) for q in found if clean(q)]


MODELS = ["openai"]


def init_models():
    """Add a few more chat models as fallbacks for requests the first one refuses."""
    try:
        r = requests.get("https://gen.pollinations.ai/text/models",
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        names = []
        for m in r.json():
            n = m.get("name") if isinstance(m, dict) else m
            if isinstance(n, str):
                names.append(n)
        bad = ("image", "audio", "video", "tts", "whisper", "vision", "search", "openai")
        extra = [n for n in names if not any(b in n.lower() for b in bad)][:3]
        MODELS[:] = ["openai"] + extra
    except Exception as e:
        print("Model list not available:", type(e).__name__)
    print("Models:", MODELS)


def ask_ai(system, user):
    headers = {
        "Authorization": "Bearer " + POLL_KEY,
        "User-Agent": "Mozilla/5.0",
    }
    rejected = 0
    for model in MODELS:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        for _ in range(3):
            try:
                r = requests.post(CHAT_URL, json=payload, headers=headers, timeout=120)
                if r.ok:
                    return r.json()["choices"][0]["message"]["content"].strip()
                print("AI error", model, r.status_code, r.text[:120])
                if r.status_code in (400, 401, 402, 403, 404, 422):
                    rejected += 1
                    break
            except Exception as e:
                print("AI exception", type(e).__name__)
            time.sleep(5)
    raise RuntimeError("AI request failed (rejected by %d models)" % rejected)


def parse_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def load_state():
    state = {"posted": [], "styles": [], "bases": []}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            state["posted"] = data
        elif isinstance(data, dict):
            state.update(data)
    return state


def save_state(state):
    state["styles"] = state["styles"][-8:]
    state["bases"] = state["bases"][-20:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


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


def candidate(h):
    """Return a dict with the quoted words, or None if the hadith is not usable."""
    english = clean(h.get("english", {}).get("text", ""))
    arabic_full = clean(strip_marks(h.get("arabic", "")))
    if not english or not arabic_full:
        return None
    en_q = quotes(english)
    if len(en_q) != 1 or not (25 <= len(en_q[0]) <= 900):
        return None
    ar_q = quotes(arabic_full)
    arabic_quote = ar_q[0] if len(ar_q) == 1 and len(ar_q[0]) <= 150 else ""
    if arabic_quote and not (0.45 <= len(arabic_quote) / len(en_q[0]) <= 1.6):
        arabic_quote = ""
    return {
        "english": english,
        "english_quote": en_q[0],
        "arabic_full": arabic_full,
        "arabic_quote": arabic_quote,
        "narrator": clean(h.get("english", {}).get("narrator", "")),
    }


def pick_hadith(posted):
    keys = list(BOOKS.keys())
    weights = [BOOKS[k]["weight"] for k in keys]
    for _ in range(400):
        key = random.choices(keys, weights=weights)[0]
        items = load_book(key)
        if not items:
            continue
        h = random.choice(items)
        allowed = ALLOWED_CHAPTERS.get(key)
        if allowed is not None and h.get("chapterId") not in allowed:
            continue
        uid = key + ":" + str(h.get("idInBook"))
        if uid in posted:
            continue
        c = candidate(h)
        if c:
            return key, h, uid, c
    return None


def truthy(v):
    return v is True or (isinstance(v, str) and v.strip().lower() in ("true", "yes"))


def analyze(c):
    user = (
        "Narrator: " + c["narrator"] + "\n\n"
        "Full English hadith:\n" + c["english"][:1500] + "\n\n"
        "Quoted words (English):\n" + c["english_quote"] + "\n\n"
        "Quoted words (Arabic):\n" + (c["arabic_quote"] or "not available")
    )
    data = parse_json(ask_ai(SYS_ANALYZE, user))
    if not isinstance(data, dict):
        return None
    bengali = clean(str(data.get("bengali", "")))
    bengali = clean(bengali.replace("\u2014", ", ").replace("\u2013", ", ").replace(" - ", ", "))
    highlights = [clean(str(x)) for x in (data.get("highlights") or []) if isinstance(x, (str,))]
    highlights = [x for x in highlights if x and x in bengali][:3]
    hook = clean(str(data.get("hook", "")))
    if hook and (hook not in bengali or len(hook.split()) > 14):
        hook = ""
    return {
        "prophet": truthy(data.get("speaker_is_prophet")),
        "suitable": truthy(data.get("suitable")),
        "reason": clean(str(data.get("reason", ""))),
        "bengali": bengali,
        "narrator_bn": clean(str(data.get("narrator_bn", "")))[:40],
        "highlights": highlights,
        "hook": hook,
    }


def verify(c, a):
    user = (
        "Narrator (English): " + c["narrator"] + "\n"
        "Narrator (Bengali): " + a["narrator_bn"] + "\n\n"
        "Arabic quoted words:\n" + (c["arabic_quote"] or "not available") + "\n\n"
        "English quoted words:\n" + c["english_quote"] + "\n\n"
        "Bengali:\n" + a["bengali"]
    )
    verdict = clean(ask_ai(SYS_VERIFY, user))
    if not verdict.startswith("OK"):
        return verdict
    back = clean(ask_ai(SYS_BACK, a["bengali"]))
    same = clean(ask_ai(SYS_COMPARE, "Text A (original):\n" + c["english_quote"]
                        + "\n\nText B (back-translation):\n" + back))
    print("  back-translation:", back[:160])
    if not same.startswith("SAME"):
        return "BAD: back-translation differs: " + same[:200]
    return "OK"


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


def choose_look(state):
    styles = [s for s in cards.STYLES if s not in state["styles"]] or list(cards.STYLES)
    files = cards.list_bases()
    recent = set(state["bases"])
    fresh = [f for f in files if os.path.basename(f) not in recent] or files
    return random.choice(styles), (random.choice(fresh) if fresh else None)


def make_one(state, renderer):
    posted = state["posted"]
    for attempt in range(1, MAX_ATTEMPTS + 1):
        print("Attempt", attempt)
        picked = pick_hadith(posted)
        if not picked:
            print("No usable hadith found")
            return False
        key, h, uid, c = picked
        try:
            a = analyze(c)
            if not a:
                print(uid, "| bad AI answer")
                continue
            if not a["prophet"] or not a["suitable"]:
                print(uid, "| skipped | prophet=%s suitable=%s | %s"
                      % (a["prophet"], a["suitable"], a["reason"][:120]))
                continue
            if len(a["bengali"]) < 10:
                continue
            verdict = verify(c, a)
        except Exception as e:
            print("Skipping, AI failed:", type(e).__name__)
            continue
        print(uid, "| verdict:", verdict)
        if not verdict.startswith("OK"):
            continue

        ref = BOOKS[key]["name"] + ", হাদিস " + bn_digits(h["idInBook"])
        if a["narrator_bn"]:
            ref += " | " + a["narrator_bn"]
        short = len(a["bengali"]) <= CARD_MAX_CHARS
        if short:
            spec = {"text": a["bengali"], "arabic": c["arabic_quote"],
                    "ref": ref, "highlights": a["highlights"]}
        elif a["hook"]:
            spec = {"text": a["hook"], "arabic": "", "ref": ref, "highlights": []}
        else:
            print(uid, "| long and no hook, skipped")
            continue

        style, base = choose_look(state)
        try:
            info = renderer.render(spec, "card.png", style=style, base_path=base)
            print("Card:", info)
            if short:
                caption = a["bengali"] + "\n\n📚 " + ref
                if len(caption) <= 1024:
                    tg_photo("card.png", caption)
                else:
                    tg_photo("card.png", "📚 " + ref)
                    tg_text(caption)
            else:
                tg_photo("card.png", a["hook"] + "\n\n📚 " + ref)
                body = a["bengali"] + "\n\n📚 " + ref
                if c["arabic_quote"]:
                    body = c["arabic_quote"] + "\n\n" + body
                tg_text(body)
            if REVIEW_MODE:
                tg_text(
                    "🔎 যাচাই (শুধু রিভিউয়ের জন্য)\n"
                    "AI check: " + verdict + "\n"
                    "Style: " + info["style"] + " | Base: " + info["base"] + "\n"
                    "Link: https://sunnah.com/" + key + ":" + str(h["idInBook"]) + "\n\n"
                    "English quote:\n" + c["english_quote"] + "\n\n"
                    "Arabic (full):\n" + c["arabic_full"][:1500] + "\n\n"
                    "English (full):\n" + c["english"][:1500]
                )
        except Exception as e:
            print("Post failed:", type(e).__name__, str(e)[:200])
            continue

        posted.append(uid)
        state["styles"].append(info["style"])
        state["bases"].append(info["base"])
        save_state(state)
        print("Posted", uid)
        return True
    return False


def main():
    init_models()
    state = load_state()
    done = 0
    with cards.CardRenderer() as renderer:
        for i in range(COUNT):
            print("=== Post", i + 1, "of", COUNT, "===")
            if make_one(state, renderer):
                done += 1
            time.sleep(3)
    print("Posted this run:", done)
    if done == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
