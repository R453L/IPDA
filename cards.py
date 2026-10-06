import base64
import colorsys
import glob
import html as htmllib
import io
import os
import random
import re

from PIL import Image, ImageDraw, ImageFilter
from playwright.sync_api import sync_playwright

FONT_HEAD = (
    '<link href="https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@500;700'
    '&family=Amiri:wght@400;700&display=swap" rel="stylesheet">'
)

LABELS = [
    "আজকের হাদিস",
    "রাসূলুল্লাহ ﷺ বলেছেন",
    "হাদিসের বাণী",
    "প্রিয় নবীজি ﷺ বলেছেন",
]

# id: (mode, width choices, max panel height)
STYLES = {
    "glass": ("auto", [760, 820], 900),
    "frame": ("auto", [760, 840], 900),
    "arch": ("auto", [780, 840], 900),
    "ogee": ("auto", [800, 860], 900),
    "direct": ("direct", [820, 880], 900),
    "directline": ("direct", [800, 860], 900),
    "directleft": ("direct", [780], 700),
    "ribbon": ("auto", [780, 840], 880),
    "pill": ("auto", [760, 820], 880),
    "chamfer": ("auto", [780, 840], 900),
    "brackets": ("auto", [780, 840], 900),
    "barleft": ("auto", [780, 840], 900),
    "bottom": ("auto", [1080], 640),
    "top": ("auto", [1080], 640),
    "side": ("auto", [680], 900),
    "tilt": ("auto", [740, 800], 860),
    "stack": ("auto", [740, 800], 860),
    "offset": ("auto", [740, 800], 860),
    "quote": ("auto", [760, 820], 880),
    "solid": ("solid_dark", [780, 840], 900),
    "cream": ("solid_light", [740, 800], 880),
    "gradient": ("auto", [760, 820], 900),
    "medal": ("auto", [780, 840], 860),
    "double": ("auto", [720, 780], 840),
}

SOLID_DARK = [
    ("#0f2a3d", "#f7f1e1", "#d9b76a", "#f0d28a"),
    ("#0c3b32", "#f6f1e0", "#d4af5f", "#efd38c"),
    ("#4a1424", "#fbefe6", "#e0b77a", "#f3d49a"),
    ("#1d1f2b", "#f5f0e6", "#cfae6b", "#ecd08f"),
    ("#123f4a", "#f4f1e8", "#e3c27d", "#f6dc9c"),
]
SOLID_LIGHT = [
    ("#f8f1e3", "#3a2a1c", "#9a6b2f", "#7a4a14"),
    ("#eef2e6", "#23342a", "#5e7d4f", "#3f6b35"),
    ("#fbeeea", "#4a2a30", "#b0606e", "#9a3a4e"),
    ("#eaf0f6", "#1f3047", "#4f6f9f", "#2f5a96"),
    ("#f4eefa", "#33224a", "#7d5aa8", "#5f3a96"),
]

