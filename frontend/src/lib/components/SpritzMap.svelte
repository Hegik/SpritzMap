<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { selectedDrinkId, selectedPriceTier } from '$lib/stores/map';
  import { createGlassIcon, createEmptyGlassIcon, createNodataGlassIcon, buildIconHtml } from '$lib/utils/markerIcon';
  import PriceSubmitModal from '$lib/components/PriceSubmitModal.svelte';
  import { isLoggedIn } from '$lib/stores/auth';
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let leaflet: any;

  let mapEl: HTMLDivElement;

  export function reloadMarkers() {
    loadEmptyMarkers();
    loadMarkers($selectedDrinkId, $selectedPriceTier);
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let map: any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let markerLayer: any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let wmsLayer: any = null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let emptyLayer: any;

  let submitOpen = $state(false);
  let submitLocationId = $state<number | null>(null);
  let submitLocationName = $state('');
  let submitIsEmpty = $state(false);

  const GEOSERVER_URL = import.meta.env.VITE_GEOSERVER_URL ?? 'http://localhost:8080/geoserver';
  const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

  async function loadEmptyMarkers() {
    if (!map) return;
    emptyLayer.clearLayers();

    const res = await fetch(`${API_URL}/locations/geojson/empty`);
    if (!res.ok) return;
    const geojson: GeoJSON.FeatureCollection = await res.json();

    const emptyIcon = await createEmptyGlassIcon(leaflet);
    for (const feature of geojson.features) {
      const { geometry, properties } = feature as GeoJSON.Feature<GeoJSON.Point>;
      const [lng, lat] = geometry.coordinates;

      const marker = leaflet.marker([lat, lng], { icon: emptyIcon });
      const locId = properties!.id;
      const locName = properties!.name;
      const emptyAddress = properties!.address?.trim().replace(/^,|,$/g, '').trim();
      marker.bindPopup(`
        <strong>${locName}</strong><br>
        ${emptyAddress ? `<small>${emptyAddress}</small><br>` : ''}
        <em style="color:#aaa;font-size:0.8rem">Noch kein Preis gemeldet</em>
        ${$isLoggedIn ? '<br><button class="popup-btn">Preis melden</button>' : ''}
      `);
      marker.on('popupopen', (e: any) => {
        const btn = e.popup.getElement()?.querySelector('.popup-btn');
        btn?.addEventListener('click', () => {
          submitLocationId = locId;
          submitLocationName = locName;
          submitIsEmpty = true;
          submitOpen = true;
          map.closePopup();
        });
      });
      emptyLayer.addLayer(marker);
    }
  }

  async function loadMarkers(drinkId: number | null, priceTier: string | null) {
    if (!map) return;
    markerLayer.clearLayers();

    // When filtering by drink, suppress the standalone empty-glass layer —
    // nodata icons (fetched below) replace it for all unpriced locations.
    if (drinkId) {
      emptyLayer.clearLayers();
    }

    const params = new URLSearchParams();
    if (drinkId) params.set('drink_id', String(drinkId));
    if (priceTier) params.set('price_tier', priceTier);

    // Fetch colored markers and (when drink is selected) nodata markers in parallel
    const fetches: [Promise<Response>, Promise<Response> | null] = [
      fetch(`${API_URL}/locations/geojson?${params}`),
      drinkId ? fetch(`${API_URL}/locations/geojson/nodata?drink_id=${drinkId}`) : null,
    ];
    const [res, nodataRes] = await Promise.all(fetches);
    if (!res.ok) return;
    const geojson: GeoJSON.FeatureCollection = await res.json();

    // Nodata icons — locations with no price for the selected drink
    if (nodataRes?.ok) {
      const nodataGeojson: GeoJSON.FeatureCollection = await nodataRes.json();
      const nodataIcon = await createNodataGlassIcon(leaflet);
      for (const feature of nodataGeojson.features) {
        const { geometry, properties } = feature as GeoJSON.Feature<GeoJSON.Point>;
        const [lng, lat] = geometry.coordinates;
        const marker = leaflet.marker([lat, lng], { icon: nodataIcon });
        const locName = properties!.name;
        const address = properties!.address?.trim().replace(/^,|,$/g, '').trim();
        marker.bindPopup(`
          <strong>${locName}</strong><br>
          ${address ? `<small>${address}</small><br>` : ''}
          <em style="color:#aaa;font-size:0.8rem">Noch kein Preis für diesen Drink</em>
          ${$isLoggedIn ? '<br><button class="popup-btn">Preis melden</button>' : ''}
        `);
        marker.on('popupopen', (e: any) => {
          const btn = e.popup.getElement()?.querySelector('.popup-btn');
          btn?.addEventListener('click', () => {
            submitLocationId = properties!.id;
            submitLocationName = locName;
            submitIsEmpty = true;
            submitOpen = true;
            map.closePopup();
          });
        });
        markerLayer.addLayer(marker);
      }
    }

    const coloredMarkers = await Promise.all(geojson.features.map(async (feature) => {
      const { geometry, properties } = feature as GeoJSON.Feature<GeoJSON.Point>;
      const [lng, lat] = geometry.coordinates;
      const icon = await createGlassIcon(
        leaflet,
        properties!.drink_color_hex,
        properties!.avg_color_value,
        properties!.price_tier
      );

      const marker = leaflet.marker([lat, lng], { icon });
      const locId = properties!.id;
      const locName = properties!.name;
      const address = properties!.address?.trim().replace(/^,|,$/g, '').trim();
      const popupIconHtml = buildIconHtml(properties!.drink_color_hex, properties!.avg_color_value, 200);
      marker.bindPopup(`
        <strong>${locName}</strong><br>
        <div style="display:flex;justify-content:center;margin:6px 0;">${popupIconHtml}</div>
        ${address ? `<small>${address}</small><br>` : ''}
        ${properties!.drink_name} — <b>${properties!.price.toFixed(2)} €</b><br>
        ${$isLoggedIn ? '<br><button class="popup-btn">Preis melden / aktualisieren</button>' : ''}
      `);
      marker.on('popupopen', (e: any) => {
        const btn = e.popup.getElement()?.querySelector('.popup-btn');
        btn?.addEventListener('click', () => {
          submitLocationId = locId;
          submitLocationName = locName;
          submitIsEmpty = false;
          submitOpen = true;
          map.closePopup();
        });
      });
      return marker;
    }));
    coloredMarkers.forEach(m => markerLayer.addLayer(m));
  }

  onMount(async () => {
    leaflet = await import('leaflet');
    await import('leaflet/dist/leaflet.css');

    map = leaflet.map(mapEl, {
      center: [52.52, 13.405], // Berlin
      zoom: 12,
    });

    leaflet.tileLayer.wms('https://sgx.geodatenzentrum.de/wms_basemapde', {
      layers: 'de_basemapde_web_raster_grau',
      format: 'image/png',
      transparent: false,
      version: '1.3.0',
      attribution: '© GeoBasis-DE / BKG 2024',
      maxZoom: 20,
      opacity: 0.5,
    }).addTo(map);

    markerLayer = leaflet.layerGroup();
    emptyLayer = leaflet.layerGroup();

    function createWmsLayer(drinkId: number | null) {
      return leaflet.tileLayer.wms(`${GEOSERVER_URL}/wms`, {
        layers: 'spritzmap:lor_index',
        format: 'image/png',
        transparent: true,
        opacity: 0.4,
        attribution: 'SpritzMap LOR Layer',
        viewparams: `drink_id:${drinkId ?? 1}`,
      });
    }

    wmsLayer = createWmsLayer($selectedDrinkId);

    function applyZoomLayers() {
      const zoom = map.getZoom();
      if (zoom < 17) {
        if (!map.hasLayer(wmsLayer)) wmsLayer.addTo(map);
        if (map.hasLayer(markerLayer)) map.removeLayer(markerLayer);
        if (map.hasLayer(emptyLayer)) map.removeLayer(emptyLayer);
      } else {
        if (map.hasLayer(wmsLayer)) map.removeLayer(wmsLayer);
        if (!map.hasLayer(markerLayer)) markerLayer.addTo(map);
        if (!map.hasLayer(emptyLayer)) emptyLayer.addTo(map);
      }
    }

    map.on('zoomend', applyZoomLayers);
    applyZoomLayers();

    await loadEmptyMarkers();
    await loadMarkers(null, null);

    const unsubDrink = selectedDrinkId.subscribe((drinkId) => {
      loadMarkers(drinkId, $selectedPriceTier);
      if (map.hasLayer(wmsLayer)) map.removeLayer(wmsLayer);
      wmsLayer = createWmsLayer(drinkId);
      if (map.getZoom() < 16) wmsLayer.addTo(map);
    });
    const unsubTier = selectedPriceTier.subscribe((tier) => loadMarkers($selectedDrinkId, tier));

    return () => {
      unsubDrink();
      unsubTier();
    };
  });

  onDestroy(() => {
    map?.remove();
  });
</script>

<div bind:this={mapEl} class="map-container"></div>

<button
  class="locate-btn"
  title="Mein Standort"
  onclick={() => map?.locate({ setView: true, maxZoom: 17 })}
>
  ◎
</button>

<PriceSubmitModal
  bind:open={submitOpen}
  locationId={submitLocationId}
  locationName={submitLocationName}
  isEmptyLocation={submitIsEmpty}
  onsubmitted={() => { loadEmptyMarkers(); loadMarkers($selectedDrinkId, $selectedPriceTier); }}
/>

<style>
  .map-container {
    width: 100%;
    height: 100%;
    z-index: 0;
  }

  .locate-btn {
    position: absolute;
    bottom: 1.5rem;
    right: 0.65rem;
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

  .locate-btn:hover {
    background: #f4f4f4;
  }

  :global(.spritz-marker) {
    background: none;
    border: none;
    display: flex;
    flex-direction: column;
    align-items: center;
  }

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

  :global(.spritz-label) {
    font-size: 11px;
    font-weight: 700;
    color: #333;
    text-shadow: 0 1px 2px white;
    margin-top: 2px;
    text-align: center;
    letter-spacing: 0;
    width: 48px;
  }
</style>
