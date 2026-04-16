<script lang="ts">
  import { onMount } from 'svelte';
  import { authStore } from '$lib/stores/auth';

  const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

  interface City {
    id: number;
    name: string;
    slug: string;
    bbox: string;
    center_lat: number;
    center_lon: number;
    default_zoom: number;
    is_active: boolean;
    osm_sync_enabled: boolean;
    wms_layer: string | null;
  }

  let cities = $state<City[]>([]);
  let loading = $state(true);
  let error = $state('');
  let syncingId = $state<number | null>(null);
  let syncMsg = $state('');

  let showForm = $state(false);
  let saving = $state(false);
  let formError = $state('');

  let form = $state({
    name: '',
    slug: '',
    bbox: '',
    center_lat: '',
    center_lon: '',
    default_zoom: '12',
    osm_sync_enabled: true,
    wms_layer: '',
  });

  function headers() {
    return {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${$authStore.token}`,
    };
  }

  async function loadCities() {
    loading = true;
    error = '';
    try {
      const res = await fetch(`${API_URL}/admin/cities`, { headers: headers() });
      if (!res.ok) throw new Error(await res.text());
      cities = await res.json();
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  async function triggerSync(id: number, name: string) {
    syncingId = id;
    syncMsg = '';
    try {
      const res = await fetch(`${API_URL}/admin/cities/${id}/sync`, {
        method: 'POST',
        headers: headers(),
      });
      const data = await res.json();
      syncMsg = data.detail ?? 'Sync gestartet';
    } catch (e: any) {
      syncMsg = 'Fehler: ' + e.message;
    } finally {
      syncingId = null;
    }
  }

  async function toggleActive(city: City) {
    await fetch(`${API_URL}/admin/cities/${city.id}`, {
      method: 'PATCH',
      headers: headers(),
      body: JSON.stringify({ is_active: !city.is_active }),
    });
    await loadCities();
  }

  async function saveCity() {
    saving = true;
    formError = '';
    try {
      const body = {
        name: form.name.trim(),
        slug: form.slug.trim(),
        bbox: form.bbox.trim(),
        center_lat: parseFloat(form.center_lat),
        center_lon: parseFloat(form.center_lon),
        default_zoom: parseInt(form.default_zoom),
        osm_sync_enabled: form.osm_sync_enabled,
        wms_layer: form.wms_layer.trim() || null,
      };
      const res = await fetch(`${API_URL}/admin/cities`, {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail ?? 'Fehler');
      }
      showForm = false;
      form = { name: '', slug: '', bbox: '', center_lat: '', center_lon: '', default_zoom: '12', osm_sync_enabled: true, wms_layer: '' };
      await loadCities();
    } catch (e: any) {
      formError = e.message;
    } finally {
      saving = false;
    }
  }

  onMount(loadCities);
</script>

<div class="cities-page">
  <div class="page-header">
    <h1>Städte verwalten</h1>
    <button class="btn-primary" onclick={() => (showForm = !showForm)}>
      {showForm ? 'Abbrechen' : '+ Neue Stadt'}
    </button>
  </div>

  {#if error}
    <div class="alert alert-error">{error}</div>
  {/if}

  {#if syncMsg}
    <div class="alert alert-info">{syncMsg}</div>
  {/if}

  {#if showForm}
    <div class="form-card">
      <h2>Neue Stadt anlegen</h2>
      {#if formError}
        <div class="alert alert-error">{formError}</div>
      {/if}
      <div class="form-grid">
        <label>
          Name
          <input type="text" bind:value={form.name} placeholder="Berlin" />
        </label>
        <label>
          Slug
          <input type="text" bind:value={form.slug} placeholder="berlin" />
        </label>
        <label class="full">
          Bbox (min_lat,min_lon,max_lat,max_lon)
          <input type="text" bind:value={form.bbox} placeholder="52.3382,13.0883,52.6755,13.7611" />
          <small>Tipp: bbox auf <a href="https://boundingbox.klokantech.com/" target="_blank" rel="noopener">boundingbox.klokantech.com</a> ermitteln</small>
        </label>
        <label>
          Zentrum Breitengrad
          <input type="number" step="0.0001" bind:value={form.center_lat} placeholder="52.52" />
        </label>
        <label>
          Zentrum Längengrad
          <input type="number" step="0.0001" bind:value={form.center_lon} placeholder="13.405" />
        </label>
        <label>
          Standard-Zoom
          <input type="number" min="8" max="18" bind:value={form.default_zoom} />
        </label>
        <label class="full">
          WMS-Layer (optional, leer lassen wenn kein GeoServer-Layer)
          <input type="text" bind:value={form.wms_layer} placeholder="spritzmap:lor_index" />
        </label>
        <label class="checkbox-label">
          <input type="checkbox" bind:checked={form.osm_sync_enabled} />
          OSM-Sync aktiviert
        </label>
      </div>
      <div class="form-actions">
        <button class="btn-primary" disabled={saving} onclick={saveCity}>
          {saving ? 'Speichern…' : 'Stadt anlegen'}
        </button>
      </div>
    </div>
  {/if}

  {#if loading}
    <div class="loading">Laden…</div>
  {:else}
    <div class="cities-grid">
      {#each cities as city}
        <div class="city-card" class:inactive={!city.is_active}>
          <div class="city-header">
            <div>
              <strong>{city.name}</strong>
              <span class="slug">/{city.slug}</span>
            </div>
            <span class="badge" class:badge-active={city.is_active} class:badge-inactive={!city.is_active}>
              {city.is_active ? 'Aktiv' : 'Inaktiv'}
            </span>
          </div>

          <div class="city-meta">
            <div><span class="label">Bbox:</span> <code>{city.bbox}</code></div>
            <div><span class="label">Zentrum:</span> {city.center_lat.toFixed(4)}, {city.center_lon.toFixed(4)}</div>
            <div><span class="label">Zoom:</span> {city.default_zoom}</div>
            <div><span class="label">WMS:</span> {city.wms_layer ?? '—'}</div>
            <div><span class="label">OSM-Sync:</span> {city.osm_sync_enabled ? 'Ja' : 'Nein'}</div>
          </div>

          <div class="city-actions">
            <button
              class="btn-secondary"
              disabled={syncingId === city.id}
              onclick={() => triggerSync(city.id, city.name)}
            >
              {syncingId === city.id ? 'Syncing…' : 'OSM-Sync starten'}
            </button>
            <button
              class="btn-outline"
              onclick={() => toggleActive(city)}
            >
              {city.is_active ? 'Deaktivieren' : 'Aktivieren'}
            </button>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .cities-page {
    max-width: 900px;
  }

  .page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1.5rem;
  }

  .page-header h1 {
    font-size: 1.5rem;
    font-weight: 700;
    margin: 0;
    color: #1a1a2e;
  }

  .alert {
    padding: 0.75rem 1rem;
    border-radius: 8px;
    margin-bottom: 1rem;
    font-size: 0.875rem;
  }

  .alert-error { background: #fee2e2; color: #b91c1c; }
  .alert-info  { background: #dbeafe; color: #1d4ed8; }

  .loading {
    color: #888;
    padding: 2rem 0;
    text-align: center;
  }

  .form-card {
    background: white;
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
  }

  .form-card h2 {
    font-size: 1.1rem;
    margin: 0 0 1rem;
    color: #1a1a2e;
  }

  .form-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
  }

  .form-grid label {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 0.8rem;
    font-weight: 600;
    color: #555;
  }

  .form-grid label.full {
    grid-column: 1 / -1;
  }

  .form-grid input[type="text"],
  .form-grid input[type="number"] {
    padding: 0.5rem 0.75rem;
    border: 1px solid #ddd;
    border-radius: 6px;
    font-size: 0.875rem;
    font-family: inherit;
  }

  .form-grid small {
    font-size: 0.75rem;
    color: #888;
    font-weight: 400;
  }

  .form-grid small a {
    color: #e8500a;
  }

  .checkbox-label {
    flex-direction: row !important;
    align-items: center;
    gap: 0.5rem !important;
    font-size: 0.875rem !important;
  }

  .form-actions {
    margin-top: 1.25rem;
  }

  .cities-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
    gap: 1rem;
  }

  .city-card {
    background: white;
    border-radius: 12px;
    padding: 1.25rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
  }

  .city-card.inactive {
    opacity: 0.6;
  }

  .city-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 1rem;
  }

  .city-header strong {
    font-size: 1rem;
    color: #1a1a2e;
  }

  .slug {
    font-size: 0.78rem;
    color: #888;
    margin-left: 4px;
  }

  .badge {
    font-size: 0.7rem;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 12px;
    text-transform: uppercase;
  }

  .badge-active   { background: #dcfce7; color: #166534; }
  .badge-inactive { background: #f1f5f9; color: #64748b; }

  .city-meta {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 0.8rem;
    color: #555;
    margin-bottom: 1rem;
  }

  .city-meta .label {
    font-weight: 600;
    color: #333;
    margin-right: 4px;
  }

  .city-meta code {
    font-family: monospace;
    font-size: 0.75rem;
    background: #f5f5f5;
    padding: 1px 4px;
    border-radius: 3px;
  }

  .city-actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .btn-primary {
    padding: 0.5rem 1.1rem;
    background: #e8500a;
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s;
  }
  .btn-primary:hover:not(:disabled) { background: #d04508; }
  .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

  .btn-secondary {
    padding: 0.45rem 1rem;
    background: #1a1a2e;
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 0.8rem;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s;
  }
  .btn-secondary:hover:not(:disabled) { background: #2d2d4a; }
  .btn-secondary:disabled { opacity: 0.5; cursor: not-allowed; }

  .btn-outline {
    padding: 0.45rem 1rem;
    background: transparent;
    color: #555;
    border: 1px solid #ddd;
    border-radius: 8px;
    font-size: 0.8rem;
    font-weight: 600;
    cursor: pointer;
    transition: border-color 0.15s, color 0.15s;
  }
  .btn-outline:hover { border-color: #999; color: #333; }
</style>