CSS = """
body { margin: 0; }
.card { width: 1080px; height: 1080px; position: relative; overflow: hidden;
        font-family: 'Hind Siliguri', 'Amiri', sans-serif; color: var(--text); }
.bg { position: absolute; inset: 0; background-size: cover; background-position: center;
      transform: var(--tf); }
.shade { position: absolute; inset: 0; background: var(--shade); }
.panel { position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%);
         width: var(--w); box-sizing: border-box; padding: var(--pt, 56px) 60px 46px;
         display: flex; flex-direction: column; align-items: center; text-align: center;
         isolation: isolate; }
.panel::before { content: ""; position: absolute; inset: 0; z-index: -1; pointer-events: none;
         background: var(--panel); border-radius: var(--r, 40px);
         border: 2px solid var(--border); backdrop-filter: blur(var(--blur, 0px));
         box-shadow: 0 16px 50px rgba(0,0,0,0.18); }
.panel::after { content: ""; position: absolute; display: none; pointer-events: none; }
.label { position: relative; font-weight: 700; font-size: 42px; line-height: 1.3;
         color: var(--accent); }
.orn { display: flex; align-items: center; gap: 14px; margin: 16px 0 22px; }
.orn i { display: block; width: 90px; height: 2px; background: var(--accent); }
.orn b { display: block; width: 12px; height: 12px; background: var(--accent);
         transform: rotate(45deg); }
.ar { font-family: 'Amiri', serif; direction: rtl; width: 100%; color: var(--text);
      font-size: calc(var(--fs) * 0.86); line-height: 2.0; margin: 0 0 14px; }
.text { width: 100%; color: var(--text); font-size: var(--fs); font-weight: 500;
        line-height: 1.6; text-wrap: balance; }
.hl { color: var(--hl); font-weight: 700; }
.nb { white-space: nowrap; }
.sal { font-family: 'Amiri', 'Hind Siliguri', serif; font-size: 1.1em; }
.ref { font-size: 30px; font-weight: 500; color: var(--accent); margin-top: 22px;
       line-height: 1.4; }

.st-frame { --r: 8px; }
.st-frame::before { border-color: var(--accent); }
.st-frame::after { display: block; inset: 12px; border: 1px solid var(--accent);
                   opacity: 0.7; z-index: -1; border-radius: 4px; }
.st-arch { --r: 300px 300px 30px 30px; --pt: 130px; }
.st-ogee { --r: 50% 50% 28px 28px / 24% 24% 28px 28px; --pt: 120px; }

.st-direct::before, .st-directline::before, .st-directleft::before { display: none; }
.st-direct .text, .st-direct .label, .st-direct .ref, .st-direct .ar,
.st-directline .text, .st-directline .label, .st-directline .ref, .st-directline .ar,
.st-directleft .text, .st-directleft .label, .st-directleft .ref, .st-directleft .ar
  { text-shadow: 0 2px 16px rgba(0,0,0,0.55); }
.st-directline { border-top: 3px solid var(--accent); border-bottom: 3px solid var(--accent);
                 padding-top: 50px; padding-bottom: 46px; }
.st-directleft { left: 90px; top: auto; bottom: 90px; transform: none;
                 align-items: flex-start; text-align: left; padding: 10px 20px 10px 44px;
                 border-left: 8px solid var(--accent); }
.st-directleft .orn { margin-left: 0; }
.st-directleft .ar { text-align: right; }

.st-ribbon { --r: 28px; --pt: 84px; }
.st-ribbon .label { position: absolute; top: -34px; left: 50%; transform: translateX(-50%);
         white-space: nowrap; background: var(--accent); color: var(--onaccent);
         padding: 10px 62px; clip-path: polygon(0 0, 100% 0, calc(100% - 24px) 50%,
         100% 100%, 0 100%, 24px 50%); }
.st-pill { --r: 36px; --pt: 84px; }
.st-pill .label { position: absolute; top: -30px; left: 50%; transform: translateX(-50%);
         white-space: nowrap; background: var(--accent); color: var(--onaccent);
         padding: 8px 44px; border-radius: 999px; font-size: 34px; }

.st-chamfer { filter: drop-shadow(0 16px 34px rgba(0,0,0,0.22)); }
.st-chamfer::before { border: none; box-shadow: none; border-radius: 0;
  clip-path: polygon(46px 0, calc(100% - 46px) 0, 100% 46px, 100% calc(100% - 46px),
  calc(100% - 46px) 100%, 46px 100%, 0 calc(100% - 46px), 0 46px); }
.st-chamfer::after { display: block; inset: -4px; z-index: -2; background: var(--accent);
  clip-path: polygon(48px 0, calc(100% - 48px) 0, 100% 48px, 100% calc(100% - 48px),
  calc(100% - 48px) 100%, 48px 100%, 0 calc(100% - 48px), 0 48px); }

.st-brackets { --r: 6px; }
.st-brackets::after { display: block; inset: 16px; z-index: -1;
  background:
   linear-gradient(var(--accent), var(--accent)) 0 0 / 52px 3px no-repeat,
   linear-gradient(var(--accent), var(--accent)) 0 0 / 3px 52px no-repeat,
   linear-gradient(var(--accent), var(--accent)) 100% 0 / 52px 3px no-repeat,
   linear-gradient(var(--accent), var(--accent)) 100% 0 / 3px 52px no-repeat,
   linear-gradient(var(--accent), var(--accent)) 0 100% / 52px 3px no-repeat,
   linear-gradient(var(--accent), var(--accent)) 0 100% / 3px 52px no-repeat,
   linear-gradient(var(--accent), var(--accent)) 100% 100% / 52px 3px no-repeat,
   linear-gradient(var(--accent), var(--accent)) 100% 100% / 3px 52px no-repeat; }

.st-barleft { --r: 14px; align-items: flex-start; text-align: left; padding-left: 80px; }
.st-barleft::before { border-left: 12px solid var(--accent); }
.st-barleft .orn { margin-left: 0; }
.st-barleft .ar { text-align: right; }

.st-bottom { left: 0; right: 0; top: auto; bottom: 0; transform: none; width: auto;
             --r: 60px 60px 0 0; padding-bottom: 80px; }
.st-top { left: 0; right: 0; top: 0; bottom: auto; transform: none; width: auto;
          --r: 0 0 60px 60px; padding-top: 80px; }
.st-side { left: 70px; transform: translateY(-50%); --r: 36px; }

.st-tilt { transform: translate(-50%, -50%) rotate(-2.2deg); --r: 10px; --pt: 70px; }
.st-tilt::after { display: block; top: -22px; left: 50%; width: 160px; height: 46px;
  margin-left: -80px; transform: rotate(3deg); background: var(--accent); opacity: 0.55; }
.st-stack { --r: 18px; }
.st-stack::before { box-shadow: 16px 16px 0 var(--accent-soft), 0 22px 50px rgba(0,0,0,0.2); }
.st-offset { --r: 6px; }
.st-offset::after { display: block; inset: 0; transform: translate(22px, 22px);
  border: 3px solid var(--accent); z-index: -2; border-radius: 6px; }
.st-quote { --r: 40px; --pt: 80px; }
.st-quote::after { display: block; content: "\\201C"; top: -48px; left: 0; right: 0;
  text-align: center; font: 700 200px/1 'Amiri', serif; color: var(--accent);
  opacity: 0.4; z-index: 0; }
.st-quote .orn { display: none; }
.st-quote .label { margin-bottom: 18px; }

.st-solid { --r: 14px; }
.st-solid::before { border: 3px solid var(--accent); }
.st-solid::after { display: block; inset: 12px; border: 1px solid var(--accent);
  opacity: 0.6; z-index: -1; border-radius: 6px; }
.st-cream { --r: 4px; }
.st-cream::before { border: 1px solid var(--accent);
  box-shadow: 0 0 0 10px var(--panel), 0 0 0 11px var(--accent), 0 22px 50px rgba(0,0,0,0.22); }
.st-gradient::before { background: linear-gradient(160deg, var(--panel), var(--panel2)); }
.st-medal { --r: 36px; --pt: 96px; }
.st-medal::after { display: block; top: -48px; left: 50%; width: 96px; height: 96px;
  margin-left: -48px; border-radius: 50%; border: 5px solid var(--accent); z-index: 0;
  background: radial-gradient(circle, var(--accent) 0 10px, transparent 11px), var(--panelsolid); }
.st-double::before { inset: -32px; z-index: -2; border-radius: 64px; background: var(--panel2);
  border: 2px solid var(--accent); }
.st-double::after { display: block; inset: 0; z-index: -1; border-radius: 40px;
  background: var(--panel); }
"""

