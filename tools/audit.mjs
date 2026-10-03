// Quality audit of the built site in dist/.
//
//   python tools/build.py --release
//   npm install          (once)
//   npm run audit
//
// Serves dist/ locally with gzip (as GitHub Pages does), then for every page:
//   - Lighthouse, mobile and desktop
//   - full-page screenshots at 360, 768 and 1440 px, light and dark
//   - horizontal-overflow and JavaScript-error checks
//   - every link and image: internal targets must exist; external links must answer
// Writes reports/audit.md, reports/lighthouse/*.html and reports/screens/*.png.
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import zlib from 'node:zlib';
import { fileURLToPath } from 'node:url';
import lighthouse from 'lighthouse';
import * as chromeLauncher from 'chrome-launcher';
import puppeteer from 'puppeteer-core';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DIST = path.join(ROOT, 'dist');
const OUT = path.join(ROOT, 'reports');
const PORT = 8123;
const BASE = `http://localhost:${PORT}`;
const WIDTHS = [360, 768, 1440];
const TYPES = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.json': 'application/json',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.webp': 'image/webp', '.ico': 'image/x-icon', '.xml': 'application/xml', '.txt': 'text/plain' };

if (!fs.existsSync(path.join(DIST, 'index.html'))) {
  console.error('dist/ is empty. Run: python tools/build.py --release');
  process.exit(1);
}
fs.mkdirSync(path.join(OUT, 'lighthouse'), { recursive: true });
fs.mkdirSync(path.join(OUT, 'screens'), { recursive: true });

// ---------- static server ----------
function resolveFile(urlPath) {
  let p = decodeURIComponent(urlPath.split('?')[0]);
  if (p.endsWith('/')) p += 'index.html';
  const f = path.join(DIST, p);
  return f.startsWith(DIST) && fs.existsSync(f) && fs.statSync(f).isFile() ? f : null;
}
const server = http.createServer((req, res) => {
  const f = resolveFile(req.url);
  const file = f || path.join(DIST, '404.html');
  let body = fs.readFileSync(file);
  const type = TYPES[path.extname(file)] || 'application/octet-stream';
  const headers = { 'Content-Type': type, 'Cache-Control': 'max-age=600' };
  if (/text|json|javascript|svg|xml/.test(type) && /gzip/.test(req.headers['accept-encoding'] || '')) {
    body = zlib.gzipSync(body);
    headers['Content-Encoding'] = 'gzip';
  }
  res.writeHead(f ? 200 : 404, headers);
  res.end(body);
});
await new Promise(r => server.listen(PORT, r));

const pages = [];
(function walk(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) walk(full);
    else if (e.name === 'index.html') pages.push('/' + path.relative(DIST, path.dirname(full)).split(path.sep).filter(Boolean).join('/') + (dir === DIST ? '' : '/'));
  }
})(DIST);
pages.sort();

const chrome = await chromeLauncher.launch({ chromeFlags: ['--headless=new'] });
const results = [];

