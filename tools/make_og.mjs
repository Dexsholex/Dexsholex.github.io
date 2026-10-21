// Draw the social share cards (1200 x 630) for every language with headless Chrome.
//
//   npm run og
//
// A browser lays out the text, so every script works, Arabic right to left included.
// Text comes from the "og" block in content/i18n/<lang>/ui.json and the figures from
// content/site.json. Writes static/og[-<card>][-<lang>].png; commit the results.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import * as chromeLauncher from 'chrome-launcher';
import puppeteer from 'puppeteer-core';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const STATIC = path.join(ROOT, 'static');
const SITE = JSON.parse(fs.readFileSync(path.join(ROOT, 'content', 'site.json'), 'utf8'));
const read = f => JSON.parse(fs.readFileSync(f, 'utf8'));
// Same number rules as tools/build.py
const NUM = { en: [',', '.'], fr: [' ', ','], pt: [' ', ','], es: [' ', ','], ar: [',', '.'] };
const fmt = (x, lang, d = 0) => {
  const [group, dec] = NUM[lang] || NUM.en;
  const [i, f] = x.toFixed(d).split('.');
  return i.replace(/\B(?=(\d{3})+(?!\d))/g, group) + (f ? dec + f : '');
};
const dataUri = f => `data:image/webp;base64,${fs.readFileSync(path.join(STATIC, 'img', f)).toString('base64')}`;
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

const MARK = `<svg viewBox="0 0 32 32" width="56" height="56"><rect width="32" height="32" rx="8" fill="#0b6b4b"/><g fill="#fff" stroke="#fff"><circle cx="16" cy="16" r="7.5" fill="none" stroke-width="2"/><path d="M16 4.5v5.5M16 22v5.5M4.5 16H10M22 16h5.5" stroke-width="2" stroke-linecap="round"/><circle cx="16" cy="16" r="2.2" stroke="none"/></g></svg>`;
const TARGET = `<svg viewBox="0 0 400 400" width="400" height="400"><g fill="none" stroke="#5cc99a" stroke-opacity=".75" stroke-width="3"><circle cx="200" cy="200" r="140"/><circle cx="200" cy="200" r="62"/><path d="M200 5v117M200 278v117M5 200h117M278 200h117"/></g><circle cx="200" cy="200" r="9" fill="#5cc99a"/></svg>`;

function card({ lang, dir, kicker, title, sub, visual, titleSize }) {
  const host = SITE.base_url.split('//')[1].replace(/\/$/, '');
  return `<!doctype html><html lang="${lang}" dir="${dir}"><head><meta charset="utf-8"><style>
  * { margin: 0; box-sizing: border-box; }
  body { width: 1200px; height: 630px; background: #0f1613; color: #e7ede9; font-family: "Segoe UI", system-ui, sans-serif; overflow: hidden; }
  .card { position: relative; display: flex; flex-direction: column; width: 1200px; height: 630px; padding: 66px 72px 54px; }
  .grid { position: absolute; inset: 0; background-image: linear-gradient(#1e342a 1px, transparent 1px), linear-gradient(90deg, #1e342a 1px, transparent 1px);
    background-size: 60px 60px; -webkit-mask-image: radial-gradient(ellipse 75% 85% at ${dir === 'rtl' ? '15%' : '85%'} 20%, #000 0%, transparent 75%); }
  .brand { position: relative; display: flex; align-items: center; gap: 18px; font-size: 34px; font-weight: 600; }
  .row { position: relative; flex: 1; display: flex; align-items: center; justify-content: space-between; gap: 48px; min-height: 0; }
  .text { flex: 1 1 0; min-width: 0; }
  .kicker { color: #5cc99a; font: 24px/1.3 Consolas, "Cascadia Mono", monospace; letter-spacing: .04em; text-transform: uppercase; }
  :lang(ar) .kicker { font-family: "Segoe UI", system-ui, sans-serif; letter-spacing: 0; font-size: 26px; }
  h1 { margin-top: 18px; color: #fff; font-size: ${titleSize}px; font-weight: 700; line-height: 1.12; letter-spacing: -.01em; }
  :lang(ar) h1 { line-height: 1.35; letter-spacing: 0; }
  .sub { margin-top: 24px; color: #a6b3ac; font-size: 28px; }
  .visual { flex: none; position: relative; }
  .visual img { display: block; width: 430px; height: 370px; object-fit: cover; border-radius: 24px; }
  .visual.map img { width: 406px; height: 350px; object-fit: cover; object-position: 50% 0; background: #faf8f3; }
  .visual.nga img { width: 430px; height: 352px; object-fit: contain; padding: 12px; background: #faf8f3; }
  .chip { position: absolute; top: 20px; inset-inline: 20px; padding: 14px 18px; border-radius: 18px; background: rgba(13, 23, 20, .86);
    color: #fff; font-size: 26px; font-weight: 600; text-align: center; }
  .coords { margin-top: -10px; color: #a6b3ac; font: 22px Consolas, monospace; text-align: center; direction: ltr; }
  .host { position: relative; color: #a6b3ac; font: 24px Consolas, monospace; direction: ltr; text-align: start; }
  [dir=rtl] .host { text-align: end; }
  .bar { position: absolute; inset: auto 0 0 0; height: 8px; background: #0b6b4b; }
  </style></head><body><div class="card"><div class="grid"></div>
  <div class="brand">${MARK}<span>${esc(SITE.name)}</span></div>
  <div class="row"><div class="text"><p class="kicker">${esc(kicker)}</p><h1>${esc(title)}</h1><p class="sub">${esc(sub)}</p></div>${visual}</div>
  <p class="host">${esc(host)}</p><div class="bar"></div></div></body></html>`;
}

