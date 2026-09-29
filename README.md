# adss.ai — static website (release 1)

Plain HTML + CSS + a small vanilla JS file, assembled from sources by a
standard-library Python build script. No framework, no CDN, no cookies, no
analytics, no third-party requests at page load. The only external endpoint is
Formspree, contacted when the contact form is submitted.

```
build.py              build script (Python 3 stdlib only)  src/ -> dist/
src/
  pages/              one file per page: front matter + page body
  partials/           header parts, footer, CTA band, pipeline, icons.svg
  partials/svg/       inline illustrations (hero, ODRMaker, Traffic Intelligence)
  content/news/       news items, one file each (newest first on /news/)
  assets/             css/site.css (source, minified on build), js/site.js, img/
  root/               favicon.svg, favicon.ico, apple-touch-icon.png (dist root)
  brand/              cleaned full logo with tagline (not published)
  htaccess            becomes dist/.htaccess
  drafts/             UNPUBLISHED: research page + ROADS news item
tools/make_assets.py  regenerates logos, favicons and the OG image (Playwright + Pillow)
tests/check.py        Playwright verification (see "Checks")
dist/                 the deployable site: upload its contents to OVH `www/`
```

## Build

```sh
python3 build.py
```

`build.py` deletes and rebuilds `dist/` from scratch: it assembles every page
(head, header, body, footer), copies assets, minifies the CSS, appends a
`?v=<content hash>` to every asset URL (so `/assets/` can be cached for a year),
and writes `sitemap.xml`, `robots.txt` and `.htaccess`. The build fails if a
page contains inline styles, `<style>`, inline scripts or event handlers
(forbidden by the Content-Security-Policy), `href="#"`, or not exactly one `<h1>`.

## Preview locally

```sh
python3 build.py
cd dist && python3 -m http.server 8000
# open http://localhost:8000/
```

All internal links are root-relative with a trailing slash (`/technology/`), so
the site must be served from the root of a web server. Opening the files
directly with `file://` does not work. The plain Python server does not send
the production security headers and does not use `404.html`; `tests/check.py`
uses a server that does both.

## Checks

```sh
pip install playwright --break-system-packages   # only if the package is missing
python3 build.py && python3 tests/check.py
```

Chromium must already be available to Playwright (`PLAYWRIGHT_BROWSERS_PATH`).
The script checks all 11 published pages at 320–1440 px (no horizontal scroll),
network requests (local only), cookies and storage, console errors and CSP
violations (the production CSP is read from `dist/.htaccess` and enforced),
the mobile menu, every internal link and `#fragment`, the contact form with a
mocked Formspree response, contrast, target sizes, layout shift, reduced
motion, meta tags, sitemap and drafts. It saves screenshots to
`tests/screenshots/`, a summary to `tests/results.md` and details to
`tests/results.json`. Exit code 0 means everything passed.

## Editing content

- **Pages**: `src/pages/<name>.html`. The block between `---` lines holds
  `title`, `description`, `url`, and optionally `nav` (highlighted menu item),
  `jsonld`, `legal_draft`, `noindex`, `sitemap: false`.
- **Shared parts**: `{% include "cta-band" %}`, `{% include "pipeline" %}`,
  `{% svg "hero" %}`, `{% icon "arrow" %}`, `{{ asset "/assets/img/logo.svg" }}`.
- **News**: add a file to `src/content/news/` like the existing one
  (`type: news`, `date: YYYY-MM-DD`, `date_label`, `slug`, `title`, then the
  text). The list on `/news/` is sorted newest first.
