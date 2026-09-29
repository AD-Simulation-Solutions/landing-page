#!/usr/bin/env python3
"""Generate brand assets into src/ (run once, or whenever the logo changes).

Not part of the stdlib-only build: this script needs Playwright (Chromium) and
Pillow to rasterise the Open Graph image and the icons. `build.py` only copies
the files this script writes.

Outputs
  src/assets/img/logo.svg                       wordmark, brand blue (#1d4999)
  src/assets/img/logo-white.svg                 wordmark, white (dark backgrounds)
  src/brand/logo-color-with-tagline.svg         cleaned copy of the full logo (not published)
  src/root/favicon.svg                          simplified mark (the gear "d")
  src/root/favicon.ico                          16 + 32 px
  src/root/apple-touch-icon.png                 180 px
  src/assets/img/og-default.png                 1200 x 630 Open Graph image
"""
from __future__ import annotations

import io
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "input"
SRC = ROOT / "src"
IMG = SRC / "assets" / "img"
STATIC_ROOT = SRC / "root"

BRAND_BLUE = "#1d4999"
NAVY = "#0f172a"
ORANGE = "#ed7d31"


def _paths(svg_text: str) -> list[str]:
    """Return the `d` attribute of every <path>, whitespace-normalised."""
    ds = re.findall(r'<path[^>]*\sd="([^"]+)"', svg_text, flags=re.S)
    return [re.sub(r"\s+", " ", d).strip() for d in ds]


def wordmark_svg(fill: str) -> str:
    """Wordmark from logo-white.svg with a new fill; Illustrator cruft removed.

    No <style> element and no style="" attribute, so the file is also clean
    under the site's Content-Security-Policy.
    """
    src = (INPUT / "logo-white.svg").read_text(encoding="utf-8")
    ds = _paths(src)
    body = "".join(f'<path d="{d}"/>' for d in ds)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 568 174.2" '
        f'width="568" height="174.2" fill="{fill}">'
        "<title>ADSS</title>"
        f"{body}</svg>\n"
    )


def tagline_logo_svg() -> str:
    src = (INPUT / "logo-color-with-tagline.svg").read_text(encoding="utf-8")
    ds = _paths(src)
    body = "".join(f'<path d="{d}"/>' for d in ds)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 690.2 335" '
        f'width="690.2" height="335" fill="{BRAND_BLUE}">'
        "<title>ADSS — Autonomous Driving Simulation Solutions</title>"
        f"{body}"
        f'<line x1="56" y1="247.9" x2="623.8" y2="247.9" stroke="{ORANGE}" stroke-width="2"/>'
        '<text x="54.9985" y="280.8779" font-family="Arial, Helvetica, sans-serif" '
        f'font-size="31.1721" fill="{BRAND_BLUE}">Autonomous Driving Simulation Solutions</text>'
        "</svg>\n"
    )


def mark_paths() -> list[str]:
    """The gear + "d" glyph of the wordmark (last three paths of logo-white)."""
    ds = _paths((INPUT / "logo-white.svg").read_text(encoding="utf-8"))
    return ds[3:6]


def favicon_svg(radius: float = 14) -> str:
    # Bounding box of the gear "d" in logo-white.svg coordinates:
    # x 153.5 .. 280, y 0.5 .. 171  -> centre (216.75, 85.75), height 170.5
    scale = 46 / 170.5
    tx = 32 - 216.75 * scale
    ty = 32 - 85.75 * scale
    body = "".join(f'<path d="{d}"/>' for d in mark_paths())
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">'
        f'<rect width="64" height="64" rx="{radius}" fill="{BRAND_BLUE}"/>'
        f'<g fill="#ffffff" transform="translate({tx:.3f} {ty:.3f}) scale({scale:.5f})">{body}</g>'
        "</svg>\n"
    )


OG_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0}
body{width:1200px;height:630px;background:#0f172a;position:relative;overflow:hidden;
  font-family:"TeX Gyre Heros","Liberation Sans",Arial,sans-serif}
.grid{position:absolute;inset:0;
  background-image:linear-gradient(rgba(148,163,184,.07) 1px,transparent 1px),
    linear-gradient(90deg,rgba(148,163,184,.07) 1px,transparent 1px);
  background-size:40px 40px}
.glow{position:absolute;inset:0;
  background:radial-gradient(640px 480px at 88% 30%,rgba(37,99,235,.30),transparent 65%)}