const palm = SITE.projects.oil_palm;
const chrome = await chromeLauncher.launch({ chromeFlags: ['--headless=new'] });
const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${chrome.port}` });
const page = await browser.newPage();
await page.setViewport({ width: 1200, height: 630 });
for (const { code: lang, dir } of SITE.languages) {
  const ui = path.join(ROOT, 'content', 'i18n', lang, 'ui.json');
  if (!fs.existsSync(ui)) continue;
  const t = read(ui);
  const suffix = lang === SITE.default_language ? '' : `-${lang}`;
  const cards = {
    [`og${suffix}`]: { kicker: t.og.home_kicker, title: t.site.flagship, sub: t.og.home_sub, titleSize: 68,
      visual: `<div class="visual">${TARGET}<p class="coords">6.455° N   3.384° E</p></div>` },
    [`og-oil-palm${suffix}`]: { kicker: t.og.palm_kicker, title: t.og.palm_title, sub: t.og.palm_sub, titleSize: 58,
      visual: `<div class="visual"><img src="${dataUri('palm-drone-pad-800.webp')}" alt=""><p class="chip">${esc(
        t.og.palm_chip.replace('{palms}', fmt(palm.palms, lang)).replace('{ha}', fmt(palm.hectares, lang, 1)))}</p></div>` },
    [`og-geoaid${suffix}`]: { kicker: t.og.geoaid_kicker, title: t.og.geoaid_title, sub: t.og.geoaid_sub, titleSize: 62,
      visual: `<div class="visual map"><img src="${dataUri('geoaid-flood-800.webp')}" alt=""></div>` },
    [`og-where-to-build${suffix}`]: { kicker: t.og.wtbn_kicker, title: t.og.wtbn_title, sub: t.og.wtbn_sub, titleSize: 58,
      visual: `<div class="visual nga"><img src="${dataUri('wtbn-map-800.webp')}" alt=""></div>` },
  };
  for (const [name, c] of Object.entries(cards)) {
    await page.setContent(card({ lang, dir, ...c }), { waitUntil: 'load' });
    const out = path.join(STATIC, `${name}.png`);
    await page.screenshot({ path: out, type: 'png' });
    console.log(`${name}.png ${(fs.statSync(out).size / 1024).toFixed(0)} KB`);
  }
}
await browser.disconnect();
await chrome.kill();