// ---------- Lighthouse ----------
for (const p of pages) {
  for (const preset of ['mobile', 'desktop']) {
    const config = preset === 'desktop' ? (await import('lighthouse/core/config/desktop-config.js')).default : undefined;
    const r = await lighthouse(BASE + p, { port: chrome.port, output: 'html', logLevel: 'error' }, config);
    const c = r.lhr.categories;
    const score = k => Math.round(c[k].score * 100);
    const name = (p === '/' ? 'home' : p.replace(/\//g, '-').replace(/^-|-$/g, '')) + '-' + preset;
    fs.writeFileSync(path.join(OUT, 'lighthouse', name + '.html'), r.report);
    const failing = Object.values(r.lhr.audits)
      .filter(a => a.score !== null && a.score < 0.9 && ['binary', 'numeric', 'metricSavings'].includes(a.scoreDisplayMode))
      .map(a => a.id);
    results.push({ page: p, preset, perf: score('performance'), a11y: score('accessibility'), best: score('best-practices'),
      seo: score('seo'), lcp: r.lhr.audits['largest-contentful-paint'].displayValue,
      cls: r.lhr.audits['cumulative-layout-shift'].displayValue, weight: r.lhr.audits['total-byte-weight'].displayValue, failing });
    console.log(`lighthouse ${preset.padEnd(7)} ${p}`);
  }
}

// ---------- screenshots, overflow, JS errors, links ----------
const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${chrome.port}` });
const page = await browser.newPage();
const errors = [];
page.on('pageerror', e => errors.push(`${page.url()}: ${e.message}`));
page.on('console', m => { if (m.type() === 'error') errors.push(`${page.url()}: ${m.text()}`); });
const layout = [];
const links = new Map();
for (const p of pages) {
  for (const scheme of ['light', 'dark']) {
    await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: scheme }]);
    for (const w of WIDTHS) {
      await page.setViewport({ width: w, height: 900 });
      await page.goto(BASE + p, { waitUntil: 'networkidle0' });
      await page.evaluate(async () => {
        for (let y = 0; y < document.documentElement.scrollHeight; y += 400) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 50)); }
      });
      await new Promise(r => setTimeout(r, 1200));
      await page.evaluate(() => window.scrollTo(0, 0));
      // full-page screenshots need every section drawn, including ones the browser is skipping off-screen
      await page.addStyleTag({ content: '* { content-visibility: visible !important; animation: none !important; }' });
      await new Promise(r => setTimeout(r, 400));
      const m = await page.evaluate(() => {
        const de = document.documentElement;
        const wide = [...document.querySelectorAll('body *')].filter(el => {
          const r = el.getBoundingClientRect();
          return r.right > de.clientWidth + 1 && getComputedStyle(el).position !== 'fixed' && !el.closest('.leaflet-container, .site-nav, .table-scroll');
        }).slice(0, 3).map(el => `${el.tagName.toLowerCase()}.${el.className}`);
        const refs = [...document.querySelectorAll('a[href], img[src], link[href], script[src]')].map(el => el.href || el.src);
        return { overflow: wide, refs };
      });
      m.refs.forEach(u => { if (!links.has(u)) links.set(u, p); });
      const name = (p === '/' ? 'home' : p.replace(/\//g, '-').replace(/^-|-$/g, ''));
      await page.screenshot({ path: path.join(OUT, 'screens', `${name}-${scheme}-${w}.png`), fullPage: true });
      layout.push({ page: p, scheme, w, overflow: m.overflow });
    }
  }
}
await browser.disconnect();
await chrome.kill();

const SITE = JSON.parse(fs.readFileSync(path.join(ROOT, 'content', 'site.json'), 'utf8')).base_url;
const broken = [];
const warnings = [];
for (const [u0, from] of links) {
  if (u0.startsWith('mailto:') || u0.startsWith('data:')) continue;
  // Canonical and share URLs point at the live domain; check them against dist/ until launch
  const u = u0.startsWith(SITE) ? BASE + '/' + u0.slice(SITE.length) : u0;
  const url = new URL(u);
  if (url.origin === BASE) {
    if (!resolveFile(url.pathname)) broken.push(`${u} (on ${from}): missing file`);
    if (url.hash && url.pathname === new URL(BASE + from).pathname) {
      const html = fs.readFileSync(resolveFile(url.pathname), 'utf8');
      if (!html.includes(`id="${url.hash.slice(1)}"`)) broken.push(`${u} (on ${from}): no element with that id`);
    }
    continue;
  }
  try {
    const r = await fetch(u, { method: 'GET', redirect: 'follow', signal: AbortSignal.timeout(15000), headers: { 'User-Agent': 'Mozilla/5.0 link-check' } });
    // Some sites refuse automated requests (LinkedIn 999, Medium 403): check those by hand, they are not broken
    if ([401, 403, 429, 999].includes(r.status)) warnings.push(`${u} (on ${from}): HTTP ${r.status}, refuses automated checks`);
    else if (r.status >= 400) broken.push(`${u} (on ${from}): HTTP ${r.status}`);
  } catch (e) {
    const why = String(e.cause?.message || e.message);
    if (/redirect/i.test(why)) warnings.push(`${u} (on ${from}): redirect loop for bots (e.g. a login cookie check), open it in a browser`);
    else broken.push(`${u} (on ${from}): ${why}`);
  }
}
server.close();

// ---------- report ----------
const lines = ['# Site audit', '', `Run ${new Date().toISOString().slice(0, 16).replace('T', ' ')} against dist/, served with gzip.`, '',
  '## Lighthouse', '', '| Page | Device | Performance | Accessibility | Best practices | SEO | LCP | CLS | Weight |', '|---|---|---|---|---|---|---|---|---|'];
for (const r of results) lines.push(`| ${r.page} | ${r.preset} | ${r.perf} | ${r.a11y} | ${r.best} | ${r.seo} | ${r.lcp} | ${r.cls} | ${r.weight} |`);
const weak = results.filter(r => r.failing.length);
if (weak.length) { lines.push('', 'Audits scoring under 0.9:'); weak.forEach(r => lines.push(`- ${r.page} ${r.preset}: ${r.failing.join(', ')}`)); }
const over = layout.filter(l => l.overflow.length);
lines.push('', '## Layout', '', over.length ? over.map(l => `- ${l.page} ${l.scheme} ${l.w}px overflows: ${l.overflow.join(', ')}`).join('\n')
  : `No horizontal overflow on ${pages.length} pages at ${WIDTHS.join(', ')} px, light and dark.`);
lines.push('', '## JavaScript errors', '', errors.length ? [...new Set(errors)].map(e => `- ${e}`).join('\n') : 'None.');
lines.push('', '## Links and images', '', broken.length ? broken.map(b => `- ${b}`).join('\n') : `All ${links.size} links and assets resolve.`);
if (warnings.length) lines.push('', 'Could not be checked automatically:', ...warnings.map(w => `- ${w}`));
fs.writeFileSync(path.join(OUT, 'audit.md'), lines.join('\n') + '\n');
console.log('\n' + lines.join('\n'));
process.exit(broken.length || over.length || errors.length ? 1 : 0);
