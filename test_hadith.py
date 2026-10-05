import json
import random
import urllib.request
import urllib.error

DATA_URL = "https://raw.githubusercontent.com/AhmedBaset/hadith-json/v1.2.0/db/by_book/forties/nawawi40.json"
API_URL = "https://gen.pollinations.ai/v1/chat/completions"

SYSTEM = (
    "You are a careful Islamic translator. Translate the given hadith into "
    "natural, simple Bengali. Rules: translate faithfully, never add, remove "
    "or explain anything. Write the Prophet as 'রাসূলুল্লাহ ﷺ'. Write (রাঃ) "
    "after the names of companions. Output ONLY the Bengali translation, "
    "with no notes or extra text."
)

with urllib.request.urlopen(DATA_URL) as r:
    data = json.loads(r.read().decode("utf-8"))

h = random.choice(data["hadiths"])
arabic = h["arabic"].strip()
narrator = h["english"]["narrator"].strip()
english = h["english"]["text"].strip()

user_text = (
    "Arabic:\n" + arabic + "\n\n"
    "English narrator: " + narrator + "\n"
    "English text:\n" + english
)

payload = {
    "model": "openai",
    "messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_text},
    ],
}

req = urllib.request.Request(
    API_URL,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
)

print("Reference: Forty Hadith of Nawawi, Hadith", h["idInBook"])
print("English:", english)
print("-----")

try:
    with urllib.request.urlopen(req, timeout=90) as r:
        res = json.loads(r.read().decode("utf-8"))
    print("Bengali:", res["choices"][0]["message"]["content"].strip())
except urllib.error.HTTPError as e:
    print("ERROR", e.code, e.read().decode("utf-8", "ignore"))
