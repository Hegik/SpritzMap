import spritzBack from '$lib/assets/spritz_back.svg?raw';
import spritzDrink from '$lib/assets/spritz_drink.svg?raw';
import spritzTop from '$lib/assets/spritz_top.svg?raw';
import drinkNodata from '$lib/assets/drink_nodata.svg?raw';

// Original drink colors and their lightness ratios relative to the base (#ba0c38)
// Base HSL: hue~345, sat~90%, lightness~38%
const DRINK_COLORS = [
  { hex: '#ff6e00', ratio: 1.000 },  // base — Oberfläche
  { hex: '#f24b00', ratio: 0.949 },  // Hauptkörper
  { hex: '#e94900', ratio: 0.914 },  // Schatten links
  { hex: '#db4400', ratio: 0.859 },  // tiefer Schatten
  { hex: '#cf4000', ratio: 0.812 },  // dunkelster Rand
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

  // Apply opacity to the group
  svg = svg.replace('<g id="Getränke">', `<g id="Getränke" opacity="${opacity.toFixed(2)}">`);
  return svg;
}

function buildIcon(drinkSvg: string, label: string): string {
  const size = 'width="48" height="48" style="position:absolute;top:0;left:0;"';
  const back = spritzBack.replace('<svg ', `<svg ${size} `);
  const drink = drinkSvg.replace('<svg ', `<svg ${size} `);
  const top = spritzTop.replace('<svg ', `<svg ${size} `);

  return `
    <div style="position:relative;width:48px;height:48px;">
      ${back}
      ${drink}
      ${top}
    </div>
    ${label ? `<div class="spritz-label">${label}</div>` : ''}
  `;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function createGlassIcon(L: any, colorHex: string, colorValue: number, priceTier: string) {
  const opacity = 0.15 + (colorValue / 255) * 0.85;
  const drinkSvg = recolorDrinkSvg(colorHex, opacity);
  const html = buildIcon(drinkSvg, priceTier);

  return L.divIcon({
    html,
    className: 'spritz-marker',
    iconSize: [48, 60],
    iconAnchor: [24, 52],
    popupAnchor: [0, -54],
  });
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function createEmptyGlassIcon(L: any) {
  const drinkSvg = recolorDrinkSvg('#cccccc', 0.3);
  const html = buildIcon(drinkSvg, '');

  return L.divIcon({
    html,
    className: 'spritz-marker',
    iconSize: [48, 60],
    iconAnchor: [24, 52],
    popupAnchor: [0, -54],
  });
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function createNodataGlassIcon(L: any) {
  const size = 'width="48" height="48" style="position:absolute;top:0;left:0;"';
  const svg = drinkNodata.replace('<svg ', `<svg ${size} `);
  const html = `<div style="position:relative;width:48px;height:48px;">${svg}</div>`;

  return L.divIcon({
    html,
    className: 'spritz-marker',
    iconSize: [48, 60],
    iconAnchor: [24, 52],
    popupAnchor: [0, -54],
  });
}