HTML = """<html><head><meta charset="utf-8">__FONT__
<style>__CSS__</style></head>
<body><div class="card" style="__VARS__">
<div class="bg"></div><div class="shade"></div>
<div class="panel st-__STYLE__" style="--fs:__FS__px">
<div class="label">__LABEL__</div>
<div class="orn"><i></i><b></b><i></i></div>
__ARABIC__
<div class="text">__TEXT__</div>
<div class="ref">__REF__</div>
</div></div></body></html>
"""

FIT_JS = """
(maxh) => {
  const p = document.querySelector('.panel');
  let s = parseInt(p.style.getPropertyValue('--fs'));
  const t = document.querySelector('.text');
  while ((p.offsetHeight > maxh || t.scrollWidth > t.clientWidth + 2) && s > 26) {
    s -= 2;
    p.style.setProperty('--fs', s + 'px');
  }
  return [s, p.offsetHeight];
}
"""


def lum(p):
    r, g, b = [v / 255 for v in p]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def hx(rgb):
    return "#%02x%02x%02x" % tuple(int(max(0, min(1, v)) * 255) for v in rgb)


def list_bases(folder="bases"):
    files = []
    if os.path.isdir(folder):
        for ext in ("jpg", "jpeg", "png", "webp"):
            files += glob.glob(folder + "/*." + ext)
            files += glob.glob(folder + "/*." + ext.upper())
    return sorted(set(files))


