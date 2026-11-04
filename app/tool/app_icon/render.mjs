// Draws every launcher icon of the app from one source, icon.svg (see DESIGN.md, "App icon").
//
//   NODE_PATH="$(npm root -g)" node tool/app_icon/render.mjs      (from app/)
//
// Needs Node 22.2 or later (for zlib.crc32) and Playwright with its Chromium
// (`npm install -g playwright`, then `npx playwright install chromium`). It overwrites the PNGs
// below and nothing else.
//
// icon.svg is drawn on Android's 108 x 108 adaptive-icon grid and holds three layers:
//   #bg    the full-bleed, opaque background
//   #fg    a subject on transparency, for the launcher's parallax (it may be empty)
//   #mono  a one-colour silhouette in currentColor, for Android 13 themed icons
// What matters stays inside the 66-unit safe circle. Pictures that icon.svg links to by a plain
// file name, such as forest-gate.jpg next to it, are inlined before drawing.
// Each platform gets a square cut from the middle of the grid: Android's adaptive layers keep the
// whole grid (the launcher masks the middle 72), iPhone and the web's own icons a side of 80, and
// the web's maskable icons a side of 82.5, so the safe circle is exactly their 80% safe zone.

import { createRequire } from 'node:module';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import zlib from 'node:zlib';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const HERE = dirname(fileURLToPath(import.meta.url));
const APP = join(HERE, '..', '..');
const GRID = 108;
const CENTER = GRID / 2;
const INK = [0x0b, 0x0d, 0x12]; // Palette ink, behind anything that must be opaque
const ANDROID_RES = 'android/app/src/main/res';
const DENSITIES = { mdpi: 1, hdpi: 1.5, xhdpi: 2, xxhdpi: 3, xxxhdpi: 4 };
const IOS_SET = 'ios/Runner/Assets.xcassets/AppIcon.appiconset';

// One picture: its path from app/, its side in pixels, which layers it shows, the side of the
// centred square of the grid it shows (`crop`), optionally rounded corners (`corner`, a share of
// the side) and an empty margin (`pad`, a share of the picture), and whether it keeps its alpha
// channel: App Store icons and full-bleed ones don't.
const FULL = ['bg', 'fg'];
const ICON = 80;
const MASKABLE = 66 / 0.8;

function outputs() {
  const list = [];
  for (const [density, scale] of Object.entries(DENSITIES)) {
    const dir = `${ANDROID_RES}/mipmap-${density}`;
    const layer = { size: GRID * scale, crop: GRID };
    list.push(
      // Android before 8, which has no adaptive icons.
      {
        path: `${dir}/ic_launcher.png`,
        size: 48 * scale,
        layers: FULL,
        crop: ICON,
        corner: 0.2,
        pad: 1 / 48,
      },
      { path: `${dir}/ic_launcher_background.png`, layers: ['bg'], alpha: false, ...layer },
      { path: `${dir}/ic_launcher_foreground.png`, layers: ['fg'], ...layer },
      { path: `${dir}/ic_launcher_monochrome.png`, layers: ['mono'], ...layer },
    );
  }
  const contents = JSON.parse(readFileSync(join(APP, IOS_SET, 'Contents.json'), 'utf8'));
  const filenames = new Set();
  for (const { filename, size, scale } of contents.images) {
    if (filenames.has(filename)) continue; // iPhone and iPad share some files
    filenames.add(filename);
    const side = Math.round(Number(size.split('x')[0]) * Number(scale.replace('x', '')));
    list.push({ path: `${IOS_SET}/${filename}`, size: side, layers: FULL, crop: ICON, alpha: false });
  }
  const web = { layers: FULL, crop: ICON };
  const maskable = { layers: FULL, crop: MASKABLE, alpha: false };
  list.push(
    { path: 'web/favicon.png', size: 32, corner: 0.2, ...web },
    { path: 'web/icons/Icon-192.png', size: 192, corner: 0.2237, ...web },
    { path: 'web/icons/Icon-512.png', size: 512, corner: 0.2237, ...web },
    { path: 'web/icons/Icon-maskable-192.png', size: 192, ...maskable },
    { path: 'web/icons/Icon-maskable-512.png', size: 512, ...maskable },
    // iOS Safari's home-screen icon: square and opaque, since iOS rounds it and blackens alpha.
    { path: 'web/icons/apple-touch-icon.png', size: 180, alpha: false, ...web },
  );
  return list;
}

