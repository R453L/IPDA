import hashlib
import json
import os
import random
import re
import sys
import time

import requests

import cards

sys.stdout.reconfigure(line_buffering=True)


def keys_from(*names):
    out = []
    for n in names:
        for k in re.split(r"[,\s]+", os.environ.get(n, "")):
            if k.strip():
                out.append(k.strip())
    return list(dict.fromkeys(out))


OR_KEYS = keys_from("OPENROUTER_API_KEYS", "OPENROUTER_API_KEY")
DS_KEYS = keys_from("DEEPSEEK_API_KEYS", "DEEPSEEK_API_KEY")
POLL_KEY = os.environ.get("POLLINATIONS_API_KEY", "").strip()
TG_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TG_CHAT = os.environ["TELEGRAM_CHAT_ID"]
REVIEW_MODE = os.environ.get("REVIEW_MODE", "1") == "1"
COUNT = int(os.environ.get("COUNT", "1") or "1")
OR_MODELS_ENV = [m.strip() for m in os.environ.get("OPENROUTER_MODELS", "").split(",") if m.strip()]

BASE = "https://raw.githubusercontent.com/AhmedBaset/hadith-json/v1.2.0/db/by_book/"
BOOKS = {
    "nawawi40": {"path": "forties/nawawi40.json", "name": "আন-নববীর ৪০ হাদিস", "weight": 2},
    "bukhari": {"path": "the_9_books/bukhari.json", "name": "সহীহ বুখারী", "weight": 3},
    "muslim": {"path": "the_9_books/muslim.json", "name": "সহীহ মুসলিম", "weight": 3},
}
STATE_FILE = "posted.json"
CARD_MAX_CHARS = 260
MAX_ATTEMPTS = 12
SLEEP_SECS = 24 * 3600
NEUTRAL_LABELS = ["আজকের হাদিস", "হাদিসের বাণী"]
PROPHET_WORDS = ["Prophet", "Messenger", "Apostle", "\ufdfa", "peace be upon him", "peace and blessings"]

PROVIDERS = {
    "or": "https://openrouter.ai/api/v1/chat/completions",
    "ds": "https://api.deepseek.com/chat/completions",
    "pl": "https://gen.pollinations.ai/v1/chat/completions",
}
TRIES = {"or": 8, "ds": 4, "pl": 1}

