// KI-Stufe 1: Mischverhältnis (color_value 0–255) aus der Drinkfarbe im Foto schätzen.
// Reine Pixelstatistik per Canvas, kein ML-Modell. Ergebnis ist nur ein Vorschlag für den Schieberegler.

export interface Region {
  x: number;
  y: number;
  width: number;
  height: number;
}

const SAMPLE_PX = 64;
const HUE_TOLERANCE = 28; // Grad um den Farbton der Getränkesorte
const MIN_MATCH_RATIO = 0.03; // unter 3 % passender Pixel → kein Vorschlag

// Kalibrierung (erste Runde mit Referenzfotos, 2026-09): Spritz-Pixel sind fast immer stark gesättigt
// (Median 0.86–0.96); ein blasser Spritz zeigt sich v. a. durch höhere Helligkeit (Median ~0.35 statt ~0.28).
// Daher wird die Helligkeit stärker gewichtet. Mit weiteren echten Fotos (ai_color_value vs. color_value) nachjustieren.
const SAT_RANGE: [number, number] = [0.7, 1.0];
const LIGHT_RANGE: [number, number] = [0.22, 0.5];
const LIGHT_WEIGHT = 0.7;

function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h: number;
  if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) * 60;
  else if (max === g) h = ((b - r) / d + 2) * 60;
  else h = ((r - g) / d + 4) * 60;
  return [h, s, l];
}

function hexToHue(hex: string): number {
  const n = parseInt(hex.slice(1), 16);
  return rgbToHsl((n >> 16) & 255, (n >> 8) & 255, n & 255)[0];
}

function hueDistance(a: number, b: number): number {
  const d = Math.abs(a - b) % 360;
  return d > 180 ? 360 - d : d;
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)];
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

/** Standard-Messbereich, wenn keine Glaserkennung vorliegt: mittleres Bilddrittel. */
export function centerRegion(width: number, height: number): Region {
  return { x: width / 3, y: height / 3, width: width / 3, height: height / 3 };
}

/**
 * Schätzt color_value (0–255) für die Getränkefarbe drinkHex im Bereich region.
 * Gibt null zurück, wenn zu wenige passende Pixel gefunden werden.
 */
export function estimateColorValue(
  bitmap: ImageBitmap,
  drinkHex: string,
  region: Region = centerRegion(bitmap.width, bitmap.height),
): number | null {
  // Weißabgleich anhand annähernd neutraler Pixel (Tischdecke, Glas, Wand) gegen Kerzen-/Abendlicht-Farbstich.
  // Klassisches Grau-Welt würde bei formatfüllendem Drink das Orange selbst "wegkorrigieren".
  const whole = document.createElement('canvas');
  whole.width = whole.height = SAMPLE_PX;
  const wctx = whole.getContext('2d', { willReadFrequently: true })!;
  wctx.drawImage(bitmap, 0, 0, SAMPLE_PX, SAMPLE_PX);
  const wd = wctx.getImageData(0, 0, SAMPLE_PX, SAMPLE_PX).data;
  let sr = 0, sg = 0, sb = 0, neutral = 0;
  for (let i = 0; i < wd.length; i += 4) {
    const [, s, l] = rgbToHsl(wd[i], wd[i + 1], wd[i + 2]);
    if (s > 0.25 || l < 0.2 || l > 0.95) continue;
    sr += wd[i]; sg += wd[i + 1]; sb += wd[i + 2]; neutral++;
  }
  let [gr, gg, gb] = [1, 1, 1];
  if (neutral >= SAMPLE_PX * SAMPLE_PX * 0.1) {
    const gray = (sr + sg + sb) / 3;
    // Verstärkung begrenzen, damit Fehleinschätzungen nicht eskalieren
    const gain = (c: number) => Math.min(1.3, Math.max(0.77, gray / Math.max(c, 1)));
    [gr, gg, gb] = [gain(sr), gain(sg), gain(sb)];
  }

  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = SAMPLE_PX;
  const ctx = canvas.getContext('2d', { willReadFrequently: true })!;
  ctx.drawImage(bitmap, region.x, region.y, region.width, region.height, 0, 0, SAMPLE_PX, SAMPLE_PX);
  const data = ctx.getImageData(0, 0, SAMPLE_PX, SAMPLE_PX).data;

  const targetHue = hexToHue(drinkHex);
  const sats: number[] = [];
  const lights: number[] = [];
  for (let i = 0; i < data.length; i += 4) {
    const [h, s, l] = rgbToHsl(
      Math.min(255, data[i] * gr),
      Math.min(255, data[i + 1] * gg),
      Math.min(255, data[i + 2] * gb),
    );
    if (s < 0.2 || l < 0.12 || l > 0.92) continue; // Glanzlichter, Schatten, Grautöne
    if (hueDistance(h, targetHue) > HUE_TOLERANCE) continue;
    sats.push(s);
    lights.push(l);
  }

  if (sats.length < SAMPLE_PX * SAMPLE_PX * MIN_MATCH_RATIO) return null;

  const satScore = clamp01((median(sats) - SAT_RANGE[0]) / (SAT_RANGE[1] - SAT_RANGE[0]));
  const darkScore = clamp01((LIGHT_RANGE[1] - median(lights)) / (LIGHT_RANGE[1] - LIGHT_RANGE[0]));
  return Math.round((LIGHT_WEIGHT * darkScore + (1 - LIGHT_WEIGHT) * satScore) * 255);
}
