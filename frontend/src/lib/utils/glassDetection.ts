// KI-Stufe 2: Glasform per vortrainiertem COCO-SSD (Klassen "wine glass" / "cup").
// Läuft komplett im Browser. Modell (uint8-quantisiert, ~4,6 MB) liegt selbst gehostet unter /models/coco-ssd
// und wird erst beim ersten Foto per dynamischem Import geladen.
import type { GlassType } from '$lib/types/photo';
import type { Region } from '$lib/utils/colorAnalysis';

export interface GlassDetection {
  glassType: GlassType;
  score: number;
  region: Region;
}

const CLASS_MAP: Record<string, GlassType> = {
  'wine glass': 'wine',
  cup: 'tumbler',
};
const MIN_SCORE = 0.3;

type Detector = { detect: (img: ImageBitmap | HTMLCanvasElement, maxBoxes?: number, minScore?: number) => Promise<{ bbox: [number, number, number, number]; class: string; score: number }[]> };
let detectorPromise: Promise<Detector> | null = null;

function loadDetector(): Promise<Detector> {
  detectorPromise ??= (async () => {
    const [tf, cocoSsd] = await Promise.all([import('@tensorflow/tfjs'), import('@tensorflow-models/coco-ssd')]);
    await tf.ready();
    return cocoSsd.load({ base: 'lite_mobilenet_v2', modelUrl: '/models/coco-ssd/model.json' }) as Promise<Detector>;
  })().catch((e) => {
    detectorPromise = null; // bei Netzwerkfehler später erneut versuchen
    throw e;
  });
  return detectorPromise;
}

/** true, sobald das Modell geladen ist (dann entfällt der Download beim nächsten Foto). */
let detectorReady = false;

/**
 * Findet das wahrscheinlichste Glas im Bild. null, wenn kein Glas erkannt wurde.
 * onStage meldet den Wechsel vom Modell-Laden zur eigentlichen Erkennung (für die Fortschrittsanzeige).
 */
export async function detectGlass(
  bitmap: ImageBitmap,
  onStage?: (stage: 'model' | 'detect') => void,
): Promise<GlassDetection | null> {
  if (!detectorReady) onStage?.('model');
  const detector = await loadDetector();
  detectorReady = true;
  onStage?.('detect');
  // coco-ssd erwartet ein Pixel-Element; ImageBitmap über Canvas übergeben
  const canvas = document.createElement('canvas');
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  canvas.getContext('2d')!.drawImage(bitmap, 0, 0);

  const predictions = await detector.detect(canvas, 10, MIN_SCORE);
  const best = predictions
    .filter((p) => p.class in CLASS_MAP)
    .sort((a, b) => b.score - a.score)[0];
  if (!best) return null;

  const [x, y, width, height] = best.bbox;
  const glassType = CLASS_MAP[best.class];
  // Messbereich = wo das Getränk typischerweise steht:
  // Weinglas → Kelch (oberes Mittelteil, darunter Stiel); Wasserglas → unterer/mittlerer Teil (oben Eis/Luft)
  const [top, bottom] = glassType === 'wine' ? [0.15, 0.55] : [0.3, 0.9];
  return {
    glassType,
    score: best.score,
    region: { x: x + width * 0.2, y: y + height * top, width: width * 0.6, height: height * (bottom - top) },
  };
}