def load_base(path):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    s = min(w, h)
    left, top = (w - s) // 2, (h - s) // 2
    return im.crop((left, top, left + s, top + s)).resize((1080, 1080), Image.LANCZOS)


def fallback_base():
    rnd = random.Random()
    a = tuple(rnd.randint(150, 235) for _ in range(3))
    b = tuple(rnd.randint(150, 235) for _ in range(3))
    im = Image.new("RGB", (1080, 1080), a)
    px = ImageDraw.Draw(im)
    for y in range(1080):
        t = y / 1079
        px.line([(0, y), (1080, y)], fill=tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3)))
    return im


def analyze(im):
    small = im.resize((60, 60))
    px = small.load()
    center, edge = [], []
    for y in range(60):
        for x in range(60):
            p = px[x, y]
            if 12 <= x < 48 and 12 <= y < 48:
                center.append(lum(p))
            if x < 9 or x >= 51 or y < 9 or y >= 51:
                edge.append(p)
    avg = sum(center) / len(center)
    er = sum(p[0] for p in edge) / len(edge) / 255
    eg = sum(p[1] for p in edge) / len(edge) / 255
    eb = sum(p[2] for p in edge) / len(edge) / 255
    h, l, s = colorsys.rgb_to_hls(er, eg, eb)
    if s < 0.08:
        h = 0.11
    s = min(max(s, 0.35), 0.7)
    return avg, h, s


def jpeg_b64(im):
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def on_color(hexcol):
    r = int(hexcol[1:3], 16) / 255
    g = int(hexcol[3:5], 16) / 255
    b = int(hexcol[5:7], 16) / 255
    return "#ffffff" if lum((r * 255, g * 255, b * 255)) < 0.55 else "#1b1b1b"


def theme_for(mode, avg, h, s):
    """Return css variable dict for the chosen colour mode."""
    if mode == "solid_dark":
        panel, text, accent, hl = random.choice(SOLID_DARK)
        t = dict(panel=panel, panel2=panel + "e6", text=text, accent=accent, hl=hl,
                 border=accent + "99", blur="0px", shade="transparent", panelsolid=panel)
    elif mode == "solid_light":
        panel, text, accent, hl = random.choice(SOLID_LIGHT)
        t = dict(panel=panel, panel2=panel + "e6", text=text, accent=accent, hl=hl,
                 border=accent + "99", blur="0px", shade="transparent", panelsolid=panel)
    elif mode == "direct":
        accent = hx(colorsys.hls_to_rgb(h, 0.82, s))
        shade = "rgba(0,0,0,0.58)" if avg > 0.5 else "rgba(0,0,0,0.46)"
        t = dict(panel="transparent", panel2="transparent", text="#ffffff", accent=accent,
                 hl="#ffe3a0", border="transparent", blur="0px", shade=shade,
                 panelsolid="#101820")
    else:
        dark = avg < 0.42
        if random.random() < 0.25:
            dark = not dark
        if dark:
            accent = hx(colorsys.hls_to_rgb(h, 0.76, s))
            t = dict(panel="rgba(12,20,34,0.76)", panel2="rgba(30,44,66,0.72)", text="#ffffff",
                     accent=accent, hl=accent, border=accent + "66", blur="8px",
                     shade="transparent", panelsolid="#0c1422")
        else:
            accent = hx(colorsys.hls_to_rgb(h, 0.30, s))
            text = hx(colorsys.hls_to_rgb(h, 0.13, 0.35))
            t = dict(panel="rgba(255,255,255,0.89)",
                     panel2=hx(colorsys.hls_to_rgb(h, 0.93, 0.5)) + "e8",
                     text=text, accent=accent, hl=accent, border=accent + "66",
                     blur="0px", shade="transparent", panelsolid="#ffffff")
    t["onaccent"] = on_color(t["accent"])
    t["accent_soft"] = t["accent"] + "73"
    return t


