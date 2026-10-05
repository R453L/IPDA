import html as htmllib
import re

from playwright.sync_api import sync_playwright

TEXT = (
    "আবূ হুরাইরাহ (রাঃ) থেকে বর্ণিত, তিনি বলেন, এক ব্যক্তি রাসূলুল্লাহ ﷺ এর কাছে "
    "বলল, আমাকে উপদেশ দিন। রাসূলুল্লাহ ﷺ বললেন, রাগ করো না। লোকটি বারবার "
    "বলল, রাসূলুল্লাহ ﷺ বললেন, রাগ করো না।"
)
REF = "আন-নববীর ৪০ হাদিস, হাদিস ১৬"

STAR = (
    "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='120' height='120'>"
    "<g fill='none' stroke='%23d4af5f' stroke-opacity='0.22' stroke-width='1.5'>"
    "<rect x='30' y='30' width='60' height='60'/>"
    "<rect x='30' y='30' width='60' height='60' transform='rotate(45 60 60)'/></g></svg>"
)

DECO = {
    "a": '<div class="arch"></div><div class="arch2"></div>',
    "b": '<div class="panel"></div>',
    "c": '<div class="moon"></div>',
    "d": '<div class="circle"></div><div class="bar"></div>',
}

HTML = """
<html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@500;700&family=Amiri&display=swap" rel="stylesheet">
<style>
body { margin: 0; }
.card { width: 1080px; height: 1080px; position: relative; overflow: hidden;
        font-family: 'Hind Siliguri', 'Amiri', sans-serif; }
.inner { position: absolute; inset: 0; display: flex; flex-direction: column;
         align-items: center; box-sizing: border-box; text-align: center; }
.textbox { flex: 1; min-height: 0; width: 100%; display: flex;
           align-items: center; justify-content: center; }
.text { font-weight: 500; line-height: 1.65; width: 100%; }
.nb { white-space: nowrap; }
.sal { font-family: 'Amiri', 'Hind Siliguri', serif; font-size: 1.1em; }
.ref { font-size: 32px; font-weight: 500; margin-top: 30px; flex: none; }
.orn { flex: none; }

.d-a { background: #f4ecdf; }
.d-a .arch { position: absolute; left: 70px; right: 70px; top: 70px; bottom: 70px;
             border: 3px solid #b8924a; border-radius: 470px 470px 24px 24px; }
.d-a .arch2 { position: absolute; left: 92px; right: 92px; top: 92px; bottom: 92px;
              border: 1px solid rgba(184,146,74,0.55); border-radius: 448px 448px 14px 14px; }
.d-a .inner { padding: 215px 190px 135px; }
.d-a .orn { width: 20px; height: 20px; background: #b8924a; transform: rotate(45deg); margin-bottom: 26px; }
.d-a .text { color: #1d3a33; }
.d-a .ref { color: #9a7432; }

.d-b { background-color: #0b3a30; background-image: url("__STAR__"); }
.d-b .panel { position: absolute; left: 80px; right: 80px; top: 80px; bottom: 80px;
              background: #082c24; border: 2px solid #d4af5f; }
.d-b .panel::after { content: ""; position: absolute; inset: 12px;
                     border: 1px solid rgba(212,175,95,0.45); }
.d-b .inner { padding: 150px 160px 125px; }
.d-b .orn { width: 20px; height: 20px; background: #d4af5f; transform: rotate(45deg); margin-bottom: 26px; }
.d-b .text { color: #f7f1e1; }
.d-b .ref { color: #d4af5f; }

.d-c { background: radial-gradient(circle at 50% 12%, #1f4278 0%, #0c1b3a 48%, #050b1c 100%); }
.d-c::before { content: ""; position: absolute; inset: 0; opacity: 0.7;
  background-image:
    radial-gradient(2px 2px at 12% 22%, #fff, transparent),
    radial-gradient(2px 2px at 82% 14%, #fff, transparent),
    radial-gradient(1.5px 1.5px at 25% 70%, #fff, transparent),
    radial-gradient(2px 2px at 90% 60%, #fff, transparent),
    radial-gradient(1.5px 1.5px at 60% 88%, #fff, transparent),
    radial-gradient(1.5px 1.5px at 8% 90%, #fff, transparent); }
.d-c .moon { position: absolute; top: 80px; left: 50%; margin-left: -10px; width: 80px; height: 80px;
             border-radius: 50%; box-shadow: -20px 8px 0 0 #f0d58a;
             filter: drop-shadow(0 0 18px rgba(240,213,138,0.55)); }
.d-c .inner { padding: 230px 120px 110px; }
.d-c .orn { width: 80px; height: 3px; background: #d4af5f; border-radius: 2px; margin-bottom: 34px; }
.d-c .text { color: #ffffff; }
.d-c .ref { color: #e9cb7d; }

.d-d { background: linear-gradient(145deg, #fbf3ea, #efd9c4); }
.d-d .circle { position: absolute; right: -150px; top: -150px; width: 440px; height: 440px;
               border-radius: 50%; background: rgba(168,103,47,0.13); }
.d-d .bar { position: absolute; left: 105px; top: 130px; bottom: 130px; width: 6px;
            border-radius: 3px; background: #a8672f; }
.d-d .inner { padding: 130px 110px 100px 165px; align-items: stretch; text-align: left; }
.d-d .orn { display: none; }
.d-d .textbox { justify-content: flex-start; }
.d-d .text { color: #3a2417; }
.d-d .ref { color: #a8672f; }
</style></head>
<body><div class="card d-__K__">__DECO__
<div class="inner"><div class="orn"></div>
<div class="textbox"><div class="text">__TEXT__</div></div>
<div class="ref">__REF__</div></div></div></body></html>
"""

FIT_JS = """
() => {
  const box = document.querySelector('.textbox');
  const t = document.querySelector('.text');
  let s = 64;
  t.style.fontSize = s + 'px';
  while (t.offsetHeight > box.clientHeight && s > 26) {
    s -= 2;
    t.style.fontSize = s + 'px';
  }
  return s;
}
"""

safe = htmllib.escape(TEXT)
safe = re.sub(r"(\S+-\S+)", r'<span class="nb">\1</span>', safe)
safe = safe.replace("ﷺ", '<span class="sal">ﷺ</span>')

with sync_playwright() as p:
    browser = p.chromium.launch()
    for k in "abcd":
        page_html = (
            HTML.replace("__STAR__", STAR)
            .replace("__K__", k)
            .replace("__DECO__", DECO[k])
            .replace("__TEXT__", safe)
            .replace("__REF__", htmllib.escape(REF))
        )
        page = browser.new_page(viewport={"width": 1080, "height": 1080})
        page.set_content(page_html, wait_until="networkidle")
        page.evaluate("document.fonts.ready.then(() => true)")
        size = page.evaluate(FIT_JS)
        print("Design", k, "font size:", size)
        page.screenshot(path="card_" + k + ".png")
        page.close()
    browser.close()
