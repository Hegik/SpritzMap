<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { selectedDrinkId, selectedPriceTier } from '$lib/stores/map';
  import { createGlassIcon, createEmptyGlassIcon } from '$lib/utils/markerIcon';
  import PriceSubmitModal from '$lib/components/PriceSubmitModal.svelte';
  import { isLoggedIn } from '$lib/stores/auth';
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let leaflet: any;

  let mapEl: HTMLDivElement;
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

  const GEOSERVER_URL = import.meta.env.VITE_GEOSERVER_URL ?? 'http://localhost:8080/geoserver';
  const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

  async function loadEmptyMarkers() {
    if (!map) return;
    emptyLayer.clearLayers();

    const res = await fetch(`${API_URL}/locations/geojson/empty`);
    if (!res.ok) return;
    const geojson: GeoJSON.FeatureCollection = await res.json();

    for (const feature of geojson.features) {
      const { geometry, properties } = feature as GeoJSON.Feature<GeoJSON.Point>;
      const [lng, lat] = geometry.coordinates;
      const icon = createEmptyGlassIcon(leaflet);

      const marker = leaflet.marker([lat, lng], { icon });
      const locId = properties!.id;
      const locName = properties!.name;
      marker.bindPopup(`
        <strong>${locName}</strong><br>
        <small>${properties!.address}</small><br>
        <em style="color:#aaa;font-size:0.8rem">Noch kein Preis gemeldet</em>
        ${$isLoggedIn ? '<br><button class="popup-btn">Preis melden</button>' : ''}
      `);
      marker.on('popupopen', (e: any) => {
        const btn = e.popup.getElement()?.querySelector('.popup-btn');
        btn?.addEventListener('click', () => {
          submitLocationId = locId;
          submitLocationName = locName;
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

    const params = new URLSearchParams();
    if (drinkId) params.set('drink_id', String(drinkId));
    if (priceTier) params.set('price_tier', priceTier);

    const res = await fetch(`${API_URL}/locations/geojson?${params}`);
    if (!res.ok) return;
    const geojson: GeoJSON.FeatureCollection = await res.json();

    for (const feature of geojson.features) {
      const { geometry, properties } = feature as GeoJSON.Feature<GeoJSON.Point>;
      const [lng, lat] = geometry.coordinates;
      const icon = createGlassIcon(
        leaflet,
        properties!.drink_color_hex,
        properties!.avg_color_value,
        properties!.price_tier
      );

      const marker = leaflet.marker([lat, lng], { icon });
      const locId = properties!.id;
      const locName = properties!.name;
      marker.bindPopup(`
        <strong>${locName}</strong><br>
        ${properties!.drink_name} — <b>${properties!.price.toFixed(2)} €</b><br>
        <small>${properties!.address}</small>
        ${$isLoggedIn ? '<br><button class="popup-btn">Preis melden / aktualisieren</button>' : ''}
      `);
      marker.on('popupopen', (e: any) => {
        const btn = e.popup.getElement()?.querySelector('.popup-btn');
        btn?.addEventListener('click', () => {
          submitLocationId = locId;
          submitLocationName = locName;
          submitOpen = true;
          map.closePopup();
        });
      });
      markerLayer.addLayer(marker);
    }
  }

  onMount(async () => {
    leaflet = await import('leaflet');
    await import('leaflet/dist/leaflet.css');

    map = leaflet.map(mapEl, {
      center: [52.52, 13.405], // Berlin
      zoom: 12,
    });

    leaflet.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors',
      maxZoom: 19,
    }).addTo(map);

    markerLayer = leaflet.layerGroup();
    emptyLayer = leaflet.layerGroup();

    wmsLayer = leaflet.tileLayer.wms(`${GEOSERVER_URL}/wms`, {
      layers: 'spritzmap:lor_price_summary',
      format: 'image/png',
      transparent: true,
      opacity: 0.4,
      attribution: 'SpritzMap LOR Layer',
    });

    function applyZoomLayers() {
      const zoom = map.getZoom();
      if (zoom < 15) {
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

    const unsubDrink = selectedDrinkId.subscribe(() => loadMarkers($selectedDrinkId, $selectedPriceTier));
    const unsubTier = selectedPriceTier.subscribe(() => loadMarkers($selectedDrinkId, $selectedPriceTier));

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

<PriceSubmitModal
  bind:open={submitOpen}
  locationId={submitLocationId}
  locationName={submitLocationName}
  onsubmitted={() => { loadEmptyMarkers(); loadMarkers($selectedDrinkId, $selectedPriceTier); }}
/>

<style>
  .map-container {
    width: 100%;
    height: 100%;
    z-index: 0;
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
  }
</style>
