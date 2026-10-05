import base64
import html as htmllib
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

TEXT = (
    "আবূ হুরায়রাহ (রাঃ) থেকে বর্ণিত, তিনি বলেন: রাসূলুল্লাহ ﷺ বলেছেন, "
    "“মানুষের প্রতিটি জোড়ার পক্ষ থেকে প্রতিদিন দান-সদকা করা কর্তব্য। "
    "সূর্য উদিত হওয়ার দিন—দুইজনের মধ্যে ন্যায়ভাবে ফায়সালা করা দান-সদকা। "
    "কোনো লোককে তার বাহনে সাহায্য করা, তাকে ওই বাহনের উপর উঠিয়ে দেওয়া "
    "অথবা তার প্রয়োজনীয় জিনিস ওই বাহনের উপর তুলে দেওয়া দান-সদকা। "
    "ভালো কথা দান-সদকা। নামাযের দিকে যে প্রতিটি পদক্ষেপ তুমি নাও, "
    "সেটাও দান-সদকা। আর রাস্তা থেকে কষ্টদায়ক বস্তু সরিয়ে দেওয়াও দান-সদকা।”"
)
REF = "আন-নববীর ৪০ হাদিস, হাদিস ২৬"
MAX_FONT = 64

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
  .overlay { position: absolute; inset: 0; background: rgba(0, 10, 30, 0.62); }
  .content { position: absolute; inset: 0; display: flex; flex-direction: column;
             align-items: center; padding: 80px 90px; box-sizing: border-box;
             text-align: center; font-family: 'Hind Siliguri', sans-serif; }
  .textbox { width: 100%; height: 740px; display: flex; align-items: center;
             justify-content: center; }
  .text { color: #ffffff; font-weight: 500; line-height: 1.6; }
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
html = (
    HTML.replace("__BG__", bg64)
    .replace("__TEXT__", htmllib.escape(TEXT))
    .replace("__REF__", htmllib.escape(REF))
    .replace("__MAX__", str(MAX_FONT))
)

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

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1080, "height": 1080})
    page.set_content(html, wait_until="networkidle")
    page.evaluate("document.fonts.ready.then(() => true)")
    size = page.evaluate(FIT_JS)
    print("Final font size:", size)
    page.screenshot(path="card.png")
    browser.close()

print("Card saved: card.png")
