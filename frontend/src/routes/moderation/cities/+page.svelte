<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { goto } from '$app/navigation';
  import { user } from '$lib/stores/auth';
  import { api } from '$lib/api/client';

  interface City {
    id: number;
    name: string;
    slug: string;
    state: string | null;
    osm_relation_id: number | null;
    has_boundary: boolean;
    is_active: boolean;
    osm_sync_enabled: boolean;
    area_source: 'osm' | 'upload' | 'none';
    area_admin_level: number | null;
    last_sync_at: string | null;
    last_sync_status: 'success' | 'failed' | null;
    last_sync_error: string | null;
    next_sync_at: string | null;
    sync_failures: number;
    area_count: number;
    location_count: number;
    priced_location_count: number;
  }
  interface SearchResult { osm_relation_id: number; name: string; state: string | null; type: string; display_name: string }
  interface LevelStat { admin_level: number; count: number; coverage: number; location_coverage?: number }
  interface SyncRun {
    id: number; started_at: string; finished_at: string | null; status: string; server: string | null;
    elements: number; created: number; updated: number; deactivated: number; error: string | null;
  }

  let cities = $state<City[]>([]);
  let loading = $state(true);
  let error = $state('');
  let notice = $state('');

  // ── Stadt hinzufügen ──────────────────────────────────────────────────────
  let query = $state('');
  let searching = $state(false);
  let results = $state<SearchResult[]>([]);
  let creatingId = $state<number | null>(null);

  // ── Detailbereich pro Stadt ───────────────────────────────────────────────
  let openId = $state<number | null>(null);
  let busy = $state('');
  let levels = $state<LevelStat[] | null>(null);
  let recommended = $state<number | null>(null);
  let chosenLevel = $state<number | null>(null);
  let runs = $state<SyncRun[]>([]);
  let uploadFile = $state<File | null>(null);
  let uploadProps = $state<string[]>([]);
  let keyProp = $state('');
  let nameProp = $state('');

  let refreshTimer: ReturnType<typeof setInterval> | undefined;

  onMount(async () => {
    if ($user?.role !== 'admin') {
      goto('/moderation/dashboard');
      return;
    }
    await loadCities();
    // Status (Sync/Gebietsimport im Hintergrund) regelmäßig aktualisieren
    refreshTimer = setInterval(() => loadCities(true), 15000);
  });
  onDestroy(() => clearInterval(refreshTimer));

  async function loadCities(silent = false) {
    if (!silent) loading = true;
    try {
      cities = await api.get<City[]>('/admin/cities');
      if (openId !== null) runs = await api.get<SyncRun[]>(`/admin/cities/${openId}/sync-runs`);
    } catch (e: any) {
      if (!silent) error = e.message;
    } finally {
      loading = false;
    }
  }

  function flash(msg: string) {
    notice = msg;
    setTimeout(() => { if (notice === msg) notice = ''; }, 5000);
  }

  async function run(label: string, fn: () => Promise<unknown>) {
    busy = label;
    error = '';
    try {
      await fn();
    } catch (e: any) {
      error = e.message;
    } finally {
      busy = '';
    }
  }

  async function search() {
    if (!query.trim()) return;
    searching = true;
    error = '';
    try {
      results = await api.get<SearchResult[]>(`/admin/cities/search?q=${encodeURIComponent(query.trim())}`);
    } catch (e: any) {
      error = e.message;
    } finally {
      searching = false;
    }
  }

  async function createCity(r: SearchResult) {
    creatingId = r.osm_relation_id;
    error = '';
    try {
      await api.post('/admin/cities', { osm_relation_id: r.osm_relation_id });
      results = [];
      query = '';
      flash(`${r.name} angelegt – Gebiete und Lokale werden im Hintergrund importiert.`);
      await loadCities();
    } catch (e: any) {
      error = e.message;
    } finally {
      creatingId = null;
    }
  }

  async function toggle(city: City, field: 'is_active' | 'osm_sync_enabled') {
    await run(field, async () => {
      await api.patch(`/admin/cities/${city.id}`, { [field]: !city[field] });
      await loadCities(true);
    });
  }

  async function openCity(city: City) {
    if (openId === city.id) { openId = null; return; }
    openId = city.id;
    levels = null;
    recommended = null;
    chosenLevel = city.area_admin_level;
    uploadFile = null;
    uploadProps = [];
    runs = await api.get<SyncRun[]>(`/admin/cities/${city.id}/sync-runs`).catch(() => []);
  }

  const syncNow = (city: City) => run('sync', async () => {
    const r = await api.post<{ detail: string }>(`/admin/cities/${city.id}/sync`, {});
    flash(r.detail);
  });

  const refreshBoundary = (city: City) => run('boundary', async () => {
    await api.post(`/admin/cities/${city.id}/boundary`, {});
    flash('Grenze aktualisiert');
    await loadCities(true);
  });

  const loadLevels = (city: City) => run('levels', async () => {
    const r = await api.get<{ levels: LevelStat[]; recommended: number | null }>(`/admin/cities/${city.id}/area-levels`);
    levels = r.levels;
    recommended = r.recommended;
    chosenLevel = chosenLevel ?? r.recommended;
  });

  const importOsmAreas = (city: City) => run('areas', async () => {
    if (city.area_source === 'upload' && !confirm('Hochgeladene Gebiete durch OSM-Gebiete ersetzen?')) return;
    const r = await api.post<{ skipped: boolean; reason?: string; count?: number; admin_level?: number }>(
      `/admin/cities/${city.id}/areas/osm`,
      { admin_level: chosenLevel, replace_upload: city.area_source === 'upload' },
    );
    flash(r.skipped ? `Nicht importiert: ${r.reason}` : `${r.count} Gebiete (Ebene ${r.admin_level}) importiert`);
    await loadCities(true);
  });

  async function onFileChosen(e: Event) {
    const file = (e.currentTarget as HTMLInputElement).files?.[0] ?? null;
    uploadFile = file;
    uploadProps = [];
    keyProp = nameProp = '';
    if (!file) return;
    try {
      // Eigenschaften des ersten Features für die Feldauswahl vorschlagen
      const json = JSON.parse(await file.text());
      uploadProps = Object.keys(json?.features?.[0]?.properties ?? {});
      keyProp = uploadProps.find((p) => /schl|key|id|nr/i.test(p)) ?? uploadProps[0] ?? '';
      nameProp = uploadProps.find((p) => /name|bez/i.test(p)) ?? uploadProps[0] ?? '';
    } catch {
      error = 'Datei ist kein gültiges GeoJSON';
      uploadFile = null;
    }
  }

  const uploadAreas = (city: City) => run('upload', async () => {
    if (!uploadFile) return;
    const form = new FormData();
    form.append('file', uploadFile);
    form.append('key_prop', keyProp);
    form.append('name_prop', nameProp);
    const r = await api.upload<{ count: number }>(`/admin/cities/${city.id}/areas/upload`, form);
    flash(`${r.count} Gebiete hochgeladen`);
    uploadFile = null;
    uploadProps = [];
    await loadCities(true);
  });

  function fmt(iso: string | null) {
    return iso ? new Date(iso).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' }) : '—';
  }

  const AREA_SOURCE_LABEL = { osm: 'OSM', upload: 'Upload', none: 'keine' } as const;
