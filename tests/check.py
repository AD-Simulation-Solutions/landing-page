#!/usr/bin/env python3
"""Verification for the ADSS static site (brief section 9, plus extra checks).

    python3 build.py && python3 tests/check.py

Serves dist/ with Python's http.server (a SimpleHTTPRequestHandler subclass that
adds the production security headers parsed from dist/.htaccess, so the real
Content-Security-Policy is enforced, and answers unknown paths with 404.html),
drives Chromium through Playwright and checks every published page.
A second, plain `python3 -m http.server` process is used for the local-preview
smoke test.

Outputs: tests/screenshots/*.png, tests/results.json, tests/results.md.
Exit code 0 only if every check passes.
"""
from __future__ import annotations

import functools
import gzip
import json
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
SHOTS = ROOT / "tests" / "screenshots"
SITE = "https://adss.ai"

PAGES = [
    ("home", "/"),
    ("technology", "/technology/"),
    ("odrmaker", "/odrmaker/"),
    ("traffic-intelligence", "/traffic-intelligence/"),
    ("about", "/about/"),
    ("news", "/news/"),
    ("contact", "/contact/"),
    ("privacy", "/privacy/"),
    ("terms", "/terms/"),
    ("legal-notice", "/legal-notice/"),
    ("404", "/404.html"),
]
NAV_KEY = {"/technology/": "Technology", "/odrmaker/": "ODRMaker", "/traffic-intelligence/": "Traffic Intelligence",
           "/about/": "About", "/news/": "News"}
WIDTHS = [320, 360, 390, 768, 1024, 1280, 1440]
LEGAL = {"/privacy/", "/terms/", "/legal-notice/"}
HYPE = ["revolutionary", "cutting-edge", "cutting edge", "game-changing", "game changer", "world-class",
        "best-in-class", "state-of-the-art", "groundbreaking", "ground-breaking", "unparalleled",
        "next-generation", "disruptive", "seamless", "unleash", "supercharge", "leading provider"]
SUCCESS_TEXT = "Thank you — we'll reply within two business days."
ERROR_TEXT = "Something went wrong. Please email us at info@adss.ai."


