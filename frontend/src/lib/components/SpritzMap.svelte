<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { drinks, selectedDrinkId, selectedPriceTier } from '$lib/stores/map';
  import { getGlassIconDataUrl, getEmptyGlassDataUrl, getNodataGlassDataUrl, buildIconHtml } from '$lib/utils/markerIcon';
  import PriceSubmitModal from '$lib/components/PriceSubmitModal.svelte';
  import { isLoggedIn } from '$lib/stores/auth';
  import { t } from '$lib/i18n';
  import type { Map, Popup, GeoJSONSource } from 'maplibre-gl';

  let mapEl: HTMLDivElement;
  let map: Map;
  let popup: Popup;

  export function reloadMarkers() {
    loadMarkers($selectedDrinkId, $selectedPriceTier);
  }

  let submitOpen = $state(false);
  let submitLocationId = $state<number | null>(null);
  let submitLocationName = $state('');
  let submitIsEmpty = $state(false);

  const GEOSERVER_URL = import.meta.env.VITE_GEOSERVER_URL ?? 'http://localhost:8080/geoserver';
  const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

  function getDrinkColor(drinkId: number | null): string {
    if (!drinkId) return '#e8500a';
    return $drinks.find((d) => d.id === drinkId)?.color_hex ?? '#e8500a';
  }

  function updateBasemapTint(drinkId: number | null) {
    if (!map?.getLayer('drink-tint')) return;
    map.setPaintProperty('drink-tint', 'background-color', getDrinkColor(drinkId));
  }

  // Image name registry — track which icon keys are already added to the map
  const registeredImages = new Set<string>();

  async function ensureImage(key: string, dataUrl: string) {
    if (registeredImages.has(key)) return;
    await new Promise<void>((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        if (!map.hasImage(key)) map.addImage(key, img);
        registeredImages.add(key);
        resolve();
      };
      img.onerror = reject;
      img.src = dataUrl;
    });
  }

  async function loadMarkers(drinkId: number | null, priceTier: string | null) {
    if (!map) return;

    const params = new URLSearchParams();
    if (drinkId) params.set('drink_id', String(drinkId));
    if (priceTier) params.set('price_tier', priceTier);

    const [res, nodataRes, emptyRes] = await Promise.all([
      fetch(`${API_URL}/locations/geojson?${params}`),
      drinkId ? fetch(`${API_URL}/locations/geojson/nodata?drink_id=${drinkId}`) : null,
      drinkId ? null : fetch(`${API_URL}/locations/geojson/empty`),
    ]);

    if (!res.ok) return;
    const geojson: GeoJSON.FeatureCollection = await res.json();

    // Collect all unique icon keys needed and preload them in parallel
    const iconJobs: Array<{ key: string; promise: Promise<string> }> = [];
    const seenKeys = new Set<string>();

    for (const f of geojson.features) {
      const p = (f as GeoJSON.Feature<GeoJSON.Point>).properties!;
      const quantized = Math.round(p.avg_color_value / 5) * 5;
      const key = `glass-${p.drink_color_hex}-${quantized}`;
      if (!seenKeys.has(key)) {
        seenKeys.add(key);
        iconJobs.push({ key, promise: getGlassIconDataUrl(p.drink_color_hex, p.avg_color_value) });
      }
    }

    if (nodataRes?.ok || !drinkId) {
      if (!seenKeys.has('__nodata__')) {
        seenKeys.add('__nodata__');
        iconJobs.push({ key: '__nodata__', promise: getNodataGlassDataUrl() });
      }
    }
    if (emptyRes || !drinkId) {
      if (!seenKeys.has('__empty__')) {
        seenKeys.add('__empty__');
        iconJobs.push({ key: '__empty__', promise: getEmptyGlassDataUrl() });
      }
    }

    // Resolve all data URLs then register images
    const resolved = await Promise.all(iconJobs.map(async j => ({ key: j.key, url: await j.promise })));
    await Promise.all(resolved.map(r => ensureImage(r.key, r.url)));

    // Build GeoJSON features with icon key + popup data
    const features: GeoJSON.Feature[] = [];

    for (const f of geojson.features) {
      const p = (f as GeoJSON.Feature<GeoJSON.Point>).properties!;
      const quantized = Math.round(p.avg_color_value / 5) * 5;
      features.push({
        type: 'Feature',
        geometry: (f as GeoJSON.Feature<GeoJSON.Point>).geometry,
        properties: {
          ...p,
          icon: `glass-${p.drink_color_hex}-${quantized}`,
          priceTier: p.price_tier,
          popup_type: 'priced',
        },
      });
    }

    if (nodataRes?.ok) {
      const nodataGeojson: GeoJSON.FeatureCollection = await nodataRes.json();
      for (const f of nodataGeojson.features) {
        features.push({
          type: 'Feature',
          geometry: (f as GeoJSON.Feature<GeoJSON.Point>).geometry,
          properties: {
            ...(f as GeoJSON.Feature<GeoJSON.Point>).properties,
            icon: '__nodata__',
            popup_type: 'nodata',
          },
        });
      }
    }

    if (emptyRes?.ok) {
      const emptyGeojson: GeoJSON.FeatureCollection = await emptyRes.json();
      for (const f of emptyGeojson.features) {
        features.push({
          type: 'Feature',
          geometry: (f as GeoJSON.Feature<GeoJSON.Point>).geometry,
          properties: {
            ...(f as GeoJSON.Feature<GeoJSON.Point>).properties,
            icon: '__empty__',
            popup_type: 'empty',
          },
        });
      }
    }

    const source = map.getSource('markers') as GeoJSONSource | undefined;
    const fc: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features };
    if (source) {
      source.setData(fc);
    } else {
      map.addSource('markers', { type: 'geojson', data: fc });

      const sharedLayout = {
        'icon-image': ['get', 'icon'] as any,
        'icon-size': 1,
        'icon-allow-overlap': true,
        'icon-anchor': 'bottom' as const,
        'text-field': ['get', 'priceTier'] as any,
        'text-size': 11,
        'text-anchor': 'top' as const,
        'text-offset': [0, 0.1] as any,
        'text-allow-overlap': true,
        'text-optional': true,
      };
      const sharedPaint = {
        'text-color': '#333333',
        'text-halo-color': '#ffffff',
        'text-halo-width': 1.5,
      };

      // Priced locations — visible one zoom level earlier
      map.addLayer({
        id: 'markers-priced',
        type: 'symbol',
        source: 'markers',
        minzoom: 13,
        filter: ['==', ['get', 'popup_type'], 'priced'],
        layout: sharedLayout,
        paint: sharedPaint,
      });

      // Nodata / empty locations — visible at same level as before
      map.addLayer({
        id: 'markers-nodata',
        type: 'symbol',
        source: 'markers',
        minzoom: 15,
        filter: ['in', ['get', 'popup_type'], ['literal', ['nodata', 'empty']]],
        layout: sharedLayout,
        paint: sharedPaint,
      });
    }
  }

  function updateWmsLayer(drinkId: number | null) {
    const url = `${GEOSERVER_URL}/wms?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&FORMAT=image/png&TRANSPARENT=true&LAYERS=spritzmap:lor_index&viewparams=drink_id:${drinkId ?? 1}&SRS=EPSG:4326&STYLES=`;
    const source = map.getSource('wms-lor') as GeoJSONSource | undefined;
    if (source) {
      (map.getSource('wms-lor') as any).tiles = [url + '&BBOX={bbox-epsg-3857}'];
      map.triggerRepaint();
    }
  }

  function buildOtherDrinksHtml(
    allPrices: { drink_id: number; drink_name: string; price: number }[],
    excludeDrinkId: number | null,
  ): string {
    const others = allPrices.filter((p) => p.drink_id !== excludeDrinkId);
    if (!others.length) return '';
    let html = `<div class="popup-other-drinks"><span>${$t.map.popup_other_drinks}</span><ul>`;
    for (const p of others) {
      html += `<li>${p.drink_name} — <b>${p.price.toFixed(2)} €</b></li>`;
    }
    html += `</ul></div>`;
    return html;
  }

  async function showPopup(e: any) {
    const feature = e.features?.[0];
    if (!feature) return;
    const props = feature.properties;
    const coords = feature.geometry.coordinates.slice();
    const address = props.address?.trim().replace(/^,|,$/g, '').trim();

    // Fetch all prices for this location in parallel with popup render prep
    const pricesRes = await fetch(`${API_URL}/locations/${props.id}/prices`).catch(() => null);
    const allPrices: { drink_id: number; drink_name: string; price: number }[] =
      pricesRes?.ok ? await pricesRes.json() : [];

    let html = `<strong>${props.name}</strong><br>`;
    if (address) html += `<small>${address}</small><br>`;

    if (props.popup_type === 'priced') {
      const popupIconHtml = buildIconHtml(props.drink_color_hex, props.avg_color_value, 200);
      html += `<div style="display:flex;justify-content:center;margin:6px 0;">${popupIconHtml}</div>`;
      html += `${props.drink_name} — <b>${Number(props.price).toFixed(2)} €</b>`;
      html += buildOtherDrinksHtml(allPrices, props.drink_id);
      html += `<div class="popup-meta">${$t.map.popup_reported_by(props.reported_by, props.reported_at)}</div>`;
      if ($isLoggedIn) html += `<button class="popup-btn" data-id="${props.id}" data-name="${props.name}" data-empty="false">${$t.map.btn_add_spritz}</button>`;
    } else if (props.popup_type === 'nodata') {
      html += `<em style="color:#aaa;font-size:0.8rem">${$t.map.popup_no_price_for_drink}</em>`;
      html += buildOtherDrinksHtml(allPrices, null);
      if ($isLoggedIn) html += `<br><button class="popup-btn" data-id="${props.id}" data-name="${props.name}" data-empty="true">${$t.map.btn_add_spritz}</button>`;
    } else {
      html += `<em style="color:#aaa;font-size:0.8rem">${$t.map.popup_no_price}</em>`;
      html += buildOtherDrinksHtml(allPrices, null);
      if ($isLoggedIn) html += `<br><button class="popup-btn" data-id="${props.id}" data-name="${props.name}" data-empty="true">${$t.map.btn_add_spritz}</button>`;
    }

    popup.setLngLat(coords).setHTML(html).addTo(map);

    // Wire up button after popup DOM is created
    setTimeout(() => {
      const btn = document.querySelector('.popup-btn') as HTMLButtonElement | null;
      btn?.addEventListener('click', () => {
        submitLocationId = Number(btn.dataset.id);
        submitLocationName = btn.dataset.name ?? '';
        submitIsEmpty = btn.dataset.empty === 'true';
        submitOpen = true;
        popup.remove();
      });
    }, 0);
  }

  onMount(async () => {
    const maplibre = await import('maplibre-gl');
    await import('maplibre-gl/dist/maplibre-gl.css');

    map = new maplibre.Map({
      container: mapEl,
      style: {
        version: 8,
        glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
        sources: {
          'basemap': {
            type: 'raster',
            tiles: [
              'https://sgx.geodatenzentrum.de/wmts_basemapde/tile/1.0.0/de_basemapde_web_raster_grau/default/GLOBAL_WEBMERCATOR/{z}/{y}/{x}.png'
            ],
            tileSize: 256,
            attribution: '© GeoBasis-DE / BKG 2024',
          },
          'wms-lor': {
            type: 'raster',
            tiles: [
              `${GEOSERVER_URL}/wms?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&FORMAT=image/png&TRANSPARENT=true&LAYERS=spritzmap:lor_index&viewparams=drink_id:${$selectedDrinkId ?? 1}&SRS=EPSG:3857&STYLES=&BBOX={bbox-epsg-3857}&WIDTH=256&HEIGHT=256`,
            ],
            tileSize: 256,
          },
        },
        layers: [
          { id: 'basemap', type: 'raster', source: 'basemap', paint: { 'raster-opacity': 0.5 } },
          { id: 'wms-lor', type: 'raster', source: 'wms-lor', paint: { 'raster-opacity': 1 },
            minzoom: 0, maxzoom: 15 },
        ],
      },
      center: [13.405, 52.52],
      zoom: 12,
    });

    popup = new maplibre.Popup({ closeButton: true, maxWidth: '280px' });

    let unsubDrink: () => void;
    let unsubTier: () => void;

    map.on('load', async () => {
      for (const layer of ['markers-priced', 'markers-nodata']) {
        map.on('click', layer, showPopup);
        map.on('mouseenter', layer, () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mouseleave', layer, () => { map.getCanvas().style.cursor = ''; });
      }

      // Drink-color tint overlay — appears at zoom ≥ 15 when LOR layer hides
      map.addLayer(
        {
          id: 'drink-tint',
          type: 'background',
          minzoom: 15,
          paint: {
            'background-color': getDrinkColor($selectedDrinkId),
            'background-opacity': 0.12,
          },
        },
        'wms-lor',
      );

      // Initial load
      await loadMarkers($selectedDrinkId, $selectedPriceTier);

      // Subscribe after map is ready — first call fires immediately with current value
      const updateWms = (drinkId: number | null) => {
        const src = map.getSource('wms-lor') as any;
        if (src?.setTiles) {
          src.setTiles([`${GEOSERVER_URL}/wms?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&FORMAT=image/png&TRANSPARENT=true&LAYERS=spritzmap:lor_index&viewparams=drink_id:${drinkId ?? 1}&SRS=EPSG:3857&STYLES=&BBOX={bbox-epsg-3857}&WIDTH=256&HEIGHT=256`]);
        }
      };

      let firstDrink = true;
      unsubDrink = selectedDrinkId.subscribe((drinkId) => {
        if (firstDrink) { firstDrink = false; return; }
        loadMarkers(drinkId, $selectedPriceTier);
        updateWms(drinkId);
        updateBasemapTint(drinkId);
      });

      let firstTier = true;
      unsubTier = selectedPriceTier.subscribe((tier) => {
        if (firstTier) { firstTier = false; return; }
        loadMarkers($selectedDrinkId, tier);
      });
    });

    return () => {
      unsubDrink?.();
      unsubTier?.();
    };
  });

  onDestroy(() => {
    map?.remove();
  });
</script>

<div bind:this={mapEl} class="map-container"></div>

<button
  class="locate-btn"
  title={$t.map.locate}
  onclick={() => {
    navigator.geolocation.getCurrentPosition(
      (pos) => map?.flyTo({ center: [pos.coords.longitude, pos.coords.latitude], zoom: 17 }),
      () => {}
    );
  }}
>
  ◎
</button>

<PriceSubmitModal
  bind:open={submitOpen}
  locationId={submitLocationId}
  locationName={submitLocationName}
  isEmptyLocation={submitIsEmpty}
  onsubmitted={() => loadMarkers($selectedDrinkId, $selectedPriceTier)}
/>

<style>
  .map-container {
    width: 100%;
    height: 100%;
  }

  .locate-btn {
    position: absolute;
    bottom: 1.5rem;
    left: 0.65rem;
    z-index: 5;
    width: 34px;
    height: 34px;
    background: white;
    border: 2px solid rgba(0,0,0,0.25);
    border-radius: 4px;
    font-size: 1.1rem;
    line-height: 1;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 1px 5px rgba(0,0,0,0.2);
    padding: 0;
  }

  @media (max-width: 640px) {
    .locate-btn {
      bottom: 4.5rem;
    }
  }

  .locate-btn:hover { background: #f4f4f4; }

  :global(.popup-btn) {
    margin-top: 6px;
    padding: 4px 10px;
    background: #e8500a;
    color: white;
    border: none;
    border-radius: 5px;
    font-size: 0.8rem;
    font-weight: 600;
    cursor: pointer;
    width: 100%;
  }

  :global(.popup-meta) {
    margin-top: 8px;
    font-size: 0.72rem;
    color: #bbb;
    text-align: right;
  }

  :global(.popup-other-drinks) {
    margin-top: 8px;
    border-top: 1px solid #eee;
    padding-top: 6px;
  }

  :global(.popup-other-drinks span) {
    font-size: 0.75rem;
    color: #999;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  :global(.popup-other-drinks ul) {
    margin: 4px 0 0;
    padding: 0;
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  :global(.popup-other-drinks li) {
    font-size: 0.8rem;
    color: #555;
  }

  :global(.maplibregl-popup-content) {
    border-radius: 12px;
    padding: 2rem;
    font-family: system-ui, sans-serif;
    font-size: 0.875rem;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
    border: none;
  }

  :global(.maplibregl-popup-tip) {
    display: none;
  }

  :global(.maplibregl-popup-close-button) {
    font-size: 1.2rem;
    padding: 0.25rem 0.5rem;
    color: #666;
  }
</style>
