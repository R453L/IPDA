import base64
import os
import urllib.error
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright

KEY = os.environ["POLLINATIONS_API_KEY"]

BG_PROMPT = (
    "peaceful mosque silhouette at dawn, soft golden light, deep blue sky, "
    "calm and serene, cinematic, no text, no people"
)
HOOK = "ভালো কথাও একটি সদকা"
REF = "আন-নববীর ৪০ হাদিস, হাদিস ২৬"

url = (
    "https://gen.pollinations.ai/image/"
    + urllib.parse.quote(BG_PROMPT)
    + "?model=flux&width=1080&height=1080&nologo=true"
)
req = urllib.request.Request(
    url,
    headers={"User-Agent": "Mozilla/5.0", "Authorization": "Bearer " + KEY},
)

try:
    with urllib.request.urlopen(req, timeout=180) as r:
        img = r.read()
except urllib.error.HTTPError as e:
    print("IMAGE ERROR", e.code, e.read().decode("utf-8", "ignore"))
    raise SystemExit(1)

with open("bg.jpg", "wb") as f:
    f.write(img)
print("Background saved, bytes:", len(img))

bg64 = base64.b64encode(img).decode("ascii")

HTML = """
<html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@500;700&display=swap" rel="stylesheet">
<style>
  body { margin: 0; }
  .card { width: 1080px; height: 1080px; position: relative;
          background-image: url(data:image/jpeg;base64,__BG__);
          background-size: cover; background-position: center; }
  .overlay { position: absolute; inset: 0; background: rgba(0, 10, 30, 0.55); }
  .content { position: absolute; inset: 0; display: flex; flex-direction: column;
             align-items: center; justify-content: center; padding: 90px;
             text-align: center; font-family: 'Hind Siliguri', sans-serif; }
  .hook { color: #ffffff; font-size: 88px; font-weight: 700; line-height: 1.35; }
  .line { width: 160px; height: 4px; background: #e8c872; margin: 56px 0; }
  .ref { color: #e8c872; font-size: 36px; font-weight: 500; }
</style></head>
<body><div class="card"><div class="overlay"></div>
<div class="content">
  <div class="hook">__HOOK__</div>
  <div class="line"></div>
  <div class="ref">__REF__</div>
</div></div></body></html>
"""
html = HTML.replace("__BG__", bg64).replace("__HOOK__", HOOK).replace("__REF__", REF)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1080, "height": 1080})
    page.set_content(html, wait_until="networkidle")
    page.evaluate("document.fonts.ready.then(() => true)")
    page.screenshot(path="card.png")
    browser.close()

print("Card saved: card.png")

