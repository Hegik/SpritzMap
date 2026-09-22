<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { drinks, selectedDrinkId, selectedPriceTier, cities, selectedCity } from '$lib/stores/map';
  import { getGlassIconDataUrl, getEmptyGlassDataUrl, getNodataGlassDataUrl, buildIconHtml } from '$lib/utils/markerIcon';
  import PriceSubmitModal from '$lib/components/PriceSubmitModal.svelte';
  import HelpModal from '$lib/components/HelpModal.svelte';
  import SplashModal from '$lib/components/SplashModal.svelte';
  import PhotoLightbox from '$lib/components/PhotoLightbox.svelte';
  import MapLegend from '$lib/components/MapLegend.svelte';
  import { isLoggedIn, user } from '$lib/stores/auth';
  import { api, mediaUrl } from '$lib/api/client';
  import type { GlassType, Photo } from '$lib/types/photo';
  import { glassIconSvg } from '$lib/utils/glassIcons';
  import { t } from '$lib/i18n';
  import type { Map, Popup, GeoJSONSource } from 'maplibre-gl';
  import type { CityMeta } from '$lib/stores/map';

  let mapEl: HTMLDivElement;
  let map: Map;
  let popup: Popup;
  let watchId: number | null = null;
  let userLocationInitialized = false;
  let userLocationInitializing = false;

  export function reloadMarkers() {
    const city = $selectedCity;
    if (city) loadMarkers(city, $selectedDrinkId, $selectedPriceTier);
  }

  let submitOpen = $state(false);
  let submitLocationId = $state<number | null>(null);
  let submitLocationName = $state('');
  let submitIsEmpty = $state(false);
  let submitCoords = $state<[number, number] | null>(null);
  let helpOpen = $state(false);
  let lightboxOpen = $state(false);
  let lightboxPhotos = $state<Photo[]>([]);
  let lightboxIndex = $state(0);
  let mapZoom = $state(12);

  // Stadtauswahl: Pills bei wenigen Städten, durchsuchbare Liste ab CITY_PILLS_MAX
  const CITY_PILLS_MAX = 4;
  let cityMenuOpen = $state(false);
  let citySearch = $state('');
  const filteredCities = $derived(
    $cities.filter((c) => c.name.toLowerCase().includes(citySearch.trim().toLowerCase()))
  );
  let suppressCityFly = false;

  function chooseCity(city: CityMeta) {
    cityMenuOpen = false;
    citySearch = '';
    selectedCity.set(city);
  }

  /** Stadt am Standort vorwählen. fly=false: Karte bleibt beim Nutzer statt zum Stadtzentrum zu springen. */
  async function selectCityAt(lat: number, lon: number, fly: boolean) {
    const res = await fetch(`${API_URL}/cities/locate?lat=${lat}&lon=${lon}`).catch(() => null);
    if (!res?.ok) return;
    const { city_id } = await res.json();
    const city = $cities.find((c) => c.id === city_id);
    if (!city || city.id === $selectedCity?.id) return;
    suppressCityFly = !fly;
    selectedCity.set(city);
  }
  let splashOpen = $state(false);

  // Oberhalb dieser Zoomstufe wird der LOR-WMS-Layer ausgeblendet und die Marker übernehmen
  const WMS_MAX_ZOOM = 15;
  const GEOSERVER_URL = import.meta.env.VITE_GEOSERVER_URL ?? 'http://localhost:8080/geoserver';
  // Ein gemeinsamer Gebietslayer für alle Städte, gefiltert per viewparams city_id
  const WMS_AREA_LAYER = import.meta.env.VITE_WMS_AREA_LAYER ?? 'spritzmap:area_summary';
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

  async function loadMarkers(city: CityMeta, drinkId: number | null, priceTier: string | null) {
    if (!map) return;

    const params = new URLSearchParams({ city_id: String(city.id) });
    if (drinkId) params.set('drink_id', String(drinkId));
    if (priceTier) params.set('price_tier', priceTier);

    // Lokale ohne Eintrag (Fragezeichen-/Leerglas) sind nur zum Eintragen da → nur für eingeloggte Nutzer
    const showUnpriced = $isLoggedIn;
    const [res, nodataRes, emptyRes] = await Promise.all([
      fetch(`${API_URL}/locations/geojson?${params}`),
      showUnpriced && drinkId ? fetch(`${API_URL}/locations/geojson/nodata?city_id=${city.id}&drink_id=${drinkId}`) : null,
      showUnpriced && !drinkId ? fetch(`${API_URL}/locations/geojson/empty?city_id=${city.id}`) : null,
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

    if (nodataRes?.ok) {
      if (!seenKeys.has('__nodata__')) {
        seenKeys.add('__nodata__');
        iconJobs.push({ key: '__nodata__', promise: getNodataGlassDataUrl() });
      }
    }
    if (emptyRes?.ok) {
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
        'text-font': ['Open Sans Regular'],
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

  function buildWmsUrl(drinkId: number | null, cityId: number | null): string {
    return `${GEOSERVER_URL}/wms?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&FORMAT=image/png&TRANSPARENT=true&LAYERS=${WMS_AREA_LAYER}&viewparams=city_id:${cityId ?? 0};drink_id:${drinkId ?? 1}&SRS=EPSG:3857&STYLES=&BBOX={bbox-epsg-3857}&WIDTH=256&HEIGHT=256`;
  }

  function applyCity(city: CityMeta) {
    // Fly to new city center (nicht, wenn die Stadt über den eigenen Standort gewählt wurde)
    if (!suppressCityFly) map.flyTo({ center: [city.center_lon, city.center_lat], zoom: city.default_zoom });
    suppressCityFly = false;

    // Gebietslayer auf die neue Stadt filtern; ohne Gebiete ausblenden
    if (map.getLayer('wms-lor')) {
      map.setLayoutProperty('wms-lor', 'visibility', city.has_areas ? 'visible' : 'none');
    }
    if (city.has_areas) {
      const src = map.getSource('wms-lor') as any;
      if (src?.setTiles) {
        src.setTiles([buildWmsUrl($selectedDrinkId, city.id)]);
      }
    }

    loadMarkers(city, $selectedDrinkId, $selectedPriceTier);
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

  const INTENSITY_LABELS = ['Fast nur Sekt', 'sehr lasch', 'lasch', 'ok', 'schon ordentlich', 'stark', 'Sekt, wo?'];

  function buildIntensityBarHtml(colorValue: number, colorHex: string): string {
    const leftPct = (colorValue / 255) * 100;
    const segmentIndex = Math.min(Math.floor((colorValue / 255) * 7), 6);
    const label = INTENSITY_LABELS[segmentIndex];
    return `<div class="popup-intensity"><div class="popup-intensity-title">Mischverhältnis</div><div class="popup-intensity-track" style="background:${colorHex}20;"><div class="popup-intensity-dot" style="left:${leftPct.toFixed(1)}%;background:${colorHex};"></div></div><div class="popup-intensity-label">${label}</div></div>`;
  }

  function escapeHtml(value: unknown): string {
    return String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
  }

  // Glasform, Anzahl der Meldungen und Notiz zum aktuellen Preis
  function buildDetailsHtml(props: Record<string, any>): string {
    const rows: string[] = [];
    const glass = props.glass_type as GlassType | null;
    if (glass && glass in $t.glass) {
      rows.push(`<div class="popup-fact">${glassIconSvg(glass, 18)}<span>${escapeHtml($t.glass[glass])}</span></div>`);
    }
    const count = Number(props.entry_count);
    if (count > 0) {
      rows.push(`<div class="popup-fact"><span class="popup-fact-num">${count}</span><span>${escapeHtml($t.map.popup_entry_count(count))}</span></div>`);
    }
    let html = rows.length ? `<div class="popup-facts">${rows.join('')}</div>` : '';
    if (props.note) html += `<div class="popup-note">„${escapeHtml(props.note)}“</div>`;
    return html;
  }

  function buildPhotoStripHtml(photos: Photo[]): string {
    if (!photos.length) return '';
    const thumbs = photos
      .map((p, i) => `<img class="popup-photo" data-idx="${i}" src="${escapeHtml(mediaUrl(p.thumb_url))}" alt="${escapeHtml($t.photos.photo_alt)}" loading="lazy" />`)
      .join('');
    return `<div class="popup-photos">${thumbs}</div>`;
  }

  function buildConfirmHtml(props: Record<string, any>): string {
    let html = '';
    if (props.last_confirmed_at && props.last_confirmed_at !== props.reported_at) {
      html += `<div class="popup-meta">${escapeHtml($t.map.popup_confirmed_at(props.last_confirmed_at))}</div>`;
    }
    const isOwn = $user != null && props.entry_user_id === $user.id;
    if ($isLoggedIn && props.entry_id && !isOwn) {
      html += `<button class="popup-confirm" data-entry-id="${escapeHtml(props.entry_id)}">${escapeHtml($t.map.btn_confirm)}</button>`;
    }
    return html;
  }

  async function confirmPrice(btn: HTMLButtonElement) {
    btn.disabled = true;
    try {
      await api.post(`/prices/${btn.dataset.entryId}/confirm`, {});
      btn.textContent = $t.map.confirm_done;
      btn.classList.add('done');
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '';
      btn.textContent = msg.startsWith('409') ? $t.map.confirm_already : $t.map.confirm_error;
    }
  }

  async function updateUserLocation(pos: GeolocationPosition) {
    if (!map) return;
    const { longitude, latitude } = pos.coords;
    const fc: GeoJSON.FeatureCollection = {
      type: 'FeatureCollection',
      features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [longitude, latitude] }, properties: {} }],
    };

    if (userLocationInitialized) {
      (map.getSource('user-location') as GeoJSONSource).setData(fc);
      return;
    }
    if (userLocationInitializing) return;
    userLocationInitializing = true;

    // Draw dot onto canvas so icon-pitch-alignment:'map' makes it oval when map is tilted
    const size = 72;
    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d')!;
    const cx = size / 2, cy = size / 2, r = 24;
    ctx.shadowColor = 'rgba(0,0,0,0.35)';
    ctx.shadowBlur = 10;
    ctx.shadowOffsetY = 3;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fillStyle = '#e8500a';
    ctx.fill();
    ctx.shadowColor = 'transparent';
    ctx.shadowBlur = 0;
    ctx.shadowOffsetY = 0;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.strokeStyle = 'white';
    ctx.lineWidth = 5;
    ctx.stroke();

    const dotImg = await new Promise<HTMLImageElement>((resolve) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.src = canvas.toDataURL();
    });

    map.addSource('user-location', { type: 'geojson', data: fc });
    if (!map.hasImage('user-location-dot')) map.addImage('user-location-dot', dotImg);
    map.addLayer({
      id: 'user-location-layer',
      type: 'symbol',
      source: 'user-location',
      layout: {
        'icon-image': 'user-location-dot',
        'icon-size': 0.35,
        'icon-allow-overlap': true,
        'icon-pitch-alignment': 'map',
        'icon-rotation-alignment': 'map',
      } as any,
    });

    userLocationInitialized = true;
    userLocationInitializing = false;
  }

  function locateUser() {
    if (watchId !== null) {
      // Already watching — just fly to current position
      navigator.geolocation.getCurrentPosition(
        (pos) => map?.flyTo({ center: [pos.coords.longitude, pos.coords.latitude], zoom: 17 }),
        () => {},
        { enableHighAccuracy: true, timeout: 10000 },
      );
      return;
    }

    let didFly = false;
    watchId = navigator.geolocation.watchPosition(
      (pos) => {
        updateUserLocation(pos);
        if (!didFly) {
          didFly = true;
          selectCityAt(pos.coords.latitude, pos.coords.longitude, false);
          map?.flyTo({ center: [pos.coords.longitude, pos.coords.latitude], zoom: 17 });
        }
      },
      () => {},
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }

  async function showPopup(e: any) {
    const feature = e.features?.[0];
    if (!feature) return;
    const props = feature.properties;
    const coords = feature.geometry.coordinates.slice();
    const address = props.address?.trim().replace(/^,|,$/g, '').trim();

    // Fetch all prices + photos for this location in parallel
    const [pricesRes, photosRes] = await Promise.all([
      fetch(`${API_URL}/locations/${props.id}/prices`).catch(() => null),
      fetch(`${API_URL}/locations/${props.id}/photos`).catch(() => null),
    ]);
    const allPrices: { drink_id: number; drink_name: string; price: number }[] =
      pricesRes?.ok ? await pricesRes.json() : [];
    const photos: Photo[] = photosRes?.ok ? await photosRes.json() : [];

    const typeLabel = $t.map.location_type[props.location_type as keyof typeof $t.map.location_type];
    let html = `<strong>${escapeHtml(props.name)}</strong>`;
    if (typeLabel) html += ` <span class="popup-type">${escapeHtml(typeLabel)}</span>`;
    html += '<br>';
    if (address) html += `<small>${escapeHtml(address)}</small><br>`;

    if (props.popup_type === 'priced') {
      const popupIconHtml = buildIconHtml(props.drink_color_hex, props.avg_color_value, 200);
      html += `<div style="display:flex;justify-content:center;margin:6px 0;">${popupIconHtml}</div>`;
      html += buildIntensityBarHtml(props.avg_color_value, props.drink_color_hex);
      html += `<div class="popup-price">${escapeHtml(props.drink_name)} — <b>${Number(props.price).toFixed(2)} €</b>`;
      if (props.price_tier) html += ` <span class="popup-tier">${escapeHtml(props.price_tier)}</span>`;
      html += `</div>`;
      html += buildDetailsHtml(props);
      html += buildOtherDrinksHtml(allPrices, props.drink_id);
      html += buildPhotoStripHtml(photos);
      html += `<div class="popup-meta">${$t.map.popup_reported_by(props.reported_by, props.reported_at)}</div>`;
      html += buildConfirmHtml(props);
      if ($isLoggedIn) html += `<button class="popup-btn" data-id="${props.id}" data-name="${escapeHtml(props.name)}" data-empty="false">${$t.map.btn_add_spritz}</button>`;
    } else if (props.popup_type === 'nodata') {
      html += `<em style="color:#aaa;font-size:0.8rem">${$t.map.popup_no_price_for_drink}</em>`;
      html += buildOtherDrinksHtml(allPrices, null);
      html += buildPhotoStripHtml(photos);
      if ($isLoggedIn) html += `<br><button class="popup-btn" data-id="${props.id}" data-name="${escapeHtml(props.name)}" data-empty="${allPrices.length === 0}">${$t.map.btn_add_spritz}</button>`;
    } else {
      html += `<em style="color:#aaa;font-size:0.8rem">${$t.map.popup_no_price}</em>`;
      html += buildOtherDrinksHtml(allPrices, null);
      if ($isLoggedIn) html += `<br><button class="popup-btn" data-id="${props.id}" data-name="${escapeHtml(props.name)}" data-empty="${allPrices.length === 0}">${$t.map.btn_add_spritz}</button>`;
    }

    popup.setLngLat(coords).setHTML(html).addTo(map);

    // Wire up buttons after popup DOM is created
    setTimeout(() => {
      const root = popup.getElement();
      root?.querySelectorAll<HTMLImageElement>('.popup-photo').forEach((img) => {
        img.addEventListener('click', () => {
          lightboxPhotos = photos;
          lightboxIndex = Number(img.dataset.idx);
          lightboxOpen = true;
        });
      });
      const confirmBtn = root?.querySelector('.popup-confirm') as HTMLButtonElement | null;
      confirmBtn?.addEventListener('click', () => confirmPrice(confirmBtn));

      const btn = root?.querySelector('.popup-btn') as HTMLButtonElement | null;
      btn?.addEventListener('click', () => {
        submitLocationId = Number(btn.dataset.id);
        submitLocationName = btn.dataset.name ?? '';
        submitIsEmpty = btn.dataset.empty === 'true';
        submitCoords = [coords[0], coords[1]];
        submitOpen = true;
        popup.remove();
      });
    }, 0);
  }

  onMount(() => {
    let unsubDrink: (() => void) | undefined;
    let unsubTier: (() => void) | undefined;
    let unsubCity: (() => void) | undefined;
    let unsubLogin: (() => void) | undefined;

    (async () => {
    // Load cities before map init
    const citiesRes = await fetch(`${API_URL}/cities/`).catch(() => null);
    if (citiesRes?.ok) {
      const cityList = await citiesRes.json();
      cities.set(cityList);
      if (cityList.length > 0) selectedCity.set(cityList[0]);
    }

    const initialCity = $selectedCity;

    const maplibre = await import('maplibre-gl');
    await import('maplibre-gl/dist/maplibre-gl.css');

    const centerLon = initialCity?.center_lon ?? 13.405;
    const centerLat = initialCity?.center_lat ?? 52.52;
    const zoom = initialCity?.default_zoom ?? 12;
    const hasWms = initialCity?.has_areas ?? false;

    map = new maplibre.Map({
      container: mapEl,
      style: {
        version: 8,
        // Selbst ausgeliefert (static/fonts), damit keine IP-Adressen an fremde Server gehen.
        // Nur die Bereiche Latin-1 und U+2000–20FF (€) liegen vor – mehr zeigen die Marker nicht an.
        glyphs: `${window.location.origin}/fonts/{fontstack}/{range}.pbf`,
        sources: {
          'basemap': {
            type: 'raster',
            tiles: [
              'https://sgx.geodatenzentrum.de/wmts_basemapde/tile/1.0.0/de_basemapde_web_raster_grau/default/GLOBAL_WEBMERCATOR/{z}/{y}/{x}.png'
            ],
            tileSize: 256,
            attribution: '© GeoBasis-DE / BKG 2024 | © <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>-Mitwirkende | <a href="/impressum">Impressum</a> | <a href="/datenschutz">Datenschutz</a>',
          },
          'wms-lor': {
            type: 'raster',
            tiles: [buildWmsUrl($selectedDrinkId, initialCity?.id ?? null)],
            tileSize: 256,
          },
        },
        layers: [
          { id: 'basemap', type: 'raster', source: 'basemap', paint: { 'raster-opacity': 0.5 } },
          {
            id: 'wms-lor',
            type: 'raster',
            source: 'wms-lor',
            paint: { 'raster-opacity': 1 },
            minzoom: 0,
            maxzoom: WMS_MAX_ZOOM,
            layout: { visibility: hasWms ? 'visible' : 'none' },
          },
        ],
      },
      center: [centerLon, centerLat],
      zoom,
    });

    popup = new maplibre.Popup({ closeButton: true, maxWidth: '280px' });

    mapZoom = map.getZoom();
    map.on('zoom', () => { mapZoom = map.getZoom(); });

    map.on('load', async () => {
      // Mobil startet die Quellenangabe eingeklappt („i“) – aufgeklappt ist sie zweizeilig und
      // läge über den Kartenbuttons und der Legende. Ein Tipp auf „i“ zeigt Impressum & Co.
      if (window.matchMedia('(max-width: 640px)').matches) {
        mapEl.querySelector('.maplibregl-ctrl-attrib')?.classList.remove('maplibregl-compact-show');
      }

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
      if (initialCity) {
        await loadMarkers(initialCity, $selectedDrinkId, $selectedPriceTier);
      }

      // Standort gleich beim Öffnen anfragen, um die Stadt des Nutzers zu öffnen.
      // Bei abgelehnter Berechtigung bleibt es bei der ersten Stadt der Liste.
      if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
          (pos) => {
            selectCityAt(pos.coords.latitude, pos.coords.longitude, true);
            if (watchId === null) watchId = navigator.geolocation.watchPosition(updateUserLocation, () => {});
          },
          () => {},
          { timeout: 10000, maximumAge: 300000 },
        );
      }

      // Subscribe after map is ready — first call fires immediately with current value
      const updateWms = (drinkId: number | null) => {
        const src = map.getSource('wms-lor') as any;
        if (src?.setTiles) {
          src.setTiles([buildWmsUrl(drinkId, $selectedCity?.id ?? null)]);
        }
      };

      let firstDrink = true;
      unsubDrink = selectedDrinkId.subscribe((drinkId) => {
        if (firstDrink) { firstDrink = false; return; }
        const city = $selectedCity;
        if (city) loadMarkers(city, drinkId, $selectedPriceTier);
        updateWms(drinkId);
        updateBasemapTint(drinkId);
      });

      let firstTier = true;
      unsubTier = selectedPriceTier.subscribe((tier) => {
        if (firstTier) { firstTier = false; return; }
        const city = $selectedCity;
        if (city) loadMarkers(city, $selectedDrinkId, tier);
      });

      let firstCity = true;
      unsubCity = selectedCity.subscribe((city) => {
        if (firstCity) { firstCity = false; return; }
        if (city) applyCity(city);
      });

      // Ein-/Ausloggen → Lokale ohne Eintrag ein-/ausblenden
      let firstLogin = true;
      unsubLogin = isLoggedIn.subscribe(() => {
        if (firstLogin) { firstLogin = false; return; }
        reloadMarkers();
      });
    });
    })();

    if (!localStorage.getItem('spritzmap_splash_seen') && !localStorage.getItem('token')) {
      splashOpen = true;
    }

    return () => {
      unsubDrink?.();
      unsubTier?.();
      unsubCity?.();
      unsubLogin?.();
    };
  });

  onDestroy(() => {
    map?.remove();
    if (watchId !== null) navigator.geolocation.clearWatch(watchId);
  });