SYS_ANALYZE = (
    "You help prepare Bengali social media cards from hadith. You receive a mode, "
    "the narrator, the text to translate, and sometimes the Arabic. Mode 'quote' "
    "means the text is the quoted words only. Mode 'narration' means the text is "
    "the whole narration. Reply with ONE JSON object and nothing else, with "
    "exactly these keys:\n"
    '"speaker_is_prophet": true only if, in mode quote, the quoted words were '
    "spoken by Prophet Muhammad (peace be upon him) himself, including him "
    "reporting the words of Allah. false if they belong to a Companion, a "
    "follower or anyone else, and always false in mode narration.\n"
    '"bengali": a faithful, natural, simple Bengali translation of exactly the '
    "text to translate. Never add, remove, summarise or explain anything, and "
    "keep every statement, command and prayer in its original form (a prayer "
    "stays a prayer, a command stays a command). Do not include the narrator's "
    "name or the chain of narrators, and do not start with 'রাসূলুল্লাহ ﷺ "
    "বলেছেন' unless the text itself says so. Write the Prophet as "
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
    "Bengali with the English text and, when the Arabic is provided, also with "
    "the Arabic. If the Arabic is not provided, judge against the English only "
    "and do NOT fail the translation for that reason. Also check that the Bengali "
    "narrator refers to the same person as the English narrator (different "
    "spellings or a shorter form of the name are fine). Reply with exactly one "
    "line: 'OK' if the Bengali is faithful, complete, adds nothing, changes no "
    "meaning, turns no supplication into a narration and no command into a "
    "description, and the narrator is right; otherwise 'BAD: <short reason in "
    "English>'."
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

STATE = {"posted": [], "styles": [], "bases": [], "sleep": {}, "modelfail": {}}
COOL = {}
OR_MODELS = []
DS_MODEL = "deepseek-chat"


# ---------------------------------------------------------------- helpers
def clean(s):
    return " ".join(str(s).split())


def bn_digits(n):
    return str(n).translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯"))


def strip_marks(s):
    return re.sub("[\u200e\u200f\u202a-\u202e\u2066-\u2069]", "", s)


def has_bengali(s):
    letters = [ch for ch in s if ch.isalpha()]
    if len(letters) < 6:
        return False
    bn = [ch for ch in letters if "\u0980" <= ch <= "\u09ff"]
    return len(bn) / len(letters) >= 0.5


def parse_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def truthy(v):
    return v is True or (isinstance(v, str) and v.strip().lower() in ("true", "yes"))


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


def balanced(s):
    return (s.count("\u201c") == s.count("\u201d")
            and s.count("\u00ab") == s.count("\u00bb")
            and s.count('"') % 2 == 0)


# ------------------------------------------------------- key / model sleep
def kid(provider, key):
    return provider + ":" + hashlib.sha256(key.encode()).hexdigest()[:8]


def asleep(ident):
    return STATE["sleep"].get(ident, 0) > time.time()


def put_to_sleep(ident, why):
    STATE["sleep"][ident] = time.time() + SLEEP_SECS
    print("  sleeping 24h:", ident, "|", why)


def cooling(ident):
    return COOL.get(ident, 0) > time.time()


def bump_fail(mident):
    n = STATE["modelfail"].get(mident, 0) + 1
    if n >= 3:
        STATE["modelfail"][mident] = 0
        put_to_sleep(mident, "3 bad answers in a row")
    else:
        STATE["modelfail"][mident] = n


def good_answer(mident):
    STATE["modelfail"][mident] = 0


def classify(status, body):
    b = body.lower()
    if status in (401, 403, 402):
        return "key_dead"
    if status == 429:
        if any(w in b for w in ("per-day", "per day", "daily", "free-models-per-day")):
            return "key_dead"
        return "cool"
    if status in (400, 404):
        if any(w in b for w in ("model", "no endpoints", "not found", "does not exist")):
            return "model_dead"
        return "cool"
    if status == 422:
        return "skip"
    return "cool"


def call_once(provider, key, model, system, user):
    headers = {
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if provider in ("or", "ds"):
        payload["temperature"] = 0.2
        payload["max_tokens"] = 1800
        headers["X-Title"] = "hadith-bot"
    r = requests.post(PROVIDERS[provider], json=payload, headers=headers, timeout=100)
    body = r.text[:400]
    if r.ok:
        try:
            data = r.json()
        except Exception:
            return "cool", "bad json body"
        if isinstance(data, dict) and data.get("choices"):
            content = (data["choices"][0].get("message") or {}).get("content")
            if content and str(content).strip():
                return "ok", str(content).strip()
            return "cool", "empty answer"
        err = data.get("error") if isinstance(data, dict) else None
        if isinstance(err, dict):
            code = err.get("code")
            code = code if isinstance(code, int) else 500
            return classify(code, json.dumps(err)), "error in body: " + str(err)[:150]
        return "cool", "no choices"
    return classify(r.status_code, body), "%d %s" % (r.status_code, body[:120])


def or_endpoints(avoid):
    for m in OR_MODELS:
        if m == avoid:
            continue
        keys = list(OR_KEYS)
        if keys:
            i = random.randrange(len(keys))
            keys = keys[i:] + keys[:i]
        for k in keys:
            yield "or", k, m


def ds_endpoints(avoid):
    if DS_MODEL == avoid:
        return
    keys = list(DS_KEYS)
    if keys:
        i = random.randrange(len(keys))
        keys = keys[i:] + keys[:i]
    for k in keys:
        yield "ds", k, DS_MODEL


def pl_endpoints(avoid):
    if POLL_KEY and avoid != "openai":
        yield "pl", POLL_KEY, "openai"


def endpoints(role, avoid):
    if role == "translate":
        order = (or_endpoints, ds_endpoints, pl_endpoints)
    else:
        order = (ds_endpoints, or_endpoints, pl_endpoints)
    for gen in order:
        for ep in gen(avoid):
            yield ep


def chat(role, system, user, validator=None, avoid=None):
    """Try providers in order. Returns (text, label, model)."""
    used = {"or": 0, "ds": 0, "pl": 0}
    for provider, key, model in endpoints(role, avoid):
        if used[provider] >= TRIES[provider]:
            continue
        kident = kid(provider, key)
        mident = "model:" + provider + "/" + model
        if asleep(kident) or asleep(mident) or cooling(kident + "|" + model):
            continue
        used[provider] += 1
        try:
            status, text = call_once(provider, key, model, system, user)
        except Exception as e:
            status, text = "cool", type(e).__name__
        if status == "ok":
            if validator and not validator(text):
                print("  invalid answer from", provider + "/" + model)
                bump_fail(mident)
                continue
            good_answer(mident)
            return text, provider + ":" + model, model
        print("  %s/%s failed: %s" % (provider, model, text[:140]))
        if status == "key_dead":
            put_to_sleep(kident, text[:80])
        elif status == "model_dead":
            put_to_sleep(mident, text[:80])
        elif status == "cool":
            COOL[kident + "|" + model] = time.time() + 120
        # "skip" only skips this endpoint for this request
    raise RuntimeError("all AI providers failed")


# ----------------------------------------------------------- model lists
BAD_NAME = ("coder", "code", "vision", "-vl", "vl-", "embed", "guard", "safety", "moderation",
            "tts", "image", "audio", "music", "lyria", "whisper", "ocr", "reward", "rerank",
            "math", "roleplay", "uncensored")
GOOD_FAMILY = ("llama-3.3", "llama-4", "qwen3", "qwen-2.5", "gpt-oss", "deepseek", "gemma-3",
               "gemma-4", "mistral", "glm", "kimi", "nemotron", "minimax", "phi-4", "command")


def rank_free(items):
    scored = []
    for m in items:
        mid = str(m.get("id", ""))
        pr = m.get("pricing") or {}
        try:
            free = float(pr.get("prompt", 1)) == 0 and float(pr.get("completion", 1)) == 0
        except Exception:
            free = False
        if not (free or mid.endswith(":free")):
            continue
        out = (m.get("architecture") or {}).get("output_modalities") or []
        if out and "text" not in out:
            continue
        low = mid.lower()
        if any(b in low for b in BAD_NAME):
            continue
        ctx = m.get("context_length") or 0
        if ctx < 16000:
            continue
        sizes = re.findall(r"(\d+(?:\.\d+)?)b", low)
        size = max(float(x) for x in sizes) if sizes else 0
        score = min(size, 400) + (60 if any(g in low for g in GOOD_FAMILY) else 0) + min(ctx / 4000, 40)
        scored.append((score, mid))
    scored.sort(reverse=True)
    return [mid for _, mid in scored[:8]]


def init_models():
    global DS_MODEL
    models = list(OR_MODELS_ENV)
    if OR_KEYS:
        try:
            r = requests.get("https://openrouter.ai/api/v1/models",
                             headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            for m in rank_free(r.json().get("data", [])):
                if m not in models:
                    models.append(m)
        except Exception as e:
            print("OpenRouter model list failed:", type(e).__name__)
    OR_MODELS[:] = models
    if DS_KEYS:
        try:
            r = requests.get("https://api.deepseek.com/models",
                             headers={"Authorization": "Bearer " + DS_KEYS[0]}, timeout=20)
            ids = [m["id"] for m in r.json()["data"]]
            pick = [i for i in ids if "reason" not in i.lower()] or ids
            if pick:
                DS_MODEL = pick[0]
        except Exception as e:
            print("DeepSeek model list failed:", type(e).__name__)
    awake_or = len([k for k in OR_KEYS if not asleep(kid("or", k))])
    awake_ds = len([k for k in DS_KEYS if not asleep(kid("ds", k))])
    print("OpenRouter models:", OR_MODELS)
    print("DeepSeek model:", DS_MODEL)
    print("Keys awake: openrouter %d/%d, deepseek %d/%d, pollinations %s"
          % (awake_or, len(OR_KEYS), awake_ds, len(DS_KEYS), "yes" if POLL_KEY else "no"))


# ------------------------------------------------------------- state / data
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            STATE["posted"] = data
        elif isinstance(data, dict):
            STATE.update(data)
    for k, v in (("posted", []), ("styles", []), ("bases", []), ("sleep", {}), ("modelfail", {})):
        STATE.setdefault(k, v)


def save_state():
    now = time.time()
    STATE["sleep"] = {k: v for k, v in STATE["sleep"].items() if v > now}
    STATE["styles"] = STATE["styles"][-8:]
    STATE["bases"] = STATE["bases"][-20:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(STATE, f, ensure_ascii=False, indent=1)


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
    """Usable hadith data, or None when the source text is broken or incomplete."""
    english = clean(h.get("english", {}).get("text", ""))
    arabic_full = clean(strip_marks(h.get("arabic", "")))
    if not english or not arabic_full:
        return None
    if not (30 <= len(english) <= 1500) or not balanced(english):
        return None
    if english[-1] not in ".!?\"'\u201d\u2019)]":
        return None
    narrator = clean(h.get("english", {}).get("narrator", ""))
    en_q = quotes(english)
    if len(en_q) == 1 and 25 <= len(en_q[0]) <= 900:
        mode = "quote"
        unit = en_q[0]
        ar_q = quotes(arabic_full)
        arabic_quote = ar_q[0] if len(ar_q) == 1 and len(ar_q[0]) <= 150 else ""
        if arabic_quote and not (0.45 <= len(arabic_quote) / len(unit) <= 1.6):
            arabic_quote = ""
        idx = english.find(unit)
        before = english[max(0, idx - 200):idx] if idx >= 0 else ""
        prophet_hint = any(w in before for w in PROPHET_WORDS)
    else:
        mode, unit, arabic_quote, prophet_hint = "narration", english, "", False
    return {
        "mode": mode, "unit": unit, "english": english, "arabic_full": arabic_full,
        "arabic_quote": arabic_quote, "narrator": narrator, "prophet_hint": prophet_hint,
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
        uid = key + ":" + str(h.get("idInBook"))
        if uid in posted:
            continue
        c = candidate(h)
        if c:
            return key, h, uid, c
    return None


# ------------------------------------------------------------------ AI tasks
def analyze(c):
    user = (
        "Mode: " + c["mode"] + "\n"
        "Narrator: " + c["narrator"] + "\n\n"
        "Text to translate:\n" + c["unit"] + "\n\n"
        "Arabic of the quoted words:\n" + (c["arabic_quote"] or "not available") + "\n\n"
        "Full English hadith (context only):\n" + c["english"][:1500]
    )

    def valid(t):
        d = parse_json(t)
        return isinstance(d, dict) and has_bengali(str(d.get("bengali", "")))

    text, label, model = chat("translate", SYS_ANALYZE, user, validator=valid)
    data = parse_json(text)
    bengali = clean(str(data.get("bengali", "")))
    bengali = clean(bengali.replace("\u2014", ", ").replace("\u2013", ", ").replace(" - ", ", "))
    highlights = [clean(x) for x in (data.get("highlights") or []) if isinstance(x, str)]
    highlights = [x for x in highlights if x and x in bengali][:3]
    hook = clean(str(data.get("hook", "")))
    if hook and (hook not in bengali or len(hook.split()) > 14):
        hook = ""
    return {
        "prophet": truthy(data.get("speaker_is_prophet")),
        "bengali": bengali,
        "narrator_bn": clean(str(data.get("narrator_bn", "")))[:40],
        "highlights": highlights,
        "hook": hook,
        "translator": label,
        "model": model,
    }


def verify(c, a):
    user = (
        "Narrator (English): " + c["narrator"] + "\n"
        "Narrator (Bengali): " + a["narrator_bn"] + "\n\n"
        "Arabic:\n" + (c["arabic_quote"] or "not available") + "\n\n"
        "English:\n" + c["unit"] + "\n\n"
        "Bengali:\n" + a["bengali"]
    )

    def v_ok(t):
        return clean(t).upper().startswith(("OK", "BAD"))

    avoid = a["model"]
    weak = ""
    try:
        text, vlabel, _ = chat("verify", SYS_VERIFY, user, validator=v_ok, avoid=avoid)
    except RuntimeError:
        # no independent model left: last resort, same model checks its own work
        avoid = None
        weak = " (same model, weaker check)"
        text, vlabel, _ = chat("verify", SYS_VERIFY, user, validator=v_ok)
    vlabel += weak
    verdict = clean(text)
    if not verdict.upper().startswith("OK"):
        return verdict, vlabel
    back, _, _ = chat("verify", SYS_BACK, a["bengali"],
                      validator=lambda t: len(clean(t)) > 5, avoid=avoid)
    back = clean(back)
    print("  back-translation:", back[:160])

    def c_ok(t):
        return clean(t).upper().startswith(("SAME", "DIFFERENT"))

    same, _, _ = chat("verify", SYS_COMPARE,
                      "Text A (original):\n" + c["unit"] + "\n\nText B (back-translation):\n" + back,
                      validator=c_ok, avoid=avoid)
    if not clean(same).upper().startswith("SAME"):
        return "BAD: back-translation differs: " + clean(same)[:200], vlabel
    return "OK", vlabel


def fallback_hook(bengali):
    first = re.split(r"(?<=[।?!])\s+", bengali)[0]
    words = first.split()
    if len(words) <= 18:
        return first
    return " ".join(words[:14]) + "…"


# ------------------------------------------------------------------ telegram
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


def choose_look():
    styles = [s for s in cards.STYLES if s not in STATE["styles"]] or list(cards.STYLES)
    files = cards.list_bases()
    recent = set(STATE["bases"])
    fresh = [f for f in files if os.path.basename(f) not in recent] or files
    return random.choice(styles), (random.choice(fresh) if fresh else None)


def make_one(renderer):
    posted = STATE["posted"]
    ai_down = 0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        print("Attempt", attempt)
        picked = pick_hadith(posted)
        if not picked:
            print("No usable hadith found")
            return False
        key, h, uid, c = picked
        try:
            a = analyze(c)
            verdict, vlabel = verify(c, a)
        except Exception as e:
            print(uid, "| AI step failed:", type(e).__name__, str(e)[:120])
            ai_down += 1
            if ai_down >= 3:
                print("All AI providers are unavailable right now, stopping this run.")
                return "abort"
            continue
        print(uid, "| mode:", c["mode"], "| translator:", a["translator"],
              "| verifier:", vlabel, "| verdict:", verdict[:200])
        if not verdict.upper().startswith("OK"):
            continue

        ref = BOOKS[key]["name"] + ", হাদিস " + bn_digits(h["idInBook"])
        if a["narrator_bn"]:
            ref += " | " + a["narrator_bn"]
        short = len(a["bengali"]) <= CARD_MAX_CHARS
        prophet = c["mode"] == "quote" and a["prophet"] and c["prophet_hint"]
        label = random.choice(cards.LABELS if prophet else NEUTRAL_LABELS)
        if short:
            spec = {"text": a["bengali"], "arabic": c["arabic_quote"], "ref": ref,
                    "highlights": a["highlights"], "label": label}
        else:
            hook = a["hook"] or fallback_hook(a["bengali"])
            spec = {"text": hook, "arabic": "", "ref": ref, "highlights": [], "label": label}

        style, base = choose_look()
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
                tg_photo("card.png", spec["text"] + "\n\n📚 " + ref)
                body = a["bengali"] + "\n\n📚 " + ref
                if c["arabic_quote"]:
                    body = c["arabic_quote"] + "\n\n" + body
                tg_text(body)
            if REVIEW_MODE:
                tg_text(
                    "🔎 যাচাই (শুধু রিভিউয়ের জন্য)\n"
                    "AI check: " + verdict + "\n"
                    "Translator: " + a["translator"] + " | Verifier: " + vlabel + "\n"
                    "Mode: " + c["mode"] + " | Style: " + info["style"] + " | Base: " + info["base"] + "\n"
                    "Link: https://sunnah.com/" + key + ":" + str(h["idInBook"]) + "\n\n"
                    "English (used):\n" + c["unit"] + "\n\n"
                    "Arabic (full):\n" + c["arabic_full"][:1500]
                )
        except Exception as e:
            print("Post failed:", type(e).__name__, str(e)[:200])
            continue

        posted.append(uid)
        STATE["styles"].append(info["style"])
        STATE["bases"].append(info["base"])
        save_state()
        print("Posted", uid)
        return True
    return False


def main():
    if not (OR_KEYS or DS_KEYS or POLL_KEY):
        print("No AI keys configured")
        sys.exit(1)
    load_state()
    init_models()
    done = 0
    try:
        with cards.CardRenderer() as renderer:
            for i in range(COUNT):
                print("=== Post", i + 1, "of", COUNT, "===")
                result = make_one(renderer)
                if result == "abort":
                    break
                if result:
                    done += 1
                time.sleep(2)
    finally:
        save_state()
    print("Posted this run:", done)
    if done == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
