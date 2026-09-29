"""Stitch the slide files in artifacts/deck/project/ into one self-contained HTML deck.

    python build_deck.py              -> artifacts/deck.html (full document, open or send as-is)
    python build_deck.py --fragment   -> artifacts/deck.fragment.html (for publishing as an Artifact,
                                         which supplies its own <html>/<head>/<body> skeleton)

The per-slide files stay the source of truth (they also feed the Slides artifact);
rerun this after editing any of them.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DECK = ROOT / "artifacts" / "deck" / "project"

STYLE = """
:root{color-scheme:dark}
html,body{height:100%}
body{margin:0; background:#0B1020; overflow:hidden; font-family:'IBM Plex Sans', Arial, sans-serif}
.stage{position:absolute; left:50%; top:50%; width:1920px; height:1080px;
  transform:translate(-50%,-50%) scale(var(--s,0.5)); transform-origin:center; box-shadow:0 20px 60px rgba(0,0,0,.45)}
.stage > section{position:absolute; inset:0; width:1920px; height:1080px; box-sizing:border-box; overflow:hidden;
  opacity:0; visibility:hidden; transition:opacity .35s ease, visibility 0s linear .35s}
.stage > section.active{opacity:1; visibility:visible; transition:opacity .35s ease}
.stage section *{box-sizing:border-box; margin:0}
.stage section h1{font-size:96px; font-weight:600; line-height:1.1}
.stage section h2{font-size:64px; font-weight:600; line-height:1.15}
.stage section h3{font-size:44px; font-weight:600; line-height:1.2}
.stage section p{font-size:32px; line-height:1.4}
.stage section ul,.stage section ol{padding-left:1.2em; line-height:1.4}
.stage section table{border-collapse:collapse; width:100%}
.stage section th,.stage section td{padding:.35em .6em; border-bottom:1px solid rgba(20,33,61,.18); text-align:left; vertical-align:top}
.stage section th{font-weight:600}
.stage section svg{display:block; flex:none}
.stage section aside{display:none}
.bar{position:fixed; right:16px; bottom:calc(14px + env(safe-area-inset-bottom,0px)); display:flex; align-items:center; gap:6px;
  background:rgba(11,16,32,.72); color:#E8ECF4; border-radius:999px; padding:4px 6px; font:500 13px 'IBM Plex Sans', Arial, sans-serif;
  opacity:.25; transition:opacity .2s}
.bar:hover,.bar:focus-within,body.show-bar .bar{opacity:1}
.bar button{font:inherit; color:inherit; background:transparent; border:0; border-radius:999px; padding:6px 10px; cursor:pointer}
.bar button:hover{background:rgba(255,255,255,.12)}
.bar button:focus-visible{outline:2px solid #F0A263}
.bar .count{min-width:64px; text-align:center; font-variant-numeric:tabular-nums}
.notes{position:fixed; left:16px; right:16px; bottom:calc(64px + env(safe-area-inset-bottom,0px)); max-width:760px; margin:0 auto;
  background:rgba(11,16,32,.92); color:#E8ECF4; border-radius:12px; padding:14px 18px; font:15px/1.55 'IBM Plex Sans', Arial, sans-serif}
.notes b{color:#F0A263; font-weight:600; letter-spacing:.06em; text-transform:uppercase; font-size:12px; display:block; margin-bottom:4px}
@media (prefers-reduced-motion:reduce){.stage > section{transition:none}}
@media print{
  @page{size:1920px 1080px; margin:0}
  html,body{height:auto; overflow:visible; background:#fff}
  .stage{position:static; transform:none; box-shadow:none; width:auto; height:auto}
  .stage > section{position:relative; opacity:1; visibility:visible; page-break-after:always; break-after:page}
  .bar,.notes{display:none}
}
"""

SCRIPT = """
(function(){
  const stage = document.querySelector('.stage');
  const slides = Array.from(stage.querySelectorAll(':scope > section'));
  const count = document.getElementById('count'), notes = document.getElementById('notes'), notesText = document.getElementById('notes-text');
  let i = 0;
  function fit(){ stage.style.setProperty('--s', Math.min(innerWidth/1920, innerHeight/1080)); }
  function show(n, fromHash){
    i = Math.max(0, Math.min(slides.length - 1, n));
    slides.forEach((s, k) => { s.classList.toggle('active', k === i); s.setAttribute('aria-hidden', k === i ? 'false' : 'true'); });
    count.textContent = (i + 1) + ' / ' + slides.length;
    const aside = slides[i].querySelector('aside');
    notesText.textContent = aside ? aside.textContent.trim() : 'No notes for this slide.';
    if (!fromHash && location.hash !== '#' + (i + 1)) history.replaceState(null, '', '#' + (i + 1));
  }
  function fromHash(){ const n = parseInt(location.hash.slice(1), 10); if (n) show(n - 1, true); }
  function toggleNotes(){ notes.hidden = !notes.hidden; }
  document.getElementById('prev').onclick = () => show(i - 1);
  document.getElementById('next').onclick = () => show(i + 1);
  document.getElementById('notes-btn').onclick = toggleNotes;
  addEventListener('keydown', e => {
    if (e.target.closest('button') && (e.key === ' ' || e.key === 'Enter')) return;
    if (['ArrowRight','ArrowDown','PageDown',' '].includes(e.key)) { e.preventDefault(); show(i + 1); }
    else if (['ArrowLeft','ArrowUp','PageUp'].includes(e.key)) { e.preventDefault(); show(i - 1); }
    else if (e.key === 'Home') show(0);
    else if (e.key === 'End') show(slides.length - 1);
    else if (e.key === 'n' || e.key === 'N') toggleNotes();
  });
  stage.addEventListener('click', e => { if (e.target.closest('a')) return; show(e.clientX > innerWidth / 2 ? i + 1 : i - 1); });
  let x0 = null;
  addEventListener('touchstart', e => { x0 = e.touches[0].clientX; }, {passive:true});
  addEventListener('touchend', e => { if (x0 === null) return; const dx = e.changedTouches[0].clientX - x0;
    if (Math.abs(dx) > 40) show(dx < 0 ? i + 1 : i - 1); x0 = null; });
  let t; addEventListener('mousemove', () => { document.body.classList.add('show-bar'); clearTimeout(t);
    t = setTimeout(() => document.body.classList.remove('show-bar'), 1500); });
  addEventListener('resize', fit); addEventListener('hashchange', fromHash);
  fit(); show(0, true); fromHash();
})();
"""


def build(fragment=False):
    index = json.loads((DECK / "deck.json").read_text(encoding="utf-8"))
    slides = []
    for sid in index["order"]:
        html = (DECK / "slides" / f"{sid}.html").read_text(encoding="utf-8").strip()
        if not html.startswith(f'<section id="{sid}"'):
            raise ValueError(f"slide {sid}: file must start with its <section id>")
        slides.append(html)
    fonts = "".join(
        f'<link rel="stylesheet" href="{face["href"]}">\n' for face in index["faces"].values() if face.get("href"))
    head = (f'<title>{index["title"]}</title>\n'
            '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            f'{fonts}<style>{STYLE}</style>\n')
    body = ('<main class="stage" aria-roledescription="slide deck">\n' + "\n".join(slides) + "\n</main>\n"
            '<div class="notes" id="notes" hidden><b>Speaker notes</b><span id="notes-text"></span></div>\n'
            '<nav class="bar" aria-label="Slide controls">'
            '<button id="prev" type="button" aria-label="Previous slide">&#8592;</button>'
            '<span class="count" id="count" aria-live="polite"></span>'
            '<button id="next" type="button" aria-label="Next slide">&#8594;</button>'
            '<button id="notes-btn" type="button" title="Speaker notes (N)">Notes</button></nav>\n'
            f'<script>{SCRIPT}</script>\n')
    if fragment:
        out = ROOT / "artifacts" / "deck.fragment.html"
        out.write_text(head + body, encoding="utf-8")
    else:
        out = ROOT / "artifacts" / "deck.html"
        out.write_text('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                       '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                       + head + '</head>\n<body>\n' + body + '</body>\n</html>\n', encoding="utf-8")
    print(f"wrote {out} ({len(slides)} slides)")


if __name__ == "__main__":
    build(fragment="--fragment" in sys.argv)
