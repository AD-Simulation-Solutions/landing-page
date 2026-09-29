#!/usr/bin/env python3
"""Build the ADSS website: src/ -> dist/.  Python 3 standard library only.

    python3 build.py            rebuild dist/ from scratch
    python3 build.py --drafts   also build the unpublished drafts into
                                preview-drafts/ (never into dist/)

Source layout (see README.md):
    src/pages/*.html        page bodies with a front-matter block
    src/partials/*.html     shared markup ({% include "name" %})
    src/partials/svg/*.svg  inline illustrations ({% svg "name" %})
    src/partials/icons.svg  icon library ({% icon "name" %})
    src/content/news/*.html news items, newest first on /news/ ({% news %})
    src/assets/**           copied to dist/assets/ (CSS is minified)
    src/root/*              copied to the dist/ root (favicons)
    src/htaccess            copied to dist/.htaccess
    src/drafts/*            NOT published (research page, ROADS news item)
"""
from __future__ import annotations

import argparse
import hashlib
import html
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
DIST = ROOT / "dist"
PREVIEW = ROOT / "preview-drafts"
SITE = "https://adss.ai"

# Main navigation: (key, label, url). The key is matched against a page's `nav`.
NAV = [
    ("technology", "Technology", "/technology/"),
    ("odrmaker", "ODRMaker", "/odrmaker/"),
    ("traffic-intelligence", "Traffic Intelligence", "/traffic-intelligence/"),
    ("about", "About", "/about/"),
    ("news", "News", "/news/"),
]

OG_IMAGE = f"{SITE}/assets/img/og-default.png"
OG_IMAGE_ALT = "ADSS — Real-world traffic scenarios for ADAS & AD validation"
LEGAL_DRAFT_COMMENT = "<!-- DRAFT — to be reviewed by a lawyer before publication -->"

ICON_ATTRS = (
    'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"'
)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def esc(value: str) -> str:
    return html.escape(value, quote=True)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_front_matter(text: str, source: Path) -> tuple[dict[str, str], str]:
    """`---` delimited `key: value` lines at the top of a file."""
    m = re.match(r"\A---\n(.*?)\n---\n", text, flags=re.S)
    if not m:
        raise SystemExit(f"{source}: missing front matter")
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise SystemExit(f"{source}: bad front-matter line {line!r}")
        meta[key.strip()] = value.strip()
    return meta, text[m.end():]


def minify_css(css: str) -> str:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{};,>])\s*", r"\1", css)
    css = re.sub(r":\s+", ":", css)
    css = css.replace(";}", "}")
    return css.strip() + "\n"


def short_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:10]


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------
@dataclass
class Page:
    source: Path
    meta: dict[str, str]
    body: str
    url: str
    out: Path
    draft: bool = False
    extra: dict[str, str] = field(default_factory=dict)


