/**
 * Creates a custom Leaflet DivIcon with a wine glass SVG.
 * Accepts the Leaflet instance (L) as first arg to avoid duplicate imports.
 * - colorHex:   base color of the drink (e.g. "#FF6B35" for Aperol)
 * - colorValue: 0–255 intensity → mapped to fill opacity 0.15–1.0
 * - priceTier:  "€" | "€€" | "€€€" shown below the glass
 */
export function createEmptyGlassIcon(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  L: any,
) {
  const html = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 44" width="32" height="44">
      <path d="M6 2 L26 2 L20 20 L20 30 L22 30 L22 32 L10 32 L10 30 L12 30 L12 20 Z"
            fill="white" fill-opacity="0.85"
            stroke="#bbb" stroke-width="1.5" stroke-linejoin="round" stroke-dasharray="4,2"/>
      <text x="16" y="19" text-anchor="middle" font-size="13" fill="#bbb" font-weight="700"
            font-family="system-ui,sans-serif">+</text>
    </svg>
  `;

  return L.divIcon({
    html,
    className: 'spritz-marker',
    iconSize: [32, 50],
    iconAnchor: [16, 44],
    popupAnchor: [0, -46],
  });
}

export function createGlassIcon(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  L: any,
  colorHex: string,
  colorValue: number,
  priceTier: string
) {
  const opacity = 0.15 + (colorValue / 255) * 0.85;

  const html = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 44" width="32" height="44">
      <path d="M6 2 L26 2 L20 20 L20 30 L22 30 L22 32 L10 32 L10 30 L12 30 L12 20 Z"
            fill="${colorHex}" fill-opacity="${opacity.toFixed(2)}"
            stroke="#555" stroke-width="1.5" stroke-linejoin="round"/>
      <line x1="6" y1="2" x2="26" y2="2" stroke="white" stroke-opacity="0.4" stroke-width="1"/>
    </svg>
    <div class="spritz-label">${priceTier}</div>
  `;

  return L.divIcon({
    html,
    className: 'spritz-marker',
    iconSize: [32, 50],
    iconAnchor: [16, 44],
    popupAnchor: [0, -46],
  });
}
