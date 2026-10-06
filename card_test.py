import base64
import colorsys
import glob
import html as htmllib
import io
import os
import random
import re

from PIL import Image
from playwright.sync_api import sync_playwright

LABELS = ["আজকের হাদিস", "রাসূলুল্লাহ ﷺ বলেছেন", "হাদিসের বাণী"]
TEXT = (
    "এক ব্যক্তি রাসূলুল্লাহ ﷺ এর কাছে বলল, আমাকে উপদেশ দিন। "
    "রাসূলুল্লাহ ﷺ বললেন, রাগ করো না। লোকটি বারবার বলল, "
    "রাসূলুল্লাহ ﷺ বললেন, রাগ করো না।"
)
REF = "আবূ হুরাইরাহ (রাঃ), আন-নববীর ৪০ হাদিস, হাদিস ১৬"

SHAPES = [
    ("44px", 56),
    ("200px 200px 30px 30px", 96),
    ("28px", 56),
    ("80px 14px 80px 14px", 64),
]

HTML = """
<html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@500;700&family=Amiri&display=swap" rel="stylesheet">
<style>
body { margin: 0; }
.card { width: 1080px; height: 1080px; position: relative; overflow: hidden;
        font-family: 'Hind Siliguri', 'Amiri', sans-serif; }
.bg { position: absolute; inset: 0; background-size: cover; background-position: center;
      background-image: url(data:image/jpeg;base64,__B64__); transform: __TRANSFORM__; }
.panel { position: absolute; left: __LR__px; right: __LR__px; top: __TB__px; bottom: __TB__px;
         box-sizing: border-box; padding: __PT__px 60px 44px; display: flex;
         flex-direction: column; align-items: center; text-align: center;
         background: __PANEL__; border-radius: __RADIUS__; border: 2px solid __BORDER__;
         backdrop-filter: blur(__BLUR__); box-shadow: 0 20px 60px rgba(0,0,0,0.2); }
.label { font-size: 40px; font-weight: 700; color: __ACCENT__; flex: none; }
.rule { width: 120px; height: 3px; background: __ACCENT__; margin: 18px 0 22px; flex: none; }
.textbox { flex: 1; min-height: 0; width: 100%; display: flex;
           align-items: center; justify-content: center; }
.text { color: __TEXTCOL__; font-weight: 500; line-height: 1.6; width: 100%; }
.nb { white-space: nowrap; }
.sal { font-family: 'Amiri', 'Hind Siliguri', serif; font-size: 1.1em; }
.ref { font-size: 26px; font-weight: 500; color: __ACCENT__; margin-top: 18px; flex: none; }
</style></head>
<body><div class="card"><div class="bg"></div><div class="panel">
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


def lum(p):
    r, g, b = [v / 255 for v in p]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def hx(r, g, b):
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


def load_base(path):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    s = min(w, h)
    left, top = (w - s) // 2, (h - s) // 2
    im = im.crop((left, top, left + s, top + s)).resize((1080, 1080), Image.LANCZOS)
    return im


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


files = []
if os.path.isdir("bases"):
    for ext in ("jpg", "jpeg", "png", "webp"):
        files += glob.glob("bases/*." + ext)
        files += glob.glob("bases/*." + ext.upper())
files = sorted(set(files))
if not files:
    print("No images found in bases/ folder")
    raise SystemExit(1)
print("Images found:", len(files))

picked = random.sample(files, min(6, len(files)))

with sync_playwright() as p:
    browser = p.chromium.launch()
    for i, path in enumerate(picked, 1):
        im = load_base(path)
        dark, accent, textcol = analyze(im)
        radius, pt = random.choice(SHAPES)
        flip = random.choice([1, -1])
        zoom = random.choice([1.0, 1.05, 1.1])
        panel = "rgba(10,18,30,0.62)" if dark else "rgba(255,255,255,0.88)"
        blur = "8px" if dark else "0px"
        page_html = (
            HTML.replace("__B64__", jpeg_b64(im))
            .replace("__TRANSFORM__", "scaleX(%d) scale(%s)" % (flip, zoom))
            .replace("__LR__", str(random.choice([120, 140, 160])))
            .replace("__TB__", str(random.choice([130, 150, 170])))
            .replace("__PT__", str(pt))
            .replace("__PANEL__", panel)
            .replace("__RADIUS__", radius)
            .replace("__BORDER__", accent + "66")
            .replace("__BLUR__", blur)
            .replace("__ACCENT__", accent)
            .replace("__TEXTCOL__", textcol)
            .replace("__LABEL__", prep(random.choice(LABELS)))
            .replace("__TEXT__", prep(TEXT))
            .replace("__REF__", htmllib.escape(REF))
        )
        page = browser.new_page(viewport={"width": 1080, "height": 1080})
        page.set_content(page_html, wait_until="networkidle")
        page.evaluate("document.fonts.ready.then(() => true)")
        size = page.evaluate(FIT_JS)
        out = "card_%d.png" % i
        page.screenshot(path=out)
        page.close()
        print(out, "<-", os.path.basename(path), "| dark:", dark, "| font:", size)
    browser.close()
