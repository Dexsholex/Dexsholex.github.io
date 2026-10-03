// Print the one-page capability statement to PDF, once per language.
//
//   python tools/build.py && npm run pdf && python tools/build.py
//
// Serves dist/, prints each language's /capability-statement/ on A4 with Chrome and saves
// static/oluwasola-oyinloye-capability-statement[-<lang>].pdf (the second build copies them
// into dist/). Fails if any statement runs past one page.
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { fileURLToPath } from 'node:url';
import * as chromeLauncher from 'chrome-launcher';
import puppeteer from 'puppeteer-core';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DIST = path.join(ROOT, 'dist');
const SITE = JSON.parse(fs.readFileSync(path.join(ROOT, 'content', 'site.json'), 'utf8'));
const PORT = 8124;
const TYPES = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.webp': 'image/webp', '.ico': 'image/x-icon' };

const server = http.createServer((req, res) => {
  let p = decodeURIComponent(req.url.split('?')[0]);
  if (p.endsWith('/')) p += 'index.html';
  const f = path.join(DIST, p);
  if (!f.startsWith(DIST) || !fs.existsSync(f)) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { 'Content-Type': TYPES[path.extname(f)] || 'application/octet-stream' });
  res.end(fs.readFileSync(f));
});
await new Promise(r => server.listen(PORT, r));

const chrome = await chromeLauncher.launch({ chromeFlags: ['--headless=new'] });
const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${chrome.port}` });
const page = await browser.newPage();
await page.emulateMediaType('print');
let tooLong = 0;
for (const { code } of SITE.languages) {
  const local = code === SITE.default_language;
  const url = `http://localhost:${PORT}${local ? '' : '/' + code}/capability-statement/`;
  if (!fs.existsSync(path.join(DIST, local ? '' : code, 'capability-statement', 'index.html'))) continue;
  const out = path.join(ROOT, 'static', `oluwasola-oyinloye-capability-statement${local ? '' : '-' + code}.pdf`);
  await page.goto(url, { waitUntil: 'networkidle0' });
  await page.pdf({ path: out, format: 'A4', printBackground: true, preferCSSPageSize: true });
  const pages = (fs.readFileSync(out, 'latin1').match(/\/Type\s*\/Page[^s]/g) || []).length;
  if (pages > 1) tooLong++;
  console.log(`${pages > 1 ? 'TOO LONG' : 'ok      '} ${path.relative(ROOT, out)}: ${pages} page(s), ${(fs.statSync(out).size / 1024).toFixed(0)} KB`);
}
await browser.disconnect();
await chrome.kill();
server.close();
process.exit(tooLong ? 1 : 0);