class Renderer:
    def __init__(self, drafts: bool) -> None:
        self.drafts = drafts
        self.asset_versions: dict[str, str] = {}
        self.icons = dict(
            re.findall(r'<symbol id="([\w-]+)">(.*?)</symbol>', read(SRC / "partials" / "icons.svg"), flags=re.S)
        )

    # -- directives ---------------------------------------------------------
    def icon(self, name: str, cls: str = "") -> str:
        if name not in self.icons:
            raise SystemExit(f"unknown icon {name!r}")
        classes = f"icon icon-{name}" + (f" {cls}" if cls else "")
        return f'<svg class="{classes}" {ICON_ATTRS}>{self.icons[name].strip()}</svg>'

    def asset(self, url: str) -> str:
        if url not in self.asset_versions:
            raise SystemExit(f"asset {url!r} is not in the build")
        return f"{url}?v={self.asset_versions[url]}"

    def news(self) -> str:
        items = []
        dirs = [SRC / "content" / "news"]
        if self.drafts:
            dirs.append(SRC / "drafts")
        for d in dirs:
            for f in sorted(d.glob("*.html")):
                text = read(f)
                if not text.startswith("---"):
                    continue
                meta, body = parse_front_matter(text, f)
                if meta.get("type") != "news":
                    continue
                items.append((meta, body.strip(), f))
        items.sort(key=lambda it: it[0]["date"], reverse=True)  # newest first
        out = []
        for meta, body, f in items:
            slug = meta.get("slug") or f.stem
            label = meta.get("date_label") or meta["date"]
            out.append(
                f'<li>\n<article class="news-card" id="{esc(slug)}" aria-labelledby="{esc(slug)}-title">\n'
                f'  <p class="news-date">{self.icon("calendar")}<time datetime="{esc(meta["date"])}">{esc(label)}</time></p>\n'
                f'  <div class="news-content">\n'
                f'    <h2 class="news-title" id="{esc(slug)}-title">{meta["title"]}</h2>\n'
                f"    {self.expand(body)}\n"
                f"  </div>\n</article>\n</li>"
            )
        return '<ol class="news-list">\n' + "\n".join(out) + "\n</ol>"

    def expand(self, text: str, depth: int = 0) -> str:
        if depth > 8:
            raise SystemExit("include depth exceeded")

        def include(m: re.Match[str]) -> str:
            return self.expand(read(SRC / "partials" / f"{m.group(1)}.html"), depth + 1)

        def svg(m: re.Match[str]) -> str:
            return read(SRC / "partials" / "svg" / f"{m.group(1)}.svg").strip()

        text = re.sub(r'\{%\s*include\s+"([\w-]+)"\s*%\}', include, text)
        text = re.sub(r'\{%\s*svg\s+"([\w-]+)"\s*%\}', svg, text)
        text = re.sub(
            r'\{%\s*icon\s+"([\w-]+)"(?:\s+"([\w\s-]*)")?\s*%\}',
            lambda m: self.icon(m.group(1), m.group(2) or ""),
            text,
        )
        text = re.sub(r"\{%\s*news\s*%\}", lambda m: self.news(), text)
        text = re.sub(r'\{\{\s*asset\s+"([^"]+)"\s*\}\}', lambda m: self.asset(m.group(1)), text)
        return text

    # -- layout ---------------------------------------------------------------
    def header(self, current: str) -> str:
        items = []
        for key, label, url in NAV:
            cur = ' aria-current="page"' if key == current else ""
            items.append(f'<li><a href="{url}"{cur}>{label}</a></li>')
        cta_cur = ' aria-current="page"' if current == "contact" else ""
        return f"""<a class="skip-link" href="#main">Skip to content</a>
<header class="site-header">
  <div class="container header-bar">
    <a class="brand" href="/"><img src="{self.asset('/assets/img/logo.svg')}" width="92" height="28" alt="ADSS home"></a>
    <nav class="site-nav" aria-label="Main">
      <button class="nav-toggle" type="button" aria-expanded="false" aria-controls="site-menu" aria-label="Menu">{self.icon("menu", "icon-open")}{self.icon("close", "icon-shut")}</button>
      <div class="nav-panel" id="site-menu">
        <ul class="nav-list">
          {(chr(10) + "          ").join(items)}
        </ul>
        <a class="btn btn--primary btn--sm nav-cta" href="/contact/"{cta_cur}>Request a pilot</a>
      </div>
    </nav>
  </div>
</header>"""

    def head(self, page: Page) -> str:
        m = page.meta
        title = m["title"]
        desc = m["description"]
        canonical = f"{SITE}{page.url}"
        og_title = m.get("og_title", title)
        robots = '\n<meta name="robots" content="noindex">' if m.get("noindex") == "true" or page.draft else ""
        jsonld = ""
        if m.get("jsonld") == "organization":
            jsonld = (
                '\n<script type="application/ld+json">\n'
                "{\n"
                '  "@context": "https://schema.org",\n'
                '  "@type": "Organization",\n'
                '  "name": "ADSS Inc.",\n'
                f'  "url": "{SITE}/",\n'
                f'  "logo": "{SITE}/assets/img/logo.svg",\n'
                '  "email": "info@adss.ai",\n'
                '  "sameAs": ["https://www.linkedin.com/company/ad-sim-solutions"]\n'
                "}\n</script>"
            )
        return f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">{robots}