# --------------------------------------------------------------------------
# result bookkeeping
# --------------------------------------------------------------------------
class Results:
    def __init__(self) -> None:
        self.checks: list[dict] = []

    def add(self, group: str, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append({"group": group, "name": name, "ok": bool(ok), "detail": detail})
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {group}: {name}" + (f" — {detail}" if detail and not ok else ""))

    @property
    def failed(self) -> list[dict]:
        return [c for c in self.checks if not c["ok"]]


R = Results()


# --------------------------------------------------------------------------
# servers
# --------------------------------------------------------------------------
def production_headers() -> dict[str, str]:
    text = (DIST / ".htaccess").read_text(encoding="utf-8")
    return dict(re.findall(r'Header always set ([\w-]+) "([^"]*)"', text))


class Handler(SimpleHTTPRequestHandler):
    extra: dict[str, str] = {}

    def end_headers(self) -> None:  # noqa: D401
        for k, v in self.extra.items():
            self.send_header(k, v)
        super().end_headers()

    def send_error(self, code, message=None, explain=None):  # mimic ErrorDocument 404
        page = DIST / "404.html"
        if code == 404 and page.exists():
            body = page.read_bytes()
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return
        super().send_error(code, message, explain)

    def log_message(self, *args) -> None:
        pass


def start_server() -> tuple[ThreadingHTTPServer, str]:
    Handler.extra = production_headers()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(DIST)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"127.0.0.1:{srv.server_address[1]}"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# --------------------------------------------------------------------------
# static checks on dist/
# --------------------------------------------------------------------------
class Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str, str]] = []  # (tag, attr, value)
        self.ids: set[str] = set()
        self.tags: list[tuple[str, dict]] = []
        self.marks: list[str] = []
        self._in_mark = 0
        self._mark_buf = ""
        self.text_parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append((tag, a))
        if "id" in a:
            self.ids.add(a["id"])
        for attr in ("href", "src", "action"):
            if attr in a and a[attr] is not None:
                self.links.append((tag, attr, a[attr]))
        if tag == "mark" and "tbc" in (a.get("class") or ""):
            self._in_mark += 1
            self._mark_buf = ""
        if tag in ("script", "style", "title"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag == "mark" and self._in_mark:
            self._in_mark -= 1
            self.marks.append(self._mark_buf)
        if tag in ("script", "style", "title") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._in_mark:
            self._mark_buf += data
        if not self._skip:
            self.text_parts.append(data)


def parse(path: Path) -> tuple[str, Collector]:
    html = path.read_text(encoding="utf-8")
    c = Collector()
    c.feed(html)
    return html, c


def dist_file_for(url_path: str) -> Path:
    p = url_path
    if p.endswith("/"):
        p += "index.html"
    return DIST / p.lstrip("/")


def static_checks() -> dict:
    print("\n== Static checks on dist/ ==")
    tbc: list[dict] = []
    titles, descs = {}, {}
    link_errors: list[str] = []
    for name, url in PAGES:
        f = dist_file_for(url)
        html, c = parse(f)
        g = f"static {url}"
        head = html.split("</head>")[0]
        R.add(g, "lang=en", '<html lang="en">' in html)
        R.add(g, "exactly one <h1>", len(re.findall(r"<h1[\s>]", html)) == 1)
        t = re.search(r"<title>(.*?)</title>", head, re.S)
        d = re.search(r'<meta name="description" content="([^"]*)"', head)
        titles[url], descs[url] = (t.group(1) if t else None), (d.group(1) if d else None)
        R.add(g, "title + description", bool(t and d and t.group(1).strip() and d.group(1).strip()))
        canon = re.search(r'<link rel="canonical" href="([^"]+)"', head)
        R.add(g, "canonical", bool(canon and canon.group(1) == f"{SITE}{url}"), canon.group(1) if canon else "missing")
        for prop in ("og:title", "og:description", "og:url", "og:type", "og:image", "og:image:width", "og:image:height"):
            if f'property="{prop}"' not in head:
                R.add(g, f"meta {prop}", False, "missing")
        R.add(g, "Open Graph set", all(f'property="{p}"' in head for p in ("og:title", "og:description", "og:url", "og:type", "og:image", "og:image:width", "og:image:height"))
              and f'content="{SITE}/assets/img/og-default.png"' in head)
        R.add(g, "twitter:card + theme-color + favicons",
              'name="twitter:card" content="summary_large_image"' in head and 'name="theme-color"' in head
              and 'href="/favicon.ico"' in head and "favicon.svg" in head and "apple-touch-icon.png" in head)
        R.add(g, "landmarks header/nav/main/footer",
              all(re.search(fr"<{t}[\s>]", html) for t in ("header", "nav", "main", "footer")))
        R.add(g, "Privacy Policy link in footer", 'href="/privacy/">Privacy Policy</a>' in html.split("<footer")[1])
        # CSP hygiene
        R.add(g, "no inline style / <style> / handlers",
              not re.search(r"<style[\s>]|\sstyle\s*=|\son[a-z]+\s*=\s*[\"']", html, re.I))
        inline_js = [m for m in re.finditer(r"<script\b([^>]*)>(.*?)</script>", html, re.S)
                     if "application/ld+json" not in m.group(1) and (m.group(2).strip() or "src=" not in m.group(1))]
        R.add(g, "no inline JavaScript", not inline_js)
        R.add(g, 'no href="#"', 'href="#"' not in html)
        # images / svg alternatives
        imgs_ok = all("alt" in a for tag, a in c.tags if tag == "img")
        svgs = [a for tag, a in c.tags if tag == "svg"]
        svg_ok = all(a.get("aria-hidden") == "true" or (a.get("role") == "img" and (a.get("aria-label") or a.get("aria-labelledby"))) for a in svgs)
        R.add(g, "img alt / svg role+label or aria-hidden", imgs_ok and svg_ok)
        # current nav item
        if url in NAV_KEY:
            ok = re.search(fr'<a href="{re.escape(url)}" aria-current="page">{re.escape(NAV_KEY[url])}</a>', html)
            R.add(g, "aria-current on nav item", bool(ok))
        # hype words
        text = " ".join(c.text_parts).lower()
        hits = [w for w in HYPE if w in text]
        R.add(g, "no hype words", not hits, ", ".join(hits))
        # legal specifics
        if url in LEGAL:
            R.add(g, "legal: draft comment", "<!-- DRAFT — to be reviewed by a lawyer before publication -->" in html)
            R.add(g, "legal: Last updated date", bool(re.search(r'Last updated: <time datetime="\d{4}-\d{2}-\d{2}">', html)))
            R.add(g, "legal: table of contents", 'class="toc"' in html)
        # links
        for tag, attr, value in c.links:
            v = value.strip()
            if v == "#" or v == "":
                link_errors.append(f"{url}: empty {attr}")
                continue
            if v.startswith(("mailto:", "tel:")):
                continue
            if v.startswith(("http://", "https://")):
                host = urlsplit(v).hostname or ""
                allowed = host in ("adss.ai", "www.linkedin.com", "formspree.io")
                if not allowed:
                    link_errors.append(f"{url}: unexpected external {attr} {v}")
                if host == "formspree.io" and not (tag == "form" and attr == "action"):
                    link_errors.append(f"{url}: formspree used outside form action")
                continue
            if v.startswith("#"):
                if v[1:] not in c.ids:
                    link_errors.append(f"{url}: fragment {v} has no target")
                continue
            if not v.startswith("/"):
                link_errors.append(f"{url}: not root-relative {v}")
                continue
            parts = urlsplit(v)
            target = dist_file_for(parts.path)
            if not target.is_file():
                link_errors.append(f"{url}: {v} -> {target.relative_to(ROOT)} missing")
                continue
            if tag == "a" and not (parts.path.endswith("/") or parts.path.endswith(".html")):
                link_errors.append(f"{url}: page link without trailing slash {v}")
            if parts.fragment:
                _, tc = parse(target)
                if parts.fragment not in tc.ids:
                    link_errors.append(f"{url}: {v} fragment target missing")
        for m in c.marks:
            tbc.append({"page": url, "text": m})

    R.add("static", "all internal href/src resolve to files in dist/ (incl. #fragments)", not link_errors,
          "; ".join(link_errors[:8]))
    R.add("static", "no [TBC] placeholders left in published pages", not tbc, "; ".join(f"{t['page']}: {t['text']}" for t in tbc[:8]))
    R.add("static", "titles unique", len(set(titles.values())) == len(titles))
    R.add("static", "descriptions unique", len(set(descs.values())) == len(descs))

    # home JSON-LD
    home = (DIST / "index.html").read_text(encoding="utf-8")
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', home, re.S)
    ok = False
    if m:
        data = json.loads(m.group(1))
        ok = (data.get("@type") == "Organization" and data.get("name") == "ADSS Inc." and data.get("url")
              and data.get("logo") and "https://www.linkedin.com/company/ad-sim-solutions" in data.get("sameAs", []))
    R.add("static", "home JSON-LD Organization", ok)

    # sitemap / robots / htaccess / drafts / sizes
    sm = (DIST / "sitemap.xml").read_text(encoding="utf-8")
    locs = re.findall(r"<loc>(.*?)</loc>", sm)
    expected = [f"{SITE}{u}" for _, u in PAGES if u != "/404.html"]
    R.add("static", "sitemap.xml lists exactly the published pages", sorted(locs) == sorted(expected), str(locs))
    robots = (DIST / "robots.txt").read_text(encoding="utf-8")
    R.add("static", "robots.txt has Sitemap line", "Sitemap: https://adss.ai/sitemap.xml" in robots)
    ht = (DIST / ".htaccess").read_text(encoding="utf-8")
    needles = ["Redirect 301 /adss_web_site.html /", "ErrorDocument 404 /404.html", "DirectorySlash On",
               "Options -Indexes", "mod_deflate", "RewriteCond %{HTTPS}", "www\\.adss\\.ai",
               "Strict-Transport-Security", "X-Content-Type-Options", "Referrer-Policy", "Permissions-Policy",
               "Content-Security-Policy", "<IfModule mod_headers.c>", 'Cache-Control "no-cache"', "max-age=31536000, immutable"]
    missing = [n for n in needles if n not in ht]
    R.add("static", ".htaccess directives", not missing, ", ".join(missing))
    csp = production_headers().get("Content-Security-Policy", "")
    R.add("static", "CSP matches brief", csp == "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self' https://formspree.io; form-action 'self' https://formspree.io; frame-ancestors 'none'; base-uri 'self'")
    all_files = [p for p in DIST.rglob("*") if p.is_file()]
    blob = " ".join(p.read_text(encoding="utf-8", errors="ignore") for p in all_files if p.suffix in (".html", ".xml", ".txt"))
    R.add("static", "drafts not published (no research page, no ROADS/UTAC text)",
          not (DIST / "research").exists() and "UTAC" not in blob and "ROADS" not in blob and "/research/" not in blob)
    css = (DIST / "assets/css/site.css").stat().st_size
    js = (DIST / "assets/js/site.js").stat().st_size
    R.add("static", f"site.css ≤ 50 KB ({css:,} B)", css <= 50 * 1024)
    R.add("static", f"site.js < 30 KB ({js:,} B)", js < 30 * 1024)
    jstext = (DIST / "assets/js/site.js").read_text(encoding="utf-8")
    R.add("static", "site.js uses no storage/cookie APIs", not re.search(r"localStorage|sessionStorage|document\.cookie|indexedDB", jstext))
    og = DIST / "assets/img/og-default.png"
    from struct import unpack
    w, h = unpack(">II", og.read_bytes()[16:24])
    R.add("static", "og-default.png is 1200×630", (w, h) == (1200, 630), f"{w}x{h}")
    at = DIST / "apple-touch-icon.png"
    w, h = unpack(">II", at.read_bytes()[16:24])
    R.add("static", "apple-touch-icon.png is 180×180", (w, h) == (180, 180), f"{w}x{h}")
    ico = (DIST / "favicon.ico").read_bytes()
    sizes = [(ico[6 + 16 * i] or 256) for i in range(int.from_bytes(ico[4:6], "little"))]
    R.add("static", "favicon.ico contains 32 px", 32 in sizes, str(sizes))
    return {"tbc": tbc}


# --------------------------------------------------------------------------
# browser checks
# --------------------------------------------------------------------------
INIT_JS = """
window.__csp = [];
document.addEventListener('securitypolicyviolation', e => window.__csp.push(e.violatedDirective + ' ' + (e.blockedURI || '')));
window.__cls = 0;
try {
  new PerformanceObserver(list => { for (const e of list.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; })
    .observe({type: 'layout-shift', buffered: true});
} catch (e) {}
"""

CONTRAST_JS = """
() => {
  const parse = c => { const m = c.match(/rgba?\\(([^)]+)\\)/); if (!m) return null;
    const p = m[1].split(/[\\s,\\/]+/).filter(Boolean).map(Number); return {r:p[0], g:p[1], b:p[2], a: p.length > 3 ? p[3] : 1}; };
  const lin = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const lum = c => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
  const blend = (t, b) => ({r: t.r * t.a + b.r * (1 - t.a), g: t.g * t.a + b.g * (1 - t.a), b: t.b * t.a + b.b * (1 - t.a), a: 1});
  const bgOf = el => { const layers = [];
    for (let n = el; n; n = n.parentElement) { const c = parse(getComputedStyle(n).backgroundColor);
      if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } }
    let bg = {r:255, g:255, b:255, a:1}; for (let i = layers.length - 1; i >= 0; i--) bg = blend(layers[i], bg); return bg; };
  const out = []; const seen = new Set();
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (w.nextNode()) {
    const t = w.currentNode; if (!t.textContent.trim()) continue;
    const el = t.parentElement; if (!el || seen.has(el)) continue; seen.add(el);
    if (el.closest('svg, .visually-hidden, .hp, option')) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility !== 'visible' || cs.display === 'none') continue;
    const r = el.getBoundingClientRect(); if (!r.width || !r.height) continue;
    let op = 1; for (let n = el; n; n = n.parentElement) op *= parseFloat(getComputedStyle(n).opacity);
    if (op < 0.99) continue;
    const bg = bgOf(el); let fg = parse(cs.color); if (fg.a < 1) fg = blend(fg, bg);
    const L1 = lum(fg), L2 = lum(bg); const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const size = parseFloat(cs.fontSize); const bold = parseInt(cs.fontWeight, 10) >= 700;
    const need = (size >= 24 || (bold && size >= 18.66)) ? 3 : 4.5;
    out.push({text: t.textContent.trim().slice(0, 50), ratio: Math.round(ratio * 100) / 100, need, cls: String(el.className)});
  }
  return out;
}
"""

TARGETS_JS = """
() => {
  const sel = '.nav-toggle, .btn, .brand, .link-arrow, .footer-social, .field input:not([type=hidden]):not(#f-gotcha), .field select, .field textarea';
  return Array.from(document.querySelectorAll(sel)).filter(el => {
    const cs = getComputedStyle(el); const r = el.getBoundingClientRect();
    return cs.visibility === 'visible' && cs.display !== 'none' && r.width > 0 && !el.closest('.nav-panel:not(.is-open)') ;
  }).map(el => { const r = el.getBoundingClientRect();
    return {cls: el.className || el.tagName, text: (el.textContent || el.name || '').trim().slice(0, 30), w: Math.round(r.width), h: Math.round(r.height)}; });
}
"""


def browser_checks(host: str) -> dict:
    base = f"http://{host}"
    weights: dict[str, dict] = {}
    contrast_min: dict[str, float] = {}
    SHOTS.mkdir(parents=True, exist_ok=True)
    for old in SHOTS.glob("*.png"):
        old.unlink()

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # ---- per page: widths, screenshots, network, console, cookies ------
        print("\n== Browser checks per page ==")
        for name, url in PAGES:
            g = f"page {url}"
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})
            ctx.add_init_script(INIT_JS)
            foreign: list[str] = []
            errors: list[str] = []
            ctx.on("request", lambda req: foreign.append(req.url)
                   if urlsplit(req.url).scheme not in ("data", "blob") and urlsplit(req.url).netloc != host else None)
            page = ctx.new_page()
            page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda exc: errors.append(str(exc)))

            overflow = []
            csp = []
            for w in WIDTHS:
                page.set_viewport_size({"width": w, "height": 900 if w >= 768 else 780})
                page.goto(base + url, wait_until="networkidle")
                sw, iw = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
                if sw > iw:
                    overflow.append(f"{w}px: scrollWidth {sw} > {iw}")
                csp += page.evaluate("window.__csp")
                if w in (390, 1280):
                    page.screenshot(path=str(SHOTS / f"{name}-{w}.png"), full_page=True, animations="disabled")
                if name == "home" and w in (360, 768):
                    page.screenshot(path=str(SHOTS / f"home-{w}.png"), full_page=True, animations="disabled")
                if w in (390, 1280):
                    res = page.evaluate(CONTRAST_JS)
                    bad = [r for r in res if r["ratio"] < r["need"]]
                    contrast_min[f"{url}@{w}"] = min((r["ratio"] for r in res), default=0)
                    R.add(g, f"text contrast ≥ WCAG AA @{w}", not bad, json.dumps(bad[:4], ensure_ascii=False))
                if w == 390:
                    small = [t for t in page.evaluate(TARGETS_JS) if t["h"] < 44 or t["w"] < 44]
                    R.add(g, "primary controls ≥ 44×44 @390", not small, json.dumps(small[:4]))
                    fs = page.evaluate("Array.from(document.querySelectorAll('input:not([type=hidden]), select, textarea')).map(e => parseFloat(getComputedStyle(e).fontSize))")
                    if fs:
                        R.add(g, "form controls font-size ≥ 16px", min(fs) >= 16, str(min(fs)))
            R.add(g, f"no horizontal scroll at {', '.join(map(str, WIDTHS))}", not overflow, "; ".join(overflow))

            # keyboard: first Tab lands on the skip link, which moves focus to <main>
            page.set_viewport_size({"width": 1280, "height": 900})
            page.goto(base + url, wait_until="networkidle")
            page.keyboard.press("Tab")
            first = page.evaluate("document.activeElement && document.activeElement.className")
            page.keyboard.press("Enter")
            page.wait_for_timeout(100)
            main_focused = page.evaluate("document.activeElement && document.activeElement.id")
            R.add(g, "skip link is first focusable and targets <main>", first == "skip-link" and main_focused == "main",
                  f"{first} -> {main_focused}")
            cls = page.evaluate("window.__cls")
            R.add(g, f"layout shift (CLS {cls:.3f}) < 0.02", cls < 0.02)

            cookies = ctx.cookies()
            storage = page.evaluate("[document.cookie, localStorage.length, sessionStorage.length]")
            R.add(g, "no cookies, no web storage", not cookies and storage == ["", 0, 0], f"{cookies} {storage}")
            R.add(g, "only requests to the local server", not foreign, "; ".join(foreign[:5]))
            R.add(g, "no console errors / CSP violations", not errors and not csp, "; ".join((errors + csp)[:5]))
            ctx.close()

            # transfer size, cold cache, desktop
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})
            page = ctx.new_page()
            reqs: list = []
            page.on("requestfinished", lambda req: reqs.append(req))
            page.goto(base + url, wait_until="networkidle")
            total = 0
            gz = 0
            items = []
            for req in reqs:
                try:
                    s = req.sizes()
                    body = s["responseBodySize"]
                    total += body + s["responseHeadersSize"]
                except Exception:
                    continue
                resp = req.response()
                data = resp.body() if resp else b""
                ctype = (resp.headers.get("content-type", "") if resp else "")
                comp = len(gzip.compress(data, 6)) if any(t in ctype for t in ("text", "javascript", "svg", "json", "xml")) else len(data)
                gz += comp
                items.append({"url": urlsplit(req.url).path, "bytes": len(data), "gzip_est": comp})
            weights[url] = {"requests": len(items), "transfer_bytes": total, "gzip_estimate": gz, "items": items}
            R.add(g, f"page weight {total/1024:.1f} KB ({len(items)} requests) ≤ 1 MB", total <= 1024 * 1024)
            ctx.close()

        # ---- mobile menu ------------------------------------------------------
        print("\n== Mobile menu (390 px) ==")
        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        page = ctx.new_page()
        page.goto(base + "/technology/", wait_until="networkidle")
        toggle = page.locator(".nav-toggle")
        box = toggle.bounding_box()
        R.add("menu", "burger is 44×44 with aria-controls and label 'Menu'",
              box["width"] >= 44 and box["height"] >= 44 and toggle.get_attribute("aria-controls") == "site-menu"
              and toggle.get_attribute("aria-label") == "Menu")
        hh = page.evaluate("document.querySelector('.site-header').getBoundingClientRect().height")
        page.set_viewport_size({"width": 1280, "height": 844})
        hh_desk = page.evaluate("document.querySelector('.site-header').getBoundingClientRect().height")
        page.set_viewport_size({"width": 390, "height": 844})
        R.add("menu", "sticky header 56 px (mobile) / 72 px (≥1024)", hh == 56 and hh_desk == 72, f"{hh} / {hh_desk}")
        R.add("menu", "header is sticky", page.evaluate("getComputedStyle(document.querySelector('.site-header')).position") == "sticky")
        R.add("menu", "closed: aria-expanded=false, links hidden",
              toggle.get_attribute("aria-expanded") == "false" and not page.locator("#site-menu a").first.is_visible())
        toggle.click()
        page.wait_for_timeout(250)
        R.add("menu", "opens on click: aria-expanded=true, links visible",
              toggle.get_attribute("aria-expanded") == "true" and page.locator("#site-menu .nav-list a").first.is_visible())
        page.screenshot(path=str(SHOTS / "menu-open-390.png"))
        rows = page.evaluate("Array.from(document.querySelectorAll('#site-menu .nav-list a')).map(a => Math.round(a.getBoundingClientRect().height))")
        R.add("menu", "rows ≥ 48 px tall", min(rows) >= 48, str(rows))
        pbox = page.locator("#site-menu").bounding_box()
        R.add("menu", "full-screen panel below the header", pbox["width"] == 390 and pbox["y"] + pbox["height"] >= 843, str(pbox))
        R.add("menu", "button 'Request a pilot' at the bottom",
              page.evaluate("(() => { const b = document.querySelector('#site-menu .nav-cta').getBoundingClientRect(); return b.bottom > innerHeight - 80; })()"))
        R.add("menu", "body scroll locked", page.evaluate("getComputedStyle(document.body).overflow") == "hidden")
        R.add("menu", "focus moved into panel", page.evaluate("document.activeElement.closest('#site-menu') !== null"))
        trapped = True
        for _ in range(9):
            page.keyboard.press("Tab")
            inside = page.evaluate("document.activeElement.closest('#site-menu') !== null || document.activeElement.classList.contains('nav-toggle')")
            trapped &= inside
        for _ in range(9):
            page.keyboard.press("Shift+Tab")
            inside = page.evaluate("document.activeElement.closest('#site-menu') !== null || document.activeElement.classList.contains('nav-toggle')")
            trapped &= inside
        R.add("menu", "focus trapped (Tab / Shift+Tab)", trapped)
        R.add("menu", "current page highlighted in panel",
              page.locator('#site-menu a[aria-current="page"]').inner_text() == "Technology")
        sw = page.evaluate("document.documentElement.scrollWidth")
        R.add("menu", "open menu causes no horizontal scroll", sw <= 390)
        page.keyboard.press("Escape")
        page.wait_for_timeout(250)
        R.add("menu", "Esc closes and returns focus to burger",
              toggle.get_attribute("aria-expanded") == "false"
              and page.evaluate("document.activeElement.classList.contains('nav-toggle')")
              and page.evaluate("getComputedStyle(document.body).overflow") != "hidden")
        toggle.click()
        page.wait_for_timeout(200)
        page.set_viewport_size({"width": 1100, "height": 844})
        page.wait_for_timeout(200)
        R.add("menu", "closes when viewport grows to ≥ 1024 px", toggle.get_attribute("aria-expanded") == "false")
        page.set_viewport_size({"width": 390, "height": 844})
        toggle.click()
        page.wait_for_timeout(200)
        page.locator("#site-menu a", has_text="ODRMaker").click()
        page.wait_for_url("**/odrmaker/")
        R.add("menu", "link tap navigates with panel closed",
              page.locator(".nav-toggle").get_attribute("aria-expanded") == "false")
        ctx.close()

        # ---- contact form ---------------------------------------------------
        print("\n== Contact form ==")
        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        page = ctx.new_page()
        posted: list = []
        pending: list = []
        page.route("https://formspree.io/**", lambda route: pending.append(route))
        page.on("request", lambda req: posted.append(req) if "formspree.io" in req.url else None)
        page.goto(base + "/contact/", wait_until="networkidle")
        R.add("form", "no request to Formspree on page load", not posted)
        form = page.locator("form.contact-form")
        R.add("form", "plain POST fallback (action + method)",
              form.get_attribute("action") == "https://formspree.io/f/xnjbwbow" and form.get_attribute("method").upper() == "POST")
        labels_ok = page.evaluate("""Array.from(document.querySelectorAll('form input:not([type=hidden]), form select, form textarea'))
            .every(el => el.id && document.querySelector('label[for="' + el.id + '"]'))""")
        R.add("form", "every input has <label for>", labels_ok)
        attrs = page.evaluate("""(() => { const f = document.querySelector('form.contact-form'); const e = n => f.elements[n];
            return {name: [e('name').autocomplete, e('name').maxLength, e('name').required],
                    company: [e('company').autocomplete, e('company').maxLength, e('company').required],
                    email: [e('email').type, e('email').autocomplete, e('email').required],
                    interest: [e('interest').required, Array.from(e('interest').options).map(o => o.text)],
                    message: [e('message').minLength, e('message').maxLength, e('message').required],
                    gotcha: [e('_gotcha').tabIndex, e('_gotcha').autocomplete, e('_gotcha').getAttribute('aria-hidden'), e('_gotcha').closest('.hp') !== null, e('_gotcha').hasAttribute('style')],
                    subject: [e('_subject').type, e('_subject').value]}; })()""")
        expect = {"name": ["name", 100, True], "company": ["organization", 150, True], "email": ["email", "email", True],
                  "interest": [False, ["Please choose", "Scenario extraction", "ODRMaker", "Traffic Intelligence", "Pilot project", "Other"]],
                  "message": [20, 3000, True], "gotcha": [-1, "off", "true", True, False], "subject": ["hidden", "adss.ai enquiry"]}
        R.add("form", "field attributes match the brief", attrs == expect, json.dumps(attrs))
        hp_box = page.locator("#f-gotcha").bounding_box()
        R.add("form", "honeypot hidden by CSS class", hp_box is None or hp_box["x"] < -1000)

        page.locator("button[type=submit]").click()
        page.wait_for_timeout(150)
        errs = page.locator(".field-error").all_inner_texts()
        R.add("form", "empty submit shows 4 text messages under the fields", len(errs) == 4 and all(len(e) > 10 for e in errs), str(errs))
        R.add("form", "invalid fields marked aria-invalid + aria-describedby",
              page.evaluate("Array.from(document.querySelectorAll('[aria-invalid=true]')).every(e => document.getElementById(e.getAttribute('aria-describedby')))")
              and page.locator("[aria-invalid=true]").count() == 4)
        R.add("form", "focus moves to first invalid field", page.evaluate("document.activeElement.id") == "f-name")
        R.add("form", "nothing sent while invalid", not posted and not pending)

        page.fill("#f-name", "Test Person")
        page.fill("#f-company", "Test GmbH")
        page.fill("#f-email", "not-an-email")
        page.fill("#f-message", "Too short")
        page.locator("button[type=submit]").click()
        page.wait_for_timeout(150)
        errs = page.locator(".field-error").all_inner_texts()
        R.add("form", "email format + message length messages",
              len(errs) == 2 and "valid email" in errs[0] and "20 characters" in errs[1], str(errs))
        R.add("form", "focus on first invalid (email)", page.evaluate("document.activeElement.id") == "f-email")

        page.fill("#f-email", "test.person@example.com")
        page.fill("#f-message", "We would like to test an unprotected left-turn function against local traffic.")
        page.select_option("#f-interest", "Pilot project")
        page.locator("button[type=submit]").click()
        page.wait_for_timeout(200)
        R.add("form", "errors cleared once valid", page.locator(".field-error").count() == 0)
        btn = page.locator("button[type=submit]")
        R.add("form", "sending state: button disabled, text 'Sending…'",
              btn.is_disabled() and btn.inner_text().strip() == "Sending…", btn.inner_text())
        req = posted[-1] if posted else None
        R.add("form", "fetch POST with Accept: application/json",
              bool(req) and req.method == "POST" and req.headers.get("accept") == "application/json")
        body = req.post_data if req else ""
        R.add("form", "payload has fields + _subject + _gotcha",
              bool(body) and all(k in body for k in ('name="name"', 'name="company"', 'name="email"', 'name="interest"', 'name="message"', 'name="_subject"', 'name="_gotcha"')))
        pending.pop(0).fulfill(status=200, content_type="application/json", body='{"ok":true,"next":"/thanks"}')
        page.wait_for_timeout(300)
        status = page.locator(".form-status")
        R.add("form", "success message shown (mocked 200)", status.inner_text().strip() == SUCCESS_TEXT, status.inner_text())
        R.add("form", "status region is aria-live=polite", status.get_attribute("aria-live") == "polite")
        R.add("form", "form reset after success",
              page.evaluate("['f-name','f-company','f-email','f-message'].every(id => document.getElementById(id).value === '')"))
        R.add("form", "button restored", not btn.is_disabled() and btn.inner_text().strip() == "Send request")

        page.fill("#f-name", "Test Person")
        page.fill("#f-company", "Test GmbH")
        page.fill("#f-email", "test.person@example.com")
        page.fill("#f-message", "Second message to check the error state of the form.")
        page.locator("button[type=submit]").click()
        page.wait_for_timeout(200)
        pending.pop(0).fulfill(status=500, content_type="application/json", body='{"error":"x"}')
        page.wait_for_timeout(300)
        R.add("form", "error message shown (mocked 500)", status.inner_text().strip() == ERROR_TEXT, status.inner_text())
        R.add("form", "error message links to info@adss.ai",
              page.locator('.form-status a[href="mailto:info@adss.ai"]').count() == 1)
        page.screenshot(path=str(SHOTS / "contact-form-error-390.png"), full_page=False)
        ctx.close()

        # ---- reduced motion ----------------------------------------------------
        print("\n== Motion ==")
        for motion, want_none in (("no-preference", False), ("reduce", True)):
            ctx = browser.new_context(viewport={"width": 1280, "height": 900}, reduced_motion=motion)
            page = ctx.new_page()
            page.goto(base + "/", wait_until="networkidle")
            names = page.evaluate("Array.from(document.querySelectorAll('.traj-f path')).map(p => getComputedStyle(p).animationName)")
            ok = all(n == "none" for n in names) if want_none else all(n != "none" for n in names)
            R.add("motion", f"hero trajectory animation {'off' if want_none else 'on'} with prefers-reduced-motion: {motion}", ok and bool(names), str(set(names)))
            ctx.close()

        # ---- hero sizing ---------------------------------------------------------
        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        page = ctx.new_page()
        page.goto(base + "/", wait_until="networkidle")
        h390 = page.evaluate("document.querySelector('.hero').getBoundingClientRect().height")
        mh390 = page.evaluate("getComputedStyle(document.querySelector('.hero')).minHeight")
        page.set_viewport_size({"width": 1280, "height": 800})
        mh1280 = page.evaluate("getComputedStyle(document.querySelector('.hero')).minHeight")
        R.add("hero", "phones: hero sizes to content; ≥768 px: min-height = viewport − header",
              mh390 in ("0px", "auto") and mh1280 == "728px", f"390: {mh390} ({h390:.0f}px tall) · 1280×800: {mh1280}")
        ctx.close()

        # ---- 404 behaviour ---------------------------------------------------------
        ctx = browser.new_context()
        page = ctx.new_page()
        resp = page.goto(base + "/does-not-exist/", wait_until="networkidle")
        R.add("404", "unknown URL returns 404 with the 404 page", resp.status == 404 and page.locator("h1").inner_text() == "Page not found")
        ctx.close()
        browser.close()
    return {"weights": weights, "contrast_min": contrast_min}


