import spritzBack from '$lib/assets/spritz_back.svg?raw';
import spritzDrink from '$lib/assets/spritz_drink.svg?raw';
import spritzTop from '$lib/assets/spritz_top.svg?raw';
import spritzNodata from '$lib/assets/spritz_nodata.svg?raw';

// Original drink colors and their lightness ratios relative to the base (#ba0c38)
const DRINK_COLORS = [
  { hex: '#ff6e00', ratio: 1.000 },
  { hex: '#f24b00', ratio: 0.949 },
  { hex: '#e94900', ratio: 0.914 },
  { hex: '#db4400', ratio: 0.859 },
  { hex: '#cf4000', ratio: 0.812 },
];

function hexToHsl(hex: string): [number, number, number] {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h = 0, s = 0;
  const l = (max + min) / 2;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break;
      case g: h = ((b - r) / d + 2) / 6; break;
      case b: h = ((r - g) / d + 4) / 6; break;
    }
  }
  return [h * 360, s * 100, l * 100];
}

function hslToHex(h: number, s: number, l: number): string {
  s /= 100; l /= 100;
  const k = (n: number) => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = (n: number) => Math.round(255 * (l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)))));
  return `#${[f(0), f(8), f(4)].map(v => v.toString(16).padStart(2, '0')).join('')}`;
}

function recolorDrinkSvg(colorHex: string, opacity: number): string {
  const [h, s, lBase] = hexToHsl(colorHex);
  let svg = spritzDrink;
  for (const { hex, ratio } of DRINK_COLORS) {
    const newL = Math.min(lBase * ratio * (1 / DRINK_COLORS[0].ratio), 95);
    const newHex = hslToHex(h, s, newL);
    svg = svg.replaceAll(hex, newHex);
  }
  svg = svg.replace('<g id="Getränke">', `<g id="Getränke" opacity="${opacity.toFixed(2)}">`);
  return svg;
}

function innerSvg(svg: string): string {
  return svg.match(/<svg[^>]*>([\s\S]*)<\/svg>/)?.[1] ?? '';
}

function buildCompositeSvg(drinkSvg: string, sizePx: number): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${sizePx}" height="${sizePx}" viewBox="0 0 410.2 405.2">
    ${innerSvg(spritzBack)}
    ${innerSvg(drinkSvg)}
    ${innerSvg(spritzTop)}
  </svg>`;
}

function svgToDataUrl(svgString: string, sizePx: number): Promise<string> {
  return new Promise((resolve, reject) => {
    const blob = new Blob([svgString], { type: 'image/svg+xml' });
    const url = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = sizePx;
      canvas.height = sizePx;
      canvas.getContext('2d')!.drawImage(img, 0, 0, sizePx, sizePx);
      URL.revokeObjectURL(url);
      resolve(canvas.toDataURL('image/png'));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('SVG rasterization failed')); };
    img.src = url;
  });
}

const dataUrlCache = new Map<string, Promise<string>>();

function getDataUrl(key: string, svgString: string, sizePx: number): Promise<string> {
  if (!dataUrlCache.has(key)) {
    dataUrlCache.set(key, svgToDataUrl(svgString, sizePx));
  }
  return dataUrlCache.get(key)!;
}

// Returns a PNG data URL for use with MapLibre addImage()
export async function getGlassIconDataUrl(colorHex: string, colorValue: number): Promise<string> {
  const quantized = Math.round(colorValue / 5) * 5;
  const key = `${colorHex}-${quantized}`;
  const opacity = 0.15 + (colorValue / 255) * 0.85;
  const drinkSvg = recolorDrinkSvg(colorHex, opacity);
  return getDataUrl(key, buildCompositeSvg(drinkSvg, 48), 48);
}

export async function getEmptyGlassDataUrl(): Promise<string> {
  const drinkSvg = recolorDrinkSvg('#cccccc', 0.3);
  return getDataUrl('__empty__', buildCompositeSvg(drinkSvg, 48), 48);
}

export async function getNodataGlassDataUrl(): Promise<string> {
  const svgWithSize = spritzNodata.replace('<svg ', '<svg width="48" height="48" ');
  return getDataUrl('__nodata__', svgWithSize, 48);
}

// Same "no price yet" glass (blue question mark) as the map marker — synchronous HTML for the legend
// (as <img> so the SVG's own <style> block with .st* classes stays isolated from the page)
export function buildNodataIconHtml(sizePx: number): string {
  const src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(spritzNodata)}`;
  return `<img src="${src}" width="${sizePx}" height="${sizePx}" alt="" />`;
}

// Glass without drink layer + red cross — for "unavailable" entries
export function buildUnavailableIconHtml(sizePx: number): string {
  const size = `width="${sizePx}" height="${sizePx}" style="position:absolute;top:0;left:0;"`;
  const back = spritzBack.replace('<svg ', `<svg ${size} `);
  const top = spritzTop.replace('<svg ', `<svg ${size} `);
  const sw = Math.max(3, Math.round(sizePx * 0.06));
  const pad = Math.round(sizePx * 0.13);
  const cross = `<svg width="${sizePx}" height="${sizePx}" viewBox="0 0 ${sizePx} ${sizePx}" style="position:absolute;top:0;left:0;">
    <line x1="${pad}" y1="${pad}" x2="${sizePx - pad}" y2="${sizePx - pad}" stroke="#d03030" stroke-width="${sw}" stroke-linecap="round" opacity="0.65"/>
    <line x1="${sizePx - pad}" y1="${pad}" x2="${pad}" y2="${sizePx - pad}" stroke="#d03030" stroke-width="${sw}" stroke-linecap="round" opacity="0.65"/>
  </svg>`;
  return `<div style="position:relative;width:${sizePx}px;height:${sizePx}px;">${back}${top}${cross}</div>`;
}

// Synchronous HTML for popups (not performance-critical)
export function buildIconHtml(colorHex: string, colorValue: number, sizePx: number): string {
  const opacity = 0.15 + (colorValue / 255) * 0.85;
  const drinkSvg = recolorDrinkSvg(colorHex, opacity);
  const size = `width="${sizePx}" height="${sizePx}" style="position:absolute;top:0;left:0;"`;
  const back = spritzBack.replace('<svg ', `<svg ${size} `);
  const drink = drinkSvg.replace('<svg ', `<svg ${size} `);
  const top = spritzTop.replace('<svg ', `<svg ${size} `);
  return `<div style="position:relative;width:${sizePx}px;height:${sizePx}px;">${back}${drink}${top}</div>`;
}
