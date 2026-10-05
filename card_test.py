import base64
import html as htmllib
import os
import re
import time
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright

KEY = os.environ["POLLINATIONS_API_KEY"]

LABEL = "আজকের হাদিস"
TEXT = (
    "এক ব্যক্তি রাসূলুল্লাহ ﷺ এর কাছে বলল, আমাকে উপদেশ দিন। "
    "রাসূলুল্লাহ ﷺ বললেন, রাগ করো না। লোকটি বারবার বলল, "
    "রাসূলুল্লাহ ﷺ বললেন, রাগ করো না।"
)
REF = "আবূ হুরাইরাহ (রাঃ), আন-নববীর ৪০ হাদিস, হাদিস ১৬"

TAIL = ", no text, no letters, no writing, no people, square composition"

STYLES = [
    {
        "id": "floral",
        "prompt": "delicate watercolor blue hydrangea flowers and green leaves in the four corners, soft white background, large empty clean white space in the center, elegant and airy" + TAIL,
        "panel": "rgba(255,255,255,0.90)", "text": "#23324a", "accent": "#4f6f9f",
        "radius": "44px", "blur": "0px",
    },
    {
        "id": "geometric",
        "prompt": "islamic geometric star pattern frame in teal, blue and purple tones with gold accents, paper-cut style with soft shadows, large empty plain light grey area in the center" + TAIL,
        "panel": "rgba(246,246,248,0.94)", "text": "#1f3b4d", "accent": "#b8862f",
        "radius": "30px", "blur": "0px",
    },
    {
        "id": "arch",
        "prompt": "bright cream wall with an elegant arch outline in gold, olive branch in a white ceramic vase and a brass lantern at the bottom corners, soft window light, photorealistic interior, large empty clean wall area in the center" + TAIL,
        "panel": "rgba(255,250,238,0.82)", "text": "#2d3b2a", "accent": "#a47a2c",
        "radius": "200px 200px 30px 30px", "blur": "0px",
    },
    {
        "id": "sunset",
        "prompt": "peaceful sunset over a calm sea seen from a green coastal hill, olive branches in the foreground corners and a glowing lantern at the bottom, soft golden sky, photorealistic, wide empty sky area in the upper center" + TAIL,
        "panel": "rgba(12,24,38,0.58)", "text": "#ffffff", "accent": "#f2c879",
        "radius": "36px", "blur": "8px",
    },
]

HTML = """
<html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@500;700&family=Amiri&display=swap" rel="stylesheet">
<style>
body { margin: 0; }
.card { width: 1080px; height: 1080px; position: relative; overflow: hidden;
        font-family: 'Hind Siliguri', 'Amiri', sans-serif; __BGCSS__ }
.panel { position: absolute; left: 140px; right: 140px; top: 150px; bottom: 150px;
         box-sizing: border-box; padding: 56px 60px 44px; display: flex;
         flex-direction: column; align-items: center; text-align: center;
         background: __PANEL__; border-radius: __RADIUS__;
         backdrop-filter: blur(__BLUR__); box-shadow: 0 20px 60px rgba(0,0,0,0.18); }
.label { font-size: 40px; font-weight: 700; color: __ACCENT__; flex: none; }
.rule { width: 120px; height: 3px; background: __ACCENT__; margin: 18px 0 22px; flex: none; }
.textbox { flex: 1; min-height: 0; width: 100%; display: flex;
           align-items: center; justify-content: center; }
.text { color: __TEXT__; font-weight: 500; line-height: 1.6; width: 100%; }
.nb { white-space: nowrap; }
.sal { font-family: 'Amiri', 'Hind Siliguri', serif; font-size: 1.1em; }
.ref { font-size: 26px; font-weight: 500; color: __ACCENT__; margin-top: 18px; flex: none; }
</style></head>
<body><div class="card"><div class="panel">
<div class="label">__LABEL__</div><div class="rule"></div>
<div class="textbox"><div class="text">__TEXT__</div></div>
<div class="ref">__REF__</div>
</div></div></body></html>
"""

FIT_JS = """
() => {
  const box = document.querySelector('.textbox');
  const t = document.querySelector('.text');
  let s = 56;
  t.style.fontSize = s + 'px';
  while (t.offsetHeight > box.clientHeight && s > 26) {
    s -= 2;
    t.style.fontSize = s + 'px';
  }
  return s;
}
"""


def gen_bg(prompt, seed):
    url = (
        "https://gen.pollinations.ai/image/" + urllib.parse.quote(prompt)
        + "?model=flux&width=1080&height=1080&nologo=true&seed=" + str(seed)
    )
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0", "Authorization": "Bearer " + KEY}
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                if r.headers.get("Content-Type", "").startswith("image"):
                    return r.read()
        except Exception as e:
            print("Image attempt", attempt + 1, "failed:", type(e).__name__, str(e)[:120])
        time.sleep(8)
    return None


safe = htmllib.escape(TEXT)
safe = re.sub(r"(\S+-\S+)", r'<span class="nb">\1</span>', safe)
safe = safe.replace("ﷺ", '<span class="sal">ﷺ</span>')

with sync_playwright() as p:
    browser = p.chromium.launch()
    for i, st in enumerate(STYLES):
        img = gen_bg(st["prompt"], 100 + i)
        if img:
            b64 = base64.b64encode(img).decode("ascii")
            bgcss = (
                "background-image: url(data:image/jpeg;base64," + b64 + ");"
                "background-size: cover; background-position: center;"
            )
            print(st["id"], "background ok, bytes:", len(img))
        else:
            bgcss = "background: linear-gradient(160deg, #cfd8e6, #f4ecdf);"
            print(st["id"], "background FAILED, using plain gradient")
        page_html = (
            HTML.replace("__BGCSS__", bgcss)
            .replace("__PANEL__", st["panel"])
            .replace("__TEXT__", safe)
            .replace("__ACCENT__", st["accent"])
            .replace("__RADIUS__", st["radius"])
            .replace("__BLUR__", st["blur"])
            .replace("__LABEL__", htmllib.escape(LABEL))
            .replace("__REF__", htmllib.escape(REF))
        )
        page_html = page_html.replace("color: " + st["accent"] + "; margin-top", "color: " + st["accent"] + "; margin-top")
        page = browser.new_page(viewport={"width": 1080, "height": 1080})
        page.set_content(page_html, wait_until="networkidle")
        page.evaluate("document.fonts.ready.then(() => true)")
        page.evaluate("(c) => { document.querySelector('.text').style.color = c; }", st["text"])
        size = page.evaluate(FIT_JS)
        print(st["id"], "font size:", size)
        page.screenshot(path="card_" + st["id"] + ".png")
        page.close()
    browser.close()
