// Kleine Strich-Symbole für die Glasformen (Formular-Chips und Karten-Popup).
// Farbe über currentColor, Größe über den Parameter.
import type { GlassType } from '$lib/types/photo';

const SHAPES: Record<GlassType, string> = {
  // Weinglas: Kelch mit Füllung, Stiel, Fuß
  wine:
    '<path d="M7.8 9.5h8.4a4.2 4.2 0 0 1-8.4 0z" fill="currentColor" fill-opacity=".3" stroke="none"/>' +
    '<path d="M7 3h10l.2 5.5a5.2 5.2 0 0 1-10.4 0z"/><path d="M12 14v6"/><path d="M8.5 21h7"/>',
  // Wasserglas: leicht konischer Becher mit Füllung
  tumbler:
    '<path d="M7.3 10h9.4l-.9 10H8.2z" fill="currentColor" fill-opacity=".3" stroke="none"/>' +
    '<path d="M6.5 3h11l-1.6 18H8.1z"/>',
  // Sonstiges: Becher mit Fragezeichen
  other:
    '<path d="M6.5 3h11l-1.6 18H8.1z"/>' +
    '<path d="M10 9.5a2 2 0 1 1 3 1.7c-.7.4-1 .9-1 1.6"/><path d="M12 16v.01" stroke-width="2.2"/>',
};

export function glassIconSvg(type: GlassType, size = 20): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${SHAPES[type]}</svg>`;
}