def build_text(text, highlights):
    marks = []
    raw = text
    for w in highlights or []:
        w = w.strip()
        if len(w) < 2 or w not in raw:
            continue
        if any(w in m or m in w for m in marks):
            continue
        raw = raw.replace(w, "\x01" + w + "\x02", 1)
        marks.append(w)
    s = htmllib.escape(raw)
    s = re.sub(r"(\S{1,13}-\S{1,13})", r'<span class="nb">\1</span>', s)
    s = s.replace("ﷺ", '<span class="sal">ﷺ</span>')
    return s.replace("\x01", '<b class="hl">').replace("\x02", "</b>")


def start_size(n, has_arabic):
    if n < 50:
        s = 76
    elif n < 100:
        s = 66
    elif n < 160:
        s = 58
    elif n < 240:
        s = 50
    elif n < 330:
        s = 44
    else:
        s = 40
    return s - (6 if has_arabic else 0)


class CardRenderer:
    def __init__(self):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()

    def close(self):
        self._browser.close()
        self._pw.stop()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def render(self, spec, out="card.png", style=None, base_path=None):
        """spec keys: text, arabic (optional), label, ref, highlights (list)."""
        style = style or random.choice(list(STYLES.keys()))
        mode, widths, maxh = STYLES[style]
        if base_path is None:
            files = list_bases()
            base_path = random.choice(files) if files else None
        im = load_base(base_path) if base_path else fallback_base()
        avg, h, s = analyze(im)
        t = theme_for(mode, avg, h, s)
        tf = "scaleX(%d) scale(%s)" % (random.choice([1, -1]), random.choice([1.0, 1.04, 1.08]))
        vars_css = "--w:%dpx;--tf:%s;" % (random.choice(widths), tf)
        vars_css += ";".join("--%s:%s" % (k.replace("_", "-"), v) for k, v in t.items())
        arabic = (spec.get("arabic") or "").strip()
        ar_html = '<div class="ar">%s</div>' % htmllib.escape(arabic) if arabic else ""
        page_html = (
            HTML.replace("__FONT__", FONT_HEAD)
            .replace("__CSS__", CSS)
            .replace("__VARS__", vars_css)
            .replace("__STYLE__", style)
            .replace("__FS__", str(start_size(len(spec["text"]), bool(arabic))))
            .replace("__LABEL__", build_text(spec.get("label") or random.choice(LABELS), []))
            .replace("__ARABIC__", ar_html)
            .replace("__TEXT__", build_text(spec["text"], spec.get("highlights")))
            .replace("__REF__", htmllib.escape(spec["ref"]))
        )
        page = self._browser.new_page(viewport={"width": 1080, "height": 1080})
        page.set_content(page_html, wait_until="networkidle")
        page.evaluate("""() => {
            const b = document.querySelector('.bg');
            b.style.backgroundImage = 'url(data:image/jpeg;base64,%s)';
        }""" % jpeg_b64(im))
        page.evaluate("document.fonts.ready.then(() => true)")
        size, height = page.evaluate(FIT_JS, maxh)
        page.screenshot(path=out)
        page.close()
        return {"style": style, "font": size, "height": height,
                "base": os.path.basename(base_path) if base_path else "none"}
