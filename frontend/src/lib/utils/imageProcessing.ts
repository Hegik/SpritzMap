// Bildverarbeitung komplett im Browser: skalieren, als WebP kodieren, EXIF (inkl. GPS) verwerfen.
// Der Server speichert die Dateien nur noch ab.

const FULL_MAX_PX = 1600;
const THUMB_MAX_PX = 400;
const FULL_QUALITY = 0.8;
const THUMB_QUALITY = 0.7;

export interface CompressedImage {
  full: Blob;
  thumb: Blob;
  /** Verkleinerte Kopie für die Bildanalyse im Client */
  bitmap: ImageBitmap;
}

function drawScaled(src: ImageBitmap, maxPx: number): HTMLCanvasElement {
  const scale = Math.min(1, maxPx / Math.max(src.width, src.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(src.width * scale);
  canvas.height = Math.round(src.height * scale);
  const ctx = canvas.getContext('2d')!;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(src, 0, 0, canvas.width, canvas.height);
  return canvas;
}

function toBlob(canvas: HTMLCanvasElement, quality: number): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((webp) => {
      // Ältere Safari-Versionen können kein WebP kodieren und liefern stattdessen PNG → JPEG-Fallback
      if (webp && webp.type === 'image/webp') return resolve(webp);
      canvas.toBlob((jpeg) => (jpeg ? resolve(jpeg) : reject(new Error('encode failed'))), 'image/jpeg', quality);
    }, 'image/webp', quality);
  });
}

export async function compressImage(file: File): Promise<CompressedImage> {
  // imageOrientation: 'from-image' dreht Handyfotos anhand der EXIF-Orientierung korrekt
  const source = await createImageBitmap(file, { imageOrientation: 'from-image' });
  try {
    const fullCanvas = drawScaled(source, FULL_MAX_PX);
    const thumbCanvas = drawScaled(source, THUMB_MAX_PX);
    const [full, thumb, bitmap] = await Promise.all([
      toBlob(fullCanvas, FULL_QUALITY),
      toBlob(thumbCanvas, THUMB_QUALITY),
      createImageBitmap(drawScaled(source, 640)),
    ]);
    return { full, thumb, bitmap };
  } finally {
    source.close();
  }
}

export function fileExtension(blob: Blob): string {
  return blob.type === 'image/webp' ? 'webp' : 'jpg';
}