<link rel="canonical" href="{esc(canonical)}">
<meta name="theme-color" content="#ffffff">
<meta property="og:type" content="{esc(m.get('og_type', 'website'))}">
<meta property="og:site_name" content="ADSS">
<meta property="og:locale" content="en_US">
<meta property="og:title" content="{esc(og_title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:image" content="{OG_IMAGE}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{esc(OG_IMAGE_ALT)}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/favicon.ico" sizes="32x32">
<link rel="icon" href="{self.asset('/favicon.svg')}" type="image/svg+xml">
<link rel="apple-touch-icon" href="{self.asset('/apple-touch-icon.png')}">
<link rel="stylesheet" href="{self.asset('/assets/css/site.css')}">
<script src="{self.asset('/assets/js/site.js')}" defer></script>{jsonld}"""

    def render(self, page: Page) -> str:
        body = self.expand(page.body).strip()
        top = "<!DOCTYPE html>\n"
        if page.meta.get("legal_draft") == "true":
            top += LEGAL_DRAFT_COMMENT + "\n"
        body_class = page.meta.get("body_class", "")
        cls = f' class="{esc(body_class)}"' if body_class else ""
        return (
            f"{top}<html lang=\"en\">\n<head>\n{self.head(page)}\n</head>\n<body{cls}>\n"
            f"{self.header(page.meta.get('nav', ''))}\n"
            f'<main id="main" tabindex="-1">\n{body}\n</main>\n'
            f"{self.expand(read(SRC / 'partials' / 'footer.html')).strip()}\n"
            "</body>\n</html>\n"
        )


# --------------------------------------------------------------------------
# build steps
# --------------------------------------------------------------------------
def load_pages(drafts: bool) -> list[Page]:
    pages: list[Page] = []
    sources = [(p, False) for p in sorted((SRC / "pages").glob("*.html"))]
    if drafts:
        sources += [(p, True) for p in sorted((SRC / "drafts").glob("*.html"))]
    for path, is_draft in sources:
        meta, body = parse_front_matter(read(path), path)
        if meta.get("type") == "news":  # news items are rendered by {% news %}
            continue
        for key in ("title", "description", "url"):
            if key not in meta:
                raise SystemExit(f"{path}: front matter needs {key!r}")
        url = meta["url"]
        if url.endswith("/"):
            out = Path(url.strip("/")) / "index.html" if url != "/" else Path("index.html")
        else:
            out = Path(url.lstrip("/"))
        pages.append(Page(source=path, meta=meta, body=body, url=url, out=out, draft=is_draft))
    return pages


def copy_assets(out_dir: Path, r: Renderer) -> None:
    for src in sorted((SRC / "assets").rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(SRC)
        dst = out_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        data = src.read_bytes()
        if src.suffix == ".css":
            data = minify_css(data.decode("utf-8")).encode("utf-8")
        dst.write_bytes(data)
        r.asset_versions["/" + rel.as_posix()] = short_hash(data)
    for src in sorted((SRC / "root").iterdir()):
        dst = out_dir / src.name
        shutil.copyfile(src, dst)
        r.asset_versions["/" + src.name] = short_hash(src.read_bytes())
    shutil.copyfile(SRC / "htaccess", out_dir / ".htaccess")


def write_meta_files(out_dir: Path, pages: list[Page]) -> None:
    urls = [p.url for p in pages if p.meta.get("sitemap", "true") == "true" and not p.draft]
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        lines.append(f"  <url><loc>{SITE}{u}</loc></url>")
    lines.append("</urlset>")
    (out_dir / "sitemap.xml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out_dir / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n", encoding="utf-8"
    )


FORBIDDEN = [
    (re.compile(r"<style[\s>]", re.I), "<style> block (CSP style-src 'self')"),
    (re.compile(r"\sstyle\s*=", re.I), 'inline style="" attribute (CSP)'),
    (re.compile(r"\son[a-z]+\s*=\s*[\"']", re.I), "inline event handler (CSP)"),
    (re.compile(r'href="#"'), 'empty href="#"'),
    (re.compile(r"localStorage|sessionStorage|document\.cookie"), "storage/cookie API"),
]


def validate(out_dir: Path, pages: list[Page]) -> list[str]:
    errors: list[str] = []
    for page in pages:
        text = read(out_dir / page.out)
        where = page.out.as_posix()
        for rx, what in FORBIDDEN:
            if rx.search(text):
                errors.append(f"{where}: {what}")
        for m in re.finditer(r"<script\b([^>]*)>(.*?)</script>", text, flags=re.S | re.I):
            attrs, content = m.group(1), m.group(2)
            if "application/ld+json" in attrs:
                continue
            if "src=" not in attrs or content.strip():
                errors.append(f"{where}: inline <script> (CSP script-src 'self')")
        if len(re.findall(r"<h1[\s>]", text)) != 1:
            errors.append(f"{where}: must contain exactly one <h1>")
        if "{%" in text or "{{" in text:
            errors.append(f"{where}: unexpanded template directive")
    js = read(out_dir / "assets" / "js" / "site.js")
    for rx, what in FORBIDDEN[-1:]:
        if rx.search(js):
            errors.append(f"site.js: {what}")
    return errors


def build(drafts: bool = False) -> Path:
    out_dir = PREVIEW if drafts else DIST
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    r = Renderer(drafts=drafts)
    copy_assets(out_dir, r)
    pages = load_pages(drafts)
    urls = [p.url for p in pages]
    if len(urls) != len(set(urls)):
        raise SystemExit("duplicate page URLs")
    titles = [p.meta["title"] for p in pages]
    if len(titles) != len(set(titles)):
        raise SystemExit("page titles must be unique")

    for page in pages:
        dst = out_dir / page.out
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(r.render(page), encoding="utf-8")
    write_meta_files(out_dir, pages)

    errors = validate(out_dir, pages)
    if errors:
        print("\n".join("ERROR " + e for e in errors), file=sys.stderr)
        raise SystemExit(1)

    total = 0
    print(f"Built {len(pages)} pages into {out_dir.relative_to(ROOT)}/ ({date.today().isoformat()})")
    for page in pages:
        size = (out_dir / page.out).stat().st_size
        total += size
        flag = "  [draft]" if page.draft else ""
        print(f"  {page.url:<26} {page.out.as_posix():<34} {size:>7,} B{flag}")
    css = (out_dir / "assets" / "css" / "site.css").stat().st_size
    js = (out_dir / "assets" / "js" / "site.js").stat().st_size
    print(f"  site.css {css:,} B (limit 50 KB) · site.js {js:,} B")
    if css > 50 * 1024:
        raise SystemExit("site.css exceeds 50 KB")
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drafts", action="store_true", help="build drafts into preview-drafts/ (not dist/)")
    args = ap.parse_args()
    build(drafts=args.drafts)


if __name__ == "__main__":
    main()