</script>

<div class="cities-page">
  <div class="page-header">
    <h1>Städte</h1>
  </div>

  {#if error}<div class="alert alert-error">{error}</div>{/if}
  {#if notice}<div class="alert alert-info">{notice}</div>{/if}

  <!-- Stadt hinzufügen -->
  <div class="add-card">
    <form class="search-row" onsubmit={(e) => { e.preventDefault(); search(); }}>
      <input type="text" bind:value={query} placeholder="Stadt suchen, z. B. Hamburg" />
      <button class="btn-primary" type="submit" disabled={searching || !query.trim()}>
        {searching ? 'Suche…' : 'Suchen'}
      </button>
    </form>
    {#if results.length}
      <ul class="results">
        {#each results as r (r.osm_relation_id)}
          {@const exists = cities.some((c) => c.osm_relation_id === r.osm_relation_id)}
          <li>
            <span><strong>{r.name}</strong> <small>{r.state ?? ''} · {r.type}</small></span>
            {#if exists}
              <span class="muted">bereits angelegt</span>
            {:else}
              <button class="btn-secondary" disabled={creatingId !== null} onclick={() => createCity(r)}>
                {creatingId === r.osm_relation_id ? 'Lege an…' : 'Anlegen'}
              </button>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
    <p class="hint">Grenze, Stadtteile und alle Lokale werden automatisch aus OpenStreetMap übernommen. Der OSM-Abgleich läuft danach gestaffelt einmal täglich.</p>
  </div>

  {#if loading}
    <p class="loading">Lade…</p>
  {:else}
    <div class="cities-grid">
      {#each cities as city (city.id)}
        <div class="city-card" class:inactive={!city.is_active}>
          <div class="city-header">
            <div>
              <strong>{city.name}</strong>
              {#if city.state && city.state !== city.name}<span class="slug">{city.state}</span>{/if}
            </div>
            <span class="badge" class:badge-active={city.is_active} class:badge-inactive={!city.is_active}>
              {city.is_active ? 'aktiv' : 'inaktiv'}
            </span>
          </div>

          <div class="city-meta">
            <div><span class="label">Lokale:</span> {city.location_count.toLocaleString('de-DE')} · davon mit Preis {city.priced_location_count}</div>
            <div>
              <span class="label">Gebiete:</span>
              {city.area_count} ({AREA_SOURCE_LABEL[city.area_source]}{city.area_admin_level ? `, Ebene ${city.area_admin_level}` : ''})
              {#if !city.area_count}<span class="warn">– keine Zusammenfassung auf der Karte</span>{/if}
            </div>
            <div>
              <span class="label">OSM-Sync:</span>
              {#if !city.osm_sync_enabled}
                <span class="muted">deaktiviert</span>
              {:else if city.last_sync_status === 'failed'}
                <span class="sync-failed" title={city.last_sync_error ?? ''}>fehlgeschlagen ({city.sync_failures}×)</span>
              {:else if city.last_sync_status === 'success'}
                <span class="sync-ok">ok</span> {fmt(city.last_sync_at)}
              {:else}
                <span class="muted">ausstehend</span>
              {/if}
              {#if city.osm_sync_enabled}<small class="muted"> · nächster {fmt(city.next_sync_at)}</small>{/if}
            </div>
            {#if !city.has_boundary}
              <div class="warn">Keine Stadtgrenze – Import über Bbox, Stadtteile nicht verfügbar</div>
            {/if}
          </div>

          <div class="city-actions">
            <button class="btn-outline" onclick={() => openCity(city)}>{openId === city.id ? 'Schließen' : 'Verwalten'}</button>
            <button class="btn-outline" onclick={() => toggle(city, 'is_active')}>{city.is_active ? 'Deaktivieren' : 'Aktivieren'}</button>
            <button class="btn-outline" onclick={() => toggle(city, 'osm_sync_enabled')}>{city.osm_sync_enabled ? 'Sync aus' : 'Sync an'}</button>
          </div>

          {#if openId === city.id}
            <div class="details">
              <section>
                <h3>OpenStreetMap</h3>
                <div class="row">
                  <button class="btn-secondary" disabled={!!busy} onclick={() => syncNow(city)}>{busy === 'sync' ? '…' : 'Jetzt synchronisieren'}</button>
                  <button class="btn-outline" disabled={!!busy || !city.osm_relation_id} onclick={() => refreshBoundary(city)}>{busy === 'boundary' ? '…' : 'Grenze aktualisieren'}</button>
                </div>
                {#if runs.length}
                  <table class="runs">
                    <thead><tr><th>Start</th><th>Status</th><th>Neu</th><th>Aktual.</th><th>Deakt.</th></tr></thead>
                    <tbody>
                      {#each runs as r (r.id)}
                        <tr title={r.error ?? r.server ?? ''}>
                          <td>{fmt(r.started_at)}</td>
                          <td class:sync-ok={r.status === 'success'} class:sync-failed={r.status === 'failed'}>{r.status}</td>
                          <td>{r.created}</td><td>{r.updated}</td><td>{r.deactivated}</td>
                        </tr>
                      {/each}
                    </tbody>
                  </table>
                {/if}
              </section>

              <section>
                <h3>Gebiete aus OSM</h3>
                <div class="row">
                  <button class="btn-outline" disabled={!!busy || !city.has_boundary} onclick={() => loadLevels(city)}>{busy === 'levels' ? 'Lade…' : 'Ebenen anzeigen'}</button>
                </div>
                {#if levels}
                  {#if levels.length}
                    {#each levels as l (l.admin_level)}
                      <label class="level">
                        <input type="radio" name="level-{city.id}" value={l.admin_level} bind:group={chosenLevel} />
                        Ebene {l.admin_level}: {l.count} Gebiete
                        {#if l.location_coverage != null}· {Math.round(l.location_coverage * 100)} % der Lokale{/if}
                        · {Math.round(l.coverage * 100)} % der Fläche
                        {#if l.admin_level === recommended}<span class="rec">empfohlen</span>{/if}
                      </label>
                    {/each}
                    <button class="btn-secondary" disabled={!!busy || chosenLevel === null} onclick={() => importOsmAreas(city)}>
                      {busy === 'areas' ? 'Importiere…' : 'Übernehmen'}
                    </button>
                    <p class="hint">Nicht abgedeckte Teile der Stadt werden automatisch zu „übriges Stadtgebiet“ zusammengefasst.</p>
                  {:else}
                    <p class="muted">OSM hat für diese Stadt keine Stadtteile (Ebene 9/10). Gebiete bitte hochladen.</p>
                  {/if}
                {/if}
              </section>

              <section>
                <h3>Offizielle Gebiete hochladen</h3>
                <p class="hint">GeoJSON-FeatureCollection in WGS84 (EPSG:4326). Ersetzt alle Gebiete der Stadt und hat Vorrang vor OSM.</p>
                <input type="file" accept=".geojson,.json,application/geo+json,application/json" onchange={onFileChosen} />
                {#if uploadProps.length}
                  <div class="row">
                    <label>Schlüssel <select bind:value={keyProp}>{#each uploadProps as p}<option>{p}</option>{/each}</select></label>
                    <label>Name <select bind:value={nameProp}>{#each uploadProps as p}<option>{p}</option>{/each}</select></label>
                    <button class="btn-secondary" disabled={!!busy} onclick={() => uploadAreas(city)}>{busy === 'upload' ? 'Lade hoch…' : 'Hochladen'}</button>
                  </div>
                {/if}
              </section>
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .cities-page { max-width: 960px; }

  .page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1.5rem;
  }
  .page-header h1 { font-size: 1.5rem; font-weight: 700; margin: 0; color: #1a1a2e; }

  .alert { padding: 0.75rem 1rem; border-radius: 8px; margin-bottom: 1rem; font-size: 0.875rem; }
  .alert-error { background: #fee2e2; color: #b91c1c; }
  .alert-info  { background: #dbeafe; color: #1d4ed8; }
  .loading { color: #888; padding: 2rem 0; text-align: center; }

  .add-card {
    background: white;
    border-radius: 12px;
    padding: 1.25rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    margin-bottom: 1.5rem;
  }
  .search-row { display: flex; gap: 8px; }
  .search-row input {
    flex: 1;
    padding: 0.5rem 0.75rem;
    border: 1px solid #ddd;
    border-radius: 8px;
    font-size: 0.9rem;
  }
  .results { list-style: none; margin: 0.75rem 0 0; padding: 0; }
  .results li {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    padding: 6px 0;
    border-top: 1px solid #f0f0f0;
    font-size: 0.9rem;
  }
  .results small { color: #888; }
  .hint { font-size: 0.78rem; color: #888; margin: 0.5rem 0 0; }

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
  .city-card.inactive { opacity: 0.6; }
  .city-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1rem; }
  .city-header strong { font-size: 1rem; color: #1a1a2e; }
  .slug { font-size: 0.78rem; color: #888; margin-left: 4px; }

  .badge { font-size: 0.7rem; font-weight: 700; padding: 2px 8px; border-radius: 12px; text-transform: uppercase; white-space: nowrap; }
  .badge-active   { background: #dcfce7; color: #166534; }
  .badge-inactive { background: #f1f5f9; color: #64748b; }

  .city-meta { display: flex; flex-direction: column; gap: 4px; font-size: 0.8rem; color: #555; margin-bottom: 1rem; }
  .city-meta .label { font-weight: 600; color: #333; margin-right: 4px; }
  .muted { color: #999; }
  .warn { color: #b26a00; }
  .sync-ok { color: #166534; font-weight: 600; }
  .sync-failed { color: #b91c1c; font-weight: 600; cursor: help; }

  .city-actions, .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }

  .details { margin-top: 1rem; border-top: 1px solid #eee; padding-top: 0.75rem; display: flex; flex-direction: column; gap: 1rem; }
  .details h3 { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.04em; color: #888; margin: 0 0 6px; }
  .details label { font-size: 0.8rem; display: flex; align-items: center; gap: 4px; }
  .level { margin: 4px 0; }
  .rec { background: #dcfce7; color: #166534; font-size: 0.68rem; font-weight: 700; padding: 1px 6px; border-radius: 8px; }

  .runs { width: 100%; border-collapse: collapse; font-size: 0.75rem; margin-top: 8px; }
  .runs th, .runs td { text-align: left; padding: 3px 4px; border-bottom: 1px solid #f3f3f3; }
  .runs th { color: #999; font-weight: 600; }

  .btn-primary {
    padding: 0.5rem 1.1rem;
    background: #e8500a;
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 600;
    cursor: pointer;
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
  }
  .btn-outline:hover:not(:disabled) { border-color: #999; color: #333; }
  .btn-outline:disabled { opacity: 0.5; cursor: not-allowed; }

  @media (max-width: 640px) {
    .cities-grid { grid-template-columns: 1fr; }
  }
</style>