def preview_smoke_test() -> None:
    """The site must also work with a plain `python3 -m http.server` from dist/."""
    print("\n== Local preview with python3 -m http.server ==")
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(DIST)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        bad = []
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1)
                break
            except Exception:
                time.sleep(0.1)
        for _, url in PAGES:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}{url}", timeout=5) as r:
                    if r.status != 200:
                        bad.append(f"{url} {r.status}")
            except Exception as exc:  # noqa: BLE001
                bad.append(f"{url} {exc}")
        # directory URL without slash is redirected by http.server
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/technology", timeout=5) as r:
            if not r.geturl().endswith("/technology/"):
                bad.append("no redirect to trailing slash")
        R.add("preview", "all pages served (200) by python3 -m http.server", not bad, "; ".join(bad))
    finally:
        proc.terminate()
        proc.wait()


def write_outputs(static: dict, browser: dict) -> None:
    out = {"checks": R.checks, "tbc": static["tbc"], "weights": browser["weights"], "contrast_min": browser["contrast_min"]}
    (ROOT / "tests" / "results.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    groups: dict[str, list] = {}
    for c in R.checks:
        key = c["group"].split(" ")[0]
        groups.setdefault(key, []).append(c)
    lines = ["# Check results", "", f"Total checks: {len(R.checks)} · failed: {len(R.failed)}", "",
             "| Group | Checks | Passed |", "|---|---:|---:|"]
    for key, cs in groups.items():
        lines.append(f"| {key} | {len(cs)} | {sum(c['ok'] for c in cs)} |")
    lines += ["", "## Page weights (cold cache, 1280 px)", "",
              "| Page | Requests | Transferred (local, uncompressed) | Estimated with gzip |", "|---|---:|---:|---:|"]
    for url, w in browser["weights"].items():
        lines.append(f"| `{url}` | {w['requests']} | {w['transfer_bytes']/1024:.1f} KB | {w['gzip_estimate']/1024:.1f} KB |")
    lines += ["", "## [TBC] placeholders", "", "| Page | Placeholder |", "|---|---|"]
    for t in static["tbc"]:
        lines.append(f"| `{t['page']}` | {t['text']} |")
    if R.failed:
        lines += ["", "## Failures", ""] + [f"- {c['group']}: {c['name']} — {c['detail']}" for c in R.failed]
    (ROOT / "tests" / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    if not (DIST / "index.html").exists():
        print("dist/ is missing — run python3 build.py first", file=sys.stderr)
        return 2
    static = static_checks()
    srv, host = start_server()
    try:
        browser = browser_checks(host)
    finally:
        srv.shutdown()
    preview_smoke_test()
    write_outputs(static, browser)
    print(f"\n{len(R.checks) - len(R.failed)}/{len(R.checks)} checks passed.")
    if R.failed:
        print("FAILED:")
        for c in R.failed:
            print(f"  - {c['group']}: {c['name']} — {c['detail']}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