- **Placeholders**: as of 28 September 2026 there are none. If a value is
  still open in the future, wrap it in `<mark class="tbc">…</mark>` (it is shown
  highlighted); `tests/check.py` fails while any such mark is left in `dist/`.
  The street address is intentionally not published yet. When the legal texts
  are approved, remove the `legal_draft: true` line (it adds the "DRAFT — to be
  reviewed by a lawyer" HTML comment) and update the "Last updated" date.
- **Logos, favicons, OG image**: edit `tools/make_assets.py` and run
  `python3 tools/make_assets.py` (needs Playwright and Pillow), then rebuild.

### Drafts (ROADS consortium) — not published

`src/drafts/research.html` and `src/drafts/news-roads.html` are never written to
`dist/`, linked or listed in the sitemap. Publication needs written approval
from UTAC. For an internal preview:

```sh
python3 build.py --drafts          # builds into preview-drafts/, NOT dist/
cd preview-drafts && python3 -m http.server 8001   # /research/ and /news/
```

Never upload `preview-drafts/`. After approval: move `news-roads.html` to
`src/content/news/`, move `research.html` to `src/pages/`, remove its
`noindex`/`sitemap` lines, add it to the menu in `build.py` (`NAV`) if wanted,
and rebuild.

## Deploy to OVHcloud (FTP)

1. **Certificate first.** In the OVHcloud Control Panel → *Web Cloud* →
   *Hosting plans* → your plan → *Multisite*, make sure both `adss.ai` and
   `www.adss.ai` point to the `www` folder and have SSL enabled (Let's Encrypt).
   The `.htaccess` forces HTTPS and sends HSTS, so HTTPS must work before upload.
2. **FTP credentials.** Same plan → *FTP-SSH* tab: server name
   (`ftp.clusterXXX.hosting.ovh.net`), login, and *Change password* if needed.
3. **Build and test locally**: `python3 build.py && python3 tests/check.py`.
4. **Upload the contents of `dist/` into `www/`** — the files and folders
   inside `dist/`, not the `dist` folder itself. Include the hidden
   `.htaccess` file.
   - *FileZilla*: Site Manager → protocol SFTP (port 22, if your plan offers
     SSH) or "FTP – explicit FTP over TLS" (port 21). Enable
     *Server → Force showing hidden files*. Open `www/` on the right, select
     everything inside `dist/` on the left, upload, and overwrite.
   - *Command line* (lftp):
     ```sh
     lftp -u LOGIN ftp.clusterXXX.hosting.ovh.net \
       -e "set ftp:ssl-force true; mirror -R --verbose dist/ www/; bye"
     ```
     Adding `--delete` also removes files on the server that are not in
     `dist/` (for example the old one-page site). Check what is in `www/`
     first.
5. **Verify** after upload:
   ```sh
   curl -sI http://adss.ai/            # 301 -> https://adss.ai/
   curl -sI https://www.adss.ai/       # 301 -> https://adss.ai/
   curl -sI https://adss.ai/adss_web_site.html   # 301 -> /
   curl -sI https://adss.ai/ | grep -iE "strict-transport|content-security|x-content-type|referrer|permissions"
   curl -s -o /dev/null -w "%{http_code}\n" https://adss.ai/missing-page/   # 404
   ```
   Then open the site on a phone, submit the contact form once and confirm the
   email arrives (the first Formspree submission may ask you to confirm the
   form address).

If `http → https` ends in a redirect loop (possible on hosting plans where TLS
is terminated in front of Apache), replace the two HTTPS `RewriteCond` lines in
`src/htaccess` with `RewriteCond %{SERVER_PORT} ^80$`, rebuild and upload
`.htaccess` again.

## Adding video later

Release 1 has no video. Rules for later: host files yourself under
`/assets/video/` (the CSP only allows same-origin media), never autoplay with
sound, and keep every script in `assets/js/site.js` (no inline JavaScript under
the CSP).

### Click-to-play video (any page)

```html
<figure class="video">
  <video controls playsinline preload="none"
         poster="/assets/video/scenario-extraction-poster.jpg"
         width="1280" height="720">
    <source src="/assets/video/scenario-extraction.mp4" type="video/mp4">
  </video>
  <figcaption>Short caption describing the video.</figcaption>
</figure>
```

```css
.video { margin: 0; }
.video video { display: block; width: 100%; height: auto; aspect-ratio: 16 / 9;
  border-radius: 12px; background: #0f172a; }
.video figcaption { margin-top: .5rem; color: var(--muted); font-size: .9375rem; }
```

`preload="none"` means nothing but the poster is downloaded until the visitor
presses play; `aspect-ratio` (and `width`/`height`) reserve the space, so there
is no layout shift. Add captions (`<track kind="captions">`) if the video has
speech.

### Desktop-only hero background video (loaded by JS)

Inside `<section class="hero">`, as the first child:

```html
<div class="hero-video" data-src="/assets/video/hero.mp4"
     data-poster="/assets/video/hero-poster.jpg" aria-hidden="true"></div>
<button class="hero-video-toggle" type="button" hidden>Pause background video</button>
```

```css
.hero-video { position: absolute; inset: 0; z-index: 0; opacity: .35; }
.hero-video video { width: 100%; height: 100%; object-fit: cover; }
.hero-video-toggle { position: absolute; z-index: 2; right: 1rem; bottom: 1rem; }
```

Append to `assets/js/site.js`:

```js
(function () {
  var slot = document.querySelector('.hero-video[data-src]');
  if (!slot) return;
  var wide = window.matchMedia('(min-width: 768px)');
  var calm = window.matchMedia('(prefers-reduced-motion: reduce)');
  var toggle = document.querySelector('.hero-video-toggle');
  function load() {
    if (!wide.matches || calm.matches || slot.firstChild) return;
    var v = document.createElement('video');
    v.muted = true; v.loop = true; v.playsInline = true; v.autoplay = true;
    v.setAttribute('muted', ''); v.setAttribute('playsinline', '');
    v.preload = 'auto';
    v.poster = slot.getAttribute('data-poster') || '';
    v.src = slot.getAttribute('data-src');
    slot.appendChild(v);
    var p = v.play(); if (p && p.catch) p.catch(function () {});
    if (toggle) {            // WCAG 2.2.2: moving content needs a pause control
      toggle.hidden = false;
      toggle.addEventListener('click', function () {
        if (v.paused) { v.play(); toggle.textContent = 'Pause background video'; }
        else { v.pause(); toggle.textContent = 'Play background video'; }
      });
    }
  }
  load();
  if (wide.addEventListener) wide.addEventListener('change', load);
})();
```

Phones, and visitors who prefer reduced motion, never download the video.