</script>

<div bind:this={mapEl} class="map-container"></div>

<!-- City picker pills -->
{#if $cities.length > CITY_PILLS_MAX}
  <div class="city-picker">
    <button class="city-btn active" onclick={() => (cityMenuOpen = !cityMenuOpen)} aria-expanded={cityMenuOpen}>
      {$selectedCity?.name ?? 'Stadt wählen'} ▾
    </button>
    {#if cityMenuOpen}
      <div class="city-menu">
        <!-- svelte-ignore a11y_autofocus -->
        <input
          type="text"
          placeholder="Stadt suchen…"
          bind:value={citySearch}
          autofocus
          onkeydown={(e) => {
            if (e.key === 'Enter' && filteredCities[0]) chooseCity(filteredCities[0]);
            if (e.key === 'Escape') cityMenuOpen = false;
          }}
        />
        <ul>
          {#each filteredCities as city (city.id)}
            <li>
              <button class:current={$selectedCity?.id === city.id} onclick={() => chooseCity(city)}>
                {city.name}{#if city.state && city.state !== city.name}<small> {city.state}</small>{/if}
              </button>
            </li>
          {:else}
            <li class="none">Keine Stadt gefunden</li>
          {/each}
        </ul>
      </div>
    {/if}
  </div>
{:else if $cities.length > 1}
  <div class="city-picker">
    {#each $cities as city}
      <button
        class="city-btn"
        class:active={$selectedCity?.id === city.id}
        onclick={() => selectedCity.set(city)}
      >
        {city.name}
      </button>
    {/each}
  </div>
{/if}

<div class="zoom-btns">
  <button class="zoom-btn" title="Vergrößern" onclick={() => map?.zoomIn()}>+</button>
  <button class="zoom-btn" title="Verkleinern" onclick={() => map?.zoomOut()}>−</button>
</div>

<button class="locate-btn" title={$t.map.locate} onclick={locateUser}>
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
    <circle cx="9" cy="9" r="6.5" stroke="white" stroke-width="2"/>
    <circle cx="9" cy="9" r="2.5" fill="white"/>
  </svg>
</button>

<button
  class="help-btn"
  aria-label={$t.help.btn_aria}
  onclick={() => (helpOpen = true)}
>
  ?
</button>

<button
  class="splash-btn"
  aria-label={$t.splash.btn_aria}
  onclick={() => (splashOpen = true)}
>
  !
</button>

<MapLegend showUnpriced={$isLoggedIn} zoom={mapZoom} wmsMaxZoom={WMS_MAX_ZOOM} hasWms={$selectedCity?.has_areas ?? false} drinkColor={getDrinkColor($selectedDrinkId)} />

<HelpModal bind:open={helpOpen} />
<PhotoLightbox bind:open={lightboxOpen} bind:photos={lightboxPhotos} bind:index={lightboxIndex} cityId={$selectedCity?.id ?? null} />
<SplashModal bind:open={splashOpen} />

<PriceSubmitModal
  bind:open={submitOpen}
  locationId={submitLocationId}
  locationName={submitLocationName}
  isEmptyLocation={submitIsEmpty}
  locationCoords={submitCoords}
  onsubmitted={() => { const city = $selectedCity; if (city) loadMarkers(city, $selectedDrinkId, $selectedPriceTier); }}
/>

<style>
  .map-container {
    width: 100%;
    height: 100%;
  }

  .city-picker {
    position: absolute;
    top: 0.75rem;
    left: 50%;
    transform: translateX(-50%);
    z-index: 5;
    display: flex;
    gap: 6px;
  }

  .city-menu {
    position: absolute;
    top: calc(100% + 6px);
    left: 50%;
    transform: translateX(-50%);
    width: min(260px, 80vw);
    background: white;
    border-radius: 10px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
    padding: 8px;
  }
  .city-menu input {
    width: 100%;
    box-sizing: border-box;
    padding: 6px 10px;
    border: 1.5px solid #ddd;
    border-radius: 6px;
    font-size: 0.9rem;
  }
  .city-menu ul { list-style: none; margin: 6px 0 0; padding: 0; max-height: 50vh; overflow-y: auto; }
  .city-menu li button {
    width: 100%;
    text-align: left;
    padding: 6px 8px;
    background: none;
    border: none;
    border-radius: 6px;
    font-size: 0.9rem;
    cursor: pointer;
  }
  .city-menu li button:hover, .city-menu li button.current { background: #fff3ec; color: #b33c00; }
  .city-menu li small { color: #999; margin-left: 4px; }
  .city-menu .none { color: #999; font-size: 0.85rem; padding: 6px 8px; }

  .city-btn {
    padding: 5px 14px;
    border: 2px solid #e8500a;
    border-radius: 20px;
    background: white;
    color: #e8500a;
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s, color 0.15s;
    white-space: nowrap;
  }

  .city-btn.active,
  .city-btn:hover {
    background: #e8500a;
    color: white;
  }

  .locate-btn,
  .help-btn,
  .splash-btn {
    position: absolute;
    bottom: 1.5rem;
    z-index: 5;
    width: 34px;
    height: 34px;
    background: #e8500a;
    border: none;
    border-radius: 6px;
    line-height: 1;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 2px 8px rgba(232, 80, 10, 0.45);
    padding: 0;
    color: white;
  }

  .zoom-btns {
    position: absolute;
    bottom: calc(1.5rem + 34px + 8px);
    left: 0.65rem;
    z-index: 5;
    display: flex;
    flex-direction: column;
    border-radius: 6px;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(232, 80, 10, 0.45);
  }

  .zoom-btn {
    width: 34px;
    height: 34px;
    background: #e8500a;
    border: none;
    border-radius: 0;
    color: white;
    font-size: 1.25rem;
    font-weight: 400;
    line-height: 1;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
  }

  .zoom-btn:first-child {
    border-bottom: 1px solid rgba(255, 255, 255, 0.25);
  }

  .zoom-btn:hover { background: #d04508; }

  .locate-btn {
    left: 0.65rem;
    font-size: 1.1rem;
  }

  .help-btn {
    left: calc(0.65rem + 34px + 8px);
    font-size: 1rem;
    font-weight: 700;
  }

  .splash-btn {
    left: calc(0.65rem + 34px + 8px + 34px + 8px);
    font-size: 1rem;
    font-weight: 700;
  }

  @media (max-width: 640px) {
    .locate-btn,
    .help-btn,
    .splash-btn {
      bottom: calc(var(--filter-bar-h, 0px) + 1.5rem);
    }

    .zoom-btns {
      bottom: calc(var(--filter-bar-h, 0px) + 1.5rem + 34px + 8px);
    }

    /* MapLibre-Hinweise (Quellen, Impressum, Datenschutz) über der Filterleiste; aufgeklappt vor der Legende */
    .map-container :global(.maplibregl-ctrl-bottom-left),
    .map-container :global(.maplibregl-ctrl-bottom-right) {
      bottom: var(--filter-bar-h, 0px);
      z-index: 11;
    }
  }

  .locate-btn:hover,
  .help-btn:hover,
  .splash-btn:hover { background: #d04508; }

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

  :global(.popup-photos) {
    display: flex;
    gap: 4px;
    margin-top: 8px;
    overflow-x: auto;
  }

  :global(.popup-photo) {
    width: 56px;
    height: 56px;
    object-fit: cover;
    border-radius: 4px;
    cursor: zoom-in;
    flex-shrink: 0;
  }

  :global(.popup-confirm) {
    margin-top: 6px;
    padding: 4px 10px;
    background: white;
    color: #2e7d32;
    border: 1.5px solid #66bb6a;
    border-radius: 5px;
    font-size: 0.8rem;
    font-weight: 600;
    cursor: pointer;
    width: 100%;
  }

  :global(.popup-confirm.done) { background: #e8f5e9; }
  :global(.popup-confirm:disabled) { cursor: default; }

  :global(.popup-meta) {
    margin-top: 8px;
    font-size: 0.72rem;
    color: #bbb;
    text-align: right;
  }

  :global(.popup-type) {
    display: inline-block;
    margin-left: 4px;
    padding: 1px 6px;
    border-radius: 4px;
    background: #f3f3f3;
    color: #777;
    font-size: 0.68rem;
    font-weight: 500;
    vertical-align: middle;
  }

  :global(.popup-price) {
    font-size: 0.95rem;
  }

  :global(.popup-tier) {
    margin-left: 2px;
    padding: 0 6px;
    border-radius: 4px;
    background: #fff3ec;
    color: #b33c00;
    font-size: 0.75rem;
    font-weight: 600;
  }

  :global(.popup-facts) {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 8px;
  }

  :global(.popup-fact) {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 8px 3px 6px;
    border: 1px solid #eee;
    border-radius: 999px;
    color: #555;
    font-size: 0.75rem;
  }

  :global(.popup-fact svg) { color: #e8500a; }
  :global(.popup-fact-num) { font-weight: 700; color: #e8500a; }

  :global(.popup-note) {
    margin-top: 8px;
    padding-left: 8px;
    border-left: 3px solid #f1e6df;
    color: #666;
    font-size: 0.8rem;
    font-style: italic;
    overflow-wrap: anywhere;
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

  :global(.popup-intensity) {
    margin: 2px 0 8px;
  }

  :global(.popup-intensity-title) {
    font-size: 0.72rem;
    color: #999;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 5px;
  }

  :global(.popup-intensity-track) {
    position: relative;
    height: 4px;
    background: #e0e0e0;
    border-radius: 2px;
    margin: 0 6px;
  }

  :global(.popup-intensity-dot) {
    position: absolute;
    top: 50%;
    transform: translate(-50%, -50%);
    width: 12px;
    height: 12px;
    border-radius: 50%;
    border: 2px solid white;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.35);
  }

  :global(.popup-intensity-label) {
    text-align: center;
    font-size: 0.72rem;
    color: #888;
    margin-top: 5px;
    font-style: italic;
  }

  :global(.maplibregl-popup-close-button) {
    font-size: 1.2rem;
    padding: 0.25rem 0.5rem;
    color: #666;
  }
</style>