.art{position:absolute;left:700px;top:40px;width:600px;height:500px;opacity:.95}
.art svg{width:600px;height:500px}
.art svg text{font:700 10px "Liberation Sans",Arial,sans-serif;letter-spacing:.04em}
.art svg .ego-label{font-size:11px;font-weight:800}
.art .traj-f path{stroke-dasharray:7 6}
.fade{position:absolute;inset:0;background:linear-gradient(90deg,#0f172a 0,#0f172a 640px,rgba(15,23,42,.55) 760px,rgba(15,23,42,0) 900px)}
.content{position:absolute;left:84px;top:0;bottom:0;width:600px;display:flex;flex-direction:column;justify-content:center}
.logo{width:210px;height:auto;display:block}
.rule{width:64px;height:4px;background:#ed7d31;border-radius:2px;margin:40px 0 30px}
h1{color:#fff;font-size:54px;line-height:1.12;margin:0;font-weight:700;letter-spacing:-.01em}
.url{position:absolute;left:84px;bottom:48px;color:#94a3b8;font-size:22px;letter-spacing:.02em}
</style></head><body>
<div class="grid"></div><div class="glow"></div>
<div class="art">__HERO__</div>
<div class="fade"></div>
<div class="content">
  <img class="logo" src="data:image/svg+xml;base64,__LOGO__" alt="">
  <div class="rule"></div>
  <h1>Real-world traffic scenarios for ADAS &amp; AD validation</h1>
</div>
<div class="url">adss.ai</div>
</body></html>"""


def render_pngs() -> None:
    import base64

    from PIL import Image
    from playwright.sync_api import sync_playwright

    fav = favicon_svg()
    touch = favicon_svg(radius=0)  # iOS applies its own mask
    hero = (SRC / "partials" / "svg" / "hero.svg").read_text(encoding="utf-8")
    logo_b64 = base64.b64encode(wordmark_svg("#ffffff").encode()).decode()
    og_html = OG_HTML.replace("__HERO__", hero).replace("__LOGO__", logo_b64)

    with sync_playwright() as p:
        browser = p.chromium.launch()

        def svg_png(svg: str, size: int) -> bytes:
            page = browser.new_page(viewport={"width": size, "height": size})
            page.set_content(
                "<html><body style='margin:0;background:transparent'>"
                f"<div style='width:{size}px;height:{size}px'>"
                + svg.replace('width="64" height="64"', f'width="{size}" height="{size}"', 1)
                + "</div></body></html>"
            )
            png = page.locator("svg").screenshot(omit_background=True)
            page.close()
            return png

        # Chromium misrenders tiny viewports, so rasterise large and downsample.
        big_touch = Image.open(io.BytesIO(svg_png(touch, 720))).convert("RGBA")
        big_touch.resize((180, 180), Image.LANCZOS).save(STATIC_ROOT / "apple-touch-icon.png")

        big_fav = Image.open(io.BytesIO(svg_png(fav, 512))).convert("RGBA")
        ico32 = big_fav.resize((32, 32), Image.LANCZOS)
        ico16 = big_fav.resize((16, 16), Image.LANCZOS)
        ico32.save(
            STATIC_ROOT / "favicon.ico",
            format="ICO",
            sizes=[(16, 16), (32, 32)],
            append_images=[ico16],
        )

        page = browser.new_page(viewport={"width": 1200, "height": 630})
        page.set_content(og_html)
        page.wait_for_timeout(200)
        page.screenshot(path=str(IMG / "og-default.png"), clip={"x": 0, "y": 0, "width": 1200, "height": 630})
        page.close()
        browser.close()

    # Re-save the OG PNG optimised (palette-free, max compression).
    og = Image.open(IMG / "og-default.png").convert("RGB")
    og.save(IMG / "og-default.png", format="PNG", optimize=True)
    touch_img = Image.open(STATIC_ROOT / "apple-touch-icon.png").convert("RGB")
    touch_img.save(STATIC_ROOT / "apple-touch-icon.png", format="PNG", optimize=True)


def main() -> None:
    IMG.mkdir(parents=True, exist_ok=True)
    STATIC_ROOT.mkdir(parents=True, exist_ok=True)
    (IMG / "logo.svg").write_text(wordmark_svg(BRAND_BLUE), encoding="utf-8")
    (IMG / "logo-white.svg").write_text(wordmark_svg("#ffffff"), encoding="utf-8")
    (SRC / "brand").mkdir(exist_ok=True)
    (SRC / "brand" / "logo-color-with-tagline.svg").write_text(tagline_logo_svg(), encoding="utf-8")
    (STATIC_ROOT / "favicon.svg").write_text(favicon_svg(), encoding="utf-8")
    render_pngs()
    for f in sorted([*IMG.iterdir(), *STATIC_ROOT.iterdir()]):
        print(f"{f.relative_to(ROOT)}  {f.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
