#!/usr/bin/env python3
"""Build the self-contained Persian HTML guide from Markdown."""
from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import markdown

from tx import __version__

DOCS = ROOT / "docs"
MD = DOCS / "راهنمای-فارسی.md"
HTML = DOCS / "راهنمای-فارسی.html"
FONT = ROOT / "tx" / "assets" / "fonts" / "Vazirmatn[wght].ttf"
SHOT = DOCS / "gui-screenshot.png"


def data_uri(path: Path, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def main() -> int:
    text = MD.read_text(encoding="utf-8")
    body = markdown.markdown(text, extensions=["fenced_code", "tables", "toc", "sane_lists"])
    if SHOT.exists():
        body = body.replace('src="gui-screenshot.png"', f'src="{data_uri(SHOT, "image/png")}"')
    font_css = ""
    if FONT.exists():
        font_css = f"@font-face {{ font-family:'Vazirmatn'; src:url('{data_uri(FONT, 'font/ttf')}') format('truetype'); font-weight:100 900; }}"
    css = """
    :root { color-scheme: light; --bg:#f3f5f7; --surface:#fff; --text:#17212b; --muted:#68788a; --accent:#0e7c66; --border:#e3e8ee; --soft:#e7f4f0; }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:var(--text); font-family:'Vazirmatn',Tahoma,sans-serif; line-height:2; }
    main { max-width:920px; margin:32px auto; background:var(--surface); border:1px solid var(--border); border-radius:20px; padding:40px 48px; box-shadow:0 8px 30px rgba(20,32,44,.06); }
    h1,h2,h3 { line-height:1.6; color:var(--text); }
    h1 { font-size:28px; margin-top:0; }
    h2 { font-size:21px; margin-top:36px; padding-bottom:8px; border-bottom:1px solid var(--border); }
    h3 { font-size:17px; margin-top:24px; }
    p,li { font-size:15px; }
    a { color:var(--accent); }
    code { font-family:Consolas,'DejaVu Sans Mono',monospace; background:var(--soft); color:#0a5c4c; padding:2px 6px; border-radius:6px; font-size:13px; direction:ltr; unicode-bidi:embed; }
    pre { background:#0f1419; color:#e8eef4; padding:16px 18px; border-radius:12px; overflow:auto; direction:ltr; text-align:left; line-height:1.7; }
    pre code { background:transparent; color:inherit; padding:0; }
    img { max-width:100%; border-radius:14px; border:1px solid var(--border); box-shadow:0 6px 24px rgba(20,32,44,.08); }
    blockquote { border-right:4px solid var(--accent); margin:16px 0; padding:8px 16px; background:var(--soft); border-radius:8px; }
    .badge { display:inline-block; background:var(--soft); color:var(--accent); border-radius:999px; padding:4px 12px; font-size:12px; font-weight:700; margin-bottom:12px; }
    footer { margin-top:40px; color:var(--muted); font-size:13px; border-top:1px solid var(--border); padding-top:16px; }
    @media (max-width:700px){ main{margin:0;border-radius:0;padding:24px;} }
    """
    html = f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>راهنمای TX</title>
<style>{font_css}{css}</style>
</head>
<body>
<main>
<span class="badge">مستندات فارسی · نسخهٔ {__version__} · Created by Matt</span>
{body}
<footer>TX · ساخته‌شده توسط Matt · پردازش محلی · بدون آپلود فایل‌ها.</footer>
</main>
</body>
</html>
"""
    HTML.write_text(html, encoding="utf-8")
    package_docs = ROOT / "tx" / "docs"
    package_docs.mkdir(parents=True, exist_ok=True)
    for file in (HTML, MD, SHOT):
        if file.exists():
            (package_docs / file.name).write_bytes(file.read_bytes())
    print(f"Wrote {HTML} ({HTML.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