function compose(inner, { layers, crop, corner, pad = 0, size }) {
  const x0 = CENTER - crop / 2;
  const margin = (crop * pad) / (1 - 2 * pad);
  const view = [x0 - margin, x0 - margin, crop + 2 * margin, crop + 2 * margin].join(' ');
  const shown = layers.map((layer) => `#${layer}{display:inline}`).join('');
  const clip = corner
    ? `<clipPath id="icon-corners"><rect x="${x0}" y="${x0}" width="${crop}" height="${crop}" rx="${crop * corner}"/></clipPath>`
    : '';
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="${view}" color="#fff">
<style>#bg,#fg,#mono{display:none}${shown}</style>${clip}
<g${corner ? ' clip-path="url(#icon-corners)"' : ''}>${inner}</g></svg>`;
}

// Draws the SVG at four times the size and halves it down, which keeps thin lines smooth.
async function rasterize(page, svg, size) {
  const base64 = await page.evaluate(
    async ({ source, size }) => {
      const image = new Image();
      image.src = 'data:image/svg+xml;base64,' + source;
      await image.decode();
      let canvas = document.createElement('canvas');
      let side = Math.max(size * 4, 256);
      canvas.width = canvas.height = side;
      canvas.getContext('2d').drawImage(image, 0, 0, side, side);
      while (side > size) {
        side = Math.max(size, Math.floor(side / 2));
        const next = document.createElement('canvas');
        next.width = next.height = side;
        const context = next.getContext('2d');
        context.imageSmoothingQuality = 'high';
        context.drawImage(canvas, 0, 0, side, side);
        canvas = next;
      }
      const data = canvas.getContext('2d').getImageData(0, 0, size, size).data;
      let text = '';
      for (let i = 0; i < data.length; i += 0x8000) {
        text += String.fromCharCode.apply(null, data.subarray(i, i + 0x8000));
      }
      return btoa(text);
    },
    { source: Buffer.from(svg).toString('base64'), size },
  );
  return Buffer.from(base64, 'base64');
}

// A PNG from straight RGBA: RGBA, or RGB flattened onto ink. Each row takes the filter that
// leaves the smallest sum, as most encoders do.
function encodePng(rgba, size, alpha) {
  const channels = alpha ? 4 : 3;
  const stride = size * channels;
  const rows = [];
  for (let y = 0; y < size; y++) {
    const row = Buffer.alloc(stride);
    for (let x = 0; x < size; x++) {
      const i = (y * size + x) * 4;
      if (alpha) {
        rgba.copy(row, x * 4, i, i + 4);
        continue;
      }
      const a = rgba[i + 3] / 255;
      for (let k = 0; k < 3; k++) row[x * 3 + k] = Math.round(rgba[i + k] * a + INK[k] * (1 - a));
    }
    rows.push(row);
  }
  const filtered = [];
  for (let y = 0; y < size; y++) {
    const current = rows[y];
    const previous = y ? rows[y - 1] : Buffer.alloc(stride);
    let best;
    let bestSum = Infinity;
    for (let filter = 0; filter < 5; filter++) {
      const line = Buffer.alloc(stride + 1);
      line[0] = filter;
      let sum = 0;
      for (let x = 0; x < stride; x++) {
        const left = x >= channels ? current[x - channels] : 0;
        const up = previous[x];
        const upLeft = x >= channels ? previous[x - channels] : 0;
        const predicted = [0, left, up, (left + up) >> 1, paeth(left, up, upLeft)][filter];
        const value = (current[x] - predicted) & 0xff;
        line[x + 1] = value;
        sum += value < 128 ? value : 256 - value;
      }
      if (sum < bestSum) [best, bestSum] = [line, sum];
    }
    filtered.push(best);
  }
  const header = Buffer.alloc(13);
  header.writeUInt32BE(size, 0);
  header.writeUInt32BE(size, 4);
  header[8] = 8; // bits per channel
  header[9] = alpha ? 6 : 2; // RGBA or RGB
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', header),
    chunk('IDAT', zlib.deflateSync(Buffer.concat(filtered), { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

function paeth(a, b, c) {
  const p = a + b - c;
  const [pa, pb, pc] = [Math.abs(p - a), Math.abs(p - b), Math.abs(p - c)];
  return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
}

function chunk(type, data) {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(zlib.crc32(body) >>> 0);
  return Buffer.concat([length, body, crc]);
}

const source = readFileSync(join(HERE, 'icon.svg'), 'utf8');
const inner = source
  .replace(/^[\s\S]*?<svg[^>]*>/, '')
  .replace(/<\/svg>\s*$/, '')
  .replace(/href="([\w.-]+)\.(png|jpe?g)"/g, (_, name, extension) => {
    const data = readFileSync(join(HERE, `${name}.${extension}`)).toString('base64');
    const type = extension === 'png' ? 'png' : 'jpeg';
    return `href="data:image/${type};base64,${data}"`;
  });
// A picture drawn from an SVG can't load files, so any other link would leave a silent hole.
const unloaded = inner.match(/<image\b[^>]*?\bhref="(?!data:)([^"]*)"/);
if (unloaded) throw new Error(`icon.svg links to ${unloaded[1]}, which is not a PNG or JPEG next to it`);
const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  // Some outputs are the same picture under another name (a 40 px iPhone icon is 20 pt at 2x and
  // 40 pt at 1x), so each picture is drawn once.
  const drawn = new Map();
  for (const output of outputs()) {
    const { path, size, alpha = true } = output;
    const key = JSON.stringify({ ...output, path: undefined });
    if (!drawn.has(key)) {
      drawn.set(key, encodePng(await rasterize(page, compose(inner, output), size), size, alpha));
    }
    mkdirSync(dirname(join(APP, path)), { recursive: true });
    writeFileSync(join(APP, path), drawn.get(key));
    console.log(`${path} (${size} px)`);
  }
} finally {
  await browser.close();
}
