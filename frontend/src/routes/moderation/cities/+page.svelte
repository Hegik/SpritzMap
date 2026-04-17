<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { user } from '$lib/stores/auth';
  import { api } from '$lib/api/client';

  const GEOSERVER_URL = import.meta.env.VITE_GEOSERVER_URL ?? 'http://localhost:8080/geoserver';

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

  // ── Wizard state ──────────────────────────────────────────────────────────
  let showWizard = $state(false);
  let wizardStep = $state(1);
  let saving = $state(false);
  let formError = $state('');
  let newCityId = $state<number | null>(null);

  let form = $state({
    name: '',
    slug: '',
    bbox: '',
    center_lat: '',
    center_lon: '',
    default_zoom: '12',
    wms_layer: 'spritzmap:lor_index_berlin',
  });

  // Pre-escaped SQL snippet for step 2 (avoids Svelte template brace conflicts)
  const lorSqlSnippet = () => `-- Beispiel: Bezirk einfügen (für jedes Gebiet wiederholen)
INSERT INTO public.lor (lor_schluessel, pr_name, geom, city_id)
VALUES (
  '010101',          -- eindeutiger Schlüssel
  'Altona-Altstadt', -- Bezirksname
  ST_GeomFromGeoJSON('{"type":"Polygon","coordinates":[...]}'),
  ${newCityId ?? 'CITY_ID'}  -- ID der neu angelegten Stadt
);`;

  const geoserverSqlSnippet = () => `WITH lor_stats AS (
  SELECT
    l.lor_schluessel,
    l.geom,
    AVG(pe.price)        AS avg_price,
    AVG(pe.color_value)  AS avg_color_value,
    COUNT(pe.id)         AS entry_count
  FROM lor l
  LEFT JOIN locations loc
    ON ST_Within(loc.geom, ST_Transform(l.geom, 4326))
  LEFT JOIN price_entries pe
    ON pe.location_id = loc.id
    AND pe.is_current   = TRUE
    AND pe.unavailable  = FALSE
    AND pe.drink_id     = %drink_id%
  WHERE l.city_id = (SELECT id FROM cities WHERE slug = '${form.slug || 'CITY_SLUG'}')
  GROUP BY l.lor_schluessel, l.geom
),
global_stats AS (
  SELECT
    MAX(avg_price) AS max_price,
    MIN(avg_price) AS min_price
  FROM lor_stats
  WHERE avg_price IS NOT NULL
),
drink_meta AS (
  SELECT color_hex
  FROM drinks
  WHERE id = %drink_id%
)
SELECT
  s.lor_schluessel,
  s.geom,
  s.avg_price,
  s.entry_count,
  dm.color_hex AS drink_color,
  CASE
    WHEN s.avg_price IS NULL OR g.max_price IS NULL OR g.min_price <= 0
    THEN NULL
    WHEN g.max_price = g.min_price
    THEN 50.0 * (COALESCE(s.avg_color_value, 128) / 128.0)
    ELSE LEAST(100.0, GREATEST(0.0,
      (LN(g.max_price / s.avg_price) / LN(g.max_price / g.min_price))
      * (COALESCE(s.avg_color_value, 128) / 128.0)
      * 100.0
    ))
  END AS spritz_index
FROM lor_stats s
CROSS JOIN global_stats g
CROSS JOIN drink_meta dm`;

  let copied = $state(false);
  function copyGeoserverSql() {
    navigator.clipboard.writeText(geoserverSqlSnippet());
    copied = true;
    setTimeout(() => { copied = false; }, 2000);
  }

  // Auto-generate slug and wms_layer from name
  function onNameInput() {
    form.slug = form.name.toLowerCase()
      .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
      .replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    form.wms_layer = `spritzmap:lor_index_${form.slug}`;
  }

  async function loadCities() {
    loading = true;
    error = '';
    try {
      cities = await api.get<City[]>('/admin/cities');
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  async function triggerSync(id: number) {
    syncingId = id;
    syncMsg = '';
    try {
      const data = await api.post<{ detail: string }>(`/admin/cities/${id}/sync`, {});
      syncMsg = data.detail ?? 'Sync gestartet';
      setTimeout(() => { syncMsg = ''; }, 4000);
    } catch (e: any) {
      syncMsg = 'Fehler: ' + e.message;
    } finally {
      syncingId = null;
    }
  }

  async function toggleActive(city: City) {
    await api.patch(`/admin/cities/${city.id}`, { is_active: !city.is_active });
    await loadCities();
  }

  // Step 1: Create the city record
  async function saveStep1() {
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
        osm_sync_enabled: true,
        wms_layer: null, // set in step 4
      };
      if (!body.name || !body.slug || !body.bbox || isNaN(body.center_lat) || isNaN(body.center_lon)) {
        throw new Error('Bitte alle Pflichtfelder ausfüllen.');
      }
      const data = await api.post<{ id: number; slug: string }>('/admin/cities', body);
      newCityId = data.id;
      wizardStep = 2;
    } catch (e: any) {
      formError = e.message;
    } finally {
      saving = false;
    }
  }

  // Step 4: Set wms_layer and finish
  async function saveStep4() {
    saving = true;
    formError = '';
    try {
      await api.patch(`/admin/cities/${newCityId}`, { wms_layer: form.wms_layer.trim() || null });
      await loadCities();
      showWizard = false;
      wizardStep = 1;
      form = { name: '', slug: '', bbox: '', center_lat: '', center_lon: '', default_zoom: '12', wms_layer: 'spritzmap:lor_index_berlin' };
      newCityId = null;
    } catch (e: any) {
      formError = e.message;
    } finally {
      saving = false;
    }
  }

  function startOsmSync() {
    if (newCityId) triggerSync(newCityId);
    wizardStep = 4;
  }

  onMount(async () => {
    if ($user?.role !== 'admin') {
      goto('/moderation/dashboard');
      return;
    }
    await loadCities();
  });
</script>

<div class="cities-page">
  <div class="page-header">
    <h1>Städte verwalten</h1>
    {#if !showWizard}
      <button class="btn-primary" onclick={() => { showWizard = true; wizardStep = 1; formError = ''; }}>
        + Neue Stadt anlegen
      </button>
    {/if}
  </div>

  {#if error}
    <div class="alert alert-error">{error}</div>
  {/if}

  {#if syncMsg}
    <div class="alert alert-info">{syncMsg}</div>
  {/if}

  <!-- ── Wizard ────────────────────────────────────────────────────────────── -->
  {#if showWizard}
    <div class="wizard">
      <!-- Progress bar -->
      <div class="wizard-progress">
        {#each [1,2,3,4] as s}
          <div class="progress-step" class:done={wizardStep > s} class:active={wizardStep === s}>
            <div class="step-dot">{wizardStep > s ? '✓' : s}</div>
            <div class="step-label">
              {s === 1 ? 'Grunddaten' : s === 2 ? 'LOR importieren' : s === 3 ? 'OSM-Sync' : 'GeoServer'}
            </div>
          </div>
          {#if s < 4}<div class="progress-line" class:done={wizardStep > s}></div>{/if}
        {/each}
      </div>

      {#if formError}
        <div class="alert alert-error">{formError}</div>
      {/if}

      <!-- Step 1: Basic data -->
      {#if wizardStep === 1}
        <div class="wizard-card">
          <h2>Schritt 1 — Grunddaten</h2>

          <div class="info-box">
            <strong>Bbox ermitteln:</strong> Gehe auf
            <a href="https://boundingbox.klokantech.com/" target="_blank" rel="noopener">boundingbox.klokantech.com</a>,
            wähle die Stadt aus und kopiere das Ergebnis im Format <code>CSV</code>
            (Reihenfolge: <code>min_lon, min_lat, max_lon, max_lat</code> → umstellen auf
            <code>min_lat, min_lon, max_lat, max_lon</code>).
          </div>

          <div class="form-grid">
            <label>
              Stadtname *
              <input type="text" bind:value={form.name} oninput={onNameInput} placeholder="Hamburg" />
            </label>
            <label>
              Slug (URL-Name) *
              <input type="text" bind:value={form.slug} placeholder="hamburg" />
              <small>Kleinbuchstaben, Bindestriche — wird auto-generiert</small>
            </label>
            <label class="full">
              Bbox * <small>(min_lat, min_lon, max_lat, max_lon)</small>
              <input type="text" bind:value={form.bbox} placeholder="53.3951,9.7319,53.9644,10.3252" />
            </label>
            <label>
              Zentrum Breitengrad *
              <input type="number" step="0.0001" bind:value={form.center_lat} placeholder="53.55" />
            </label>
            <label>
              Zentrum Längengrad *
              <input type="number" step="0.0001" bind:value={form.center_lon} placeholder="10.0" />
            </label>
            <label>
              Standard-Zoom
              <input type="number" min="8" max="18" bind:value={form.default_zoom} />
              <small>12 ist ein guter Startwert für Großstädte</small>
            </label>
          </div>

          <div class="wizard-actions">
            <button class="btn-outline" onclick={() => { showWizard = false; formError = ''; }}>Abbrechen</button>
            <button class="btn-primary" disabled={saving} onclick={saveStep1}>
              {saving ? 'Speichern…' : 'Stadt anlegen & weiter →'}
            </button>
          </div>
        </div>

      <!-- Step 2: Import LOR districts -->
      {:else if wizardStep === 2}
        <div class="wizard-card">
          <h2>Schritt 2 — Bezirksgrenzen (LOR) in die Datenbank importieren</h2>

          <div class="info-box info-important">
            <strong>Pflichtschritt:</strong> Ohne Bezirksgrenzen funktioniert die Heatmap-Darstellung nicht.
            Die Daten müssen einmalig als Superuser in die <code>public.lor</code>-Tabelle eingespielt werden.
          </div>

          <div class="steps-list">
            <div class="step-item">
              <div class="step-num">1</div>
              <div>
                <strong>Bezirksdaten beschaffen</strong><br>
                Lade die Stadtteil-/Bezirksgrenzen als GeoJSON oder Shapefile herunter.
                Gute Quellen:
                <ul>
                  <li><a href="https://overpass-turbo.eu/" target="_blank" rel="noopener">Overpass Turbo</a> (Query: <code>relation["boundary"="administrative"]["admin_level"="9"]["name"="{form.name || 'Stadtname'}"]</code>)</li>
                  <li>Statistikamt / Open-Data-Portal der Stadt</li>
                  <li><a href="https://www.openstreetmap.org/" target="_blank" rel="noopener">OpenStreetMap</a> → Gebietsexport</li>
                </ul>
              </div>
            </div>

            <div class="step-item">
              <div class="step-num">2</div>
              <div>
                <strong>SQL in Coolify-DB-Konsole ausführen</strong><br>
                Öffne im Coolify-Dashboard die PostgreSQL-Konsole und führe aus:
                <pre class="code-block">{lorSqlSnippet()}</pre>
                <small>Alternativ: <code>ogr2ogr</code> für Massenimport aus Shapefile/GeoJSON</small>
              </div>
            </div>

            <div class="step-item">
              <div class="step-num">3</div>
              <div>
                <strong>Koordinatensystem prüfen</strong><br>
                Die gespeicherte Geometrie kann in beliebigem CRS vorliegen — die Queries verwenden
                <code>ST_SRID(l.geom)</code> dynamisch.
                Empfohlen: EPSG:4326 (WGS84, Standard bei GeoJSON) oder EPSG:25832 (UTM Zone 32N, für Hamburg/Westdeutschland).
              </div>
            </div>
          </div>

          <div class="wizard-actions">
            <button class="btn-outline" onclick={() => { wizardStep = 1; }}>← Zurück</button>
            <button class="btn-primary" onclick={() => { wizardStep = 3; }}>
              LOR importiert — weiter →
            </button>
          </div>
        </div>

      <!-- Step 3: OSM Sync -->
      {:else if wizardStep === 3}
        <div class="wizard-card">
          <h2>Schritt 3 — Bars & Restaurants aus OpenStreetMap importieren</h2>

          <div class="info-box">
            Der OSM-Sync lädt automatisch alle Bars, Restaurants, Cafés und Biergärten
            aus dem angegebenen Bbox-Bereich. Das kann bei großen Städten
            1–2 Minuten dauern.
          </div>

          <div class="steps-list">
            <div class="step-item">
              <div class="step-num">1</div>
              <div>
                <strong>Sync jetzt starten</strong><br>
                Klicke auf den Button — der Import läuft im Hintergrund.
                Du kannst die Seite danach normal weiternutzen.
              </div>
            </div>
            <div class="step-item">
              <div class="step-num">2</div>
              <div>
                <strong>Ergebnis prüfen</strong><br>
                Nach dem Sync erscheinen die Locations auf der Karte (Stadtauswahl erforderlich, falls noch nicht vorhanden).
                Der automatische Sync läuft danach täglich.
              </div>
            </div>
          </div>

          <div class="wizard-actions">
            <button class="btn-outline" onclick={() => { wizardStep = 2; }}>← Zurück</button>
            <button class="btn-primary" onclick={startOsmSync} disabled={syncingId === newCityId}>
              {syncingId === newCityId ? 'Sync läuft…' : 'OSM-Sync starten & weiter →'}
            </button>
          </div>
        </div>

      <!-- Step 4: GeoServer -->
      {:else if wizardStep === 4}
        <div class="wizard-card">
          <h2>Schritt 4 — GeoServer-Layer einrichten</h2>

          <div class="info-box">
            Jede Stadt bekommt einen eigenen GeoServer-Layer mit einer SQL-View, die nur die Bezirke
            dieser Stadt anzeigt. Der fertige SQL-Code ist unten bereits generiert — du musst ihn nur kopieren.
          </div>

          <div class="steps-list">
            <div class="step-item">
              <div class="step-num">1</div>
              <div>
                <strong>GeoServer-Admin öffnen</strong><br>
                <a href="{GEOSERVER_URL}/web/" target="_blank" rel="noopener">{GEOSERVER_URL}/web/</a>
                → Daten → Layer hinzufügen → SQL View → Workspace <code>spritzmap</code>
              </div>
            </div>
            <div class="step-item">
              <div class="step-num">2</div>
              <div>
                <strong>Layer-Name vergeben</strong><br>
                Name des neuen Layers: <code>lor_index_{form.slug || 'CITY_SLUG'}</code><br>
                <small>Der vollständige Layer-Name lautet dann <code>spritzmap:lor_index_{form.slug || 'CITY_SLUG'}</code></small>
              </div>
            </div>
            <div class="step-item">
              <div class="step-num">3</div>
              <div>
                <strong>SQL-View einfügen</strong><br>
                Kopiere den generierten SQL-Code und füge ihn als SQL-View ein.
                Der <code>drink_id</code>-Parameter ist bereits als <code>viewparam</code> vordefiniert.
                <div class="code-header">
                  <span>SQL für Layer <code>lor_index_{form.slug || 'CITY_SLUG'}</code></span>
                  <button class="btn-copy" onclick={copyGeoserverSql}>
                    {copied ? '✓ Kopiert!' : 'Kopieren'}
                  </button>
                </div>
                <pre class="code-block">{geoserverSqlSnippet()}</pre>
              </div>
            </div>
            <div class="step-item">
              <div class="step-num">4</div>
              <div>
                <strong>Viewparam registrieren</strong><br>
                Im GeoServer-Formular unter „SQL View Parameters" eintragen:<br>
                Name: <code>drink_id</code> — Default: <code>1</code> — Validator: <code>^[\d]+$</code>
              </div>
            </div>
            <div class="step-item">
              <div class="step-num">5</div>
              <div>
                <strong>Geometrie-Attribut konfigurieren</strong><br>
                Klicke „Refresh" → Geometry-Typ auf <code>MultiPolygon</code> setzen → SRID auf <code>25833</code> (Berlin) oder den SRID deiner LOR-Daten.
              </div>
            </div>
          </div>

          <label class="wms-label">
            WMS-Layer-Name (wird in der Datenbank gespeichert)
            <input type="text" bind:value={form.wms_layer} placeholder={`spritzmap:lor_index_${form.slug || 'CITY_SLUG'}`} />
            <small>Standard: <code>spritzmap:lor_index_{form.slug || 'CITY_SLUG'}</code> — nur ändern wenn du einen anderen Namen vergeben hast</small>
          </label>

          <div class="wizard-actions">
            <button class="btn-outline" onclick={() => { wizardStep = 3; }}>← Zurück</button>
            <button class="btn-primary" disabled={saving} onclick={saveStep4}>
              {saving ? 'Speichern…' : 'Fertigstellen ✓'}
            </button>
          </div>
        </div>
      {/if}
    </div>
  {/if}

  <!-- ── City list ─────────────────────────────────────────────────────────── -->
  {#if !showWizard}
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
              <div><span class="label">WMS-Layer:</span> {city.wms_layer ?? '—'}</div>
              <div><span class="label">OSM-Sync:</span> {city.osm_sync_enabled ? 'Ja' : 'Nein'}</div>
            </div>

            <div class="city-actions">
              <button
                class="btn-secondary"
                disabled={syncingId === city.id}
                onclick={() => triggerSync(city.id)}
              >
                {syncingId === city.id ? 'Syncing…' : '↻ OSM-Sync'}
              </button>
              <button class="btn-outline" onclick={() => toggleActive(city)}>
                {city.is_active ? 'Deaktivieren' : 'Aktivieren'}
              </button>
            </div>
          </div>
        {/each}
      </div>
    {/if}
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

  .loading { color: #888; padding: 2rem 0; text-align: center; }

  /* ── Wizard ── */
  .wizard { margin-bottom: 2rem; }

  .wizard-progress {
    display: flex;
    align-items: center;
    margin-bottom: 1.5rem;
    gap: 0;
  }

  .progress-step {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
  }

  .step-dot {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: #e5e7eb;
    color: #6b7280;
    font-size: 0.8rem;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.2s, color 0.2s;
  }

  .progress-step.active .step-dot {
    background: #e8500a;
    color: white;
  }

  .progress-step.done .step-dot {
    background: #16a34a;
    color: white;
  }

  .step-label {
    font-size: 0.7rem;
    color: #6b7280;
    white-space: nowrap;
  }
  .progress-step.active .step-label { color: #e8500a; font-weight: 600; }
  .progress-step.done .step-label   { color: #16a34a; }

  .progress-line {
    flex: 1;
    height: 2px;
    background: #e5e7eb;
    margin: 0 4px;
    margin-bottom: 20px;
    transition: background 0.2s;
  }
  .progress-line.done { background: #16a34a; }

  .wizard-card {
    background: white;
    border-radius: 12px;
    padding: 1.75rem;
    box-shadow: 0 1px 6px rgba(0,0,0,0.08);
  }

  .wizard-card h2 {
    font-size: 1.1rem;
    font-weight: 700;
    margin: 0 0 1.25rem;
    color: #1a1a2e;
  }

  .info-box {
    background: #f0f9ff;
    border-left: 3px solid #0ea5e9;
    border-radius: 0 8px 8px 0;
    padding: 0.75rem 1rem;
    font-size: 0.85rem;
    color: #0c4a6e;
    margin-bottom: 1.25rem;
    line-height: 1.5;
  }

  .info-important {
    background: #fff7ed;
    border-color: #f97316;
    color: #7c2d12;
  }

  .info-box a { color: #0ea5e9; }

  .code-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 0.75rem;
    margin-bottom: 0;
    background: #2d3748;
    border-radius: 6px 6px 0 0;
    padding: 0.4rem 0.75rem;
    font-size: 0.75rem;
    color: #a0aec0;
  }

  .code-header code { color: #e2e8f0; }

  .btn-copy {
    padding: 2px 10px;
    background: #4a5568;
    color: #e2e8f0;
    border: none;
    border-radius: 4px;
    font-size: 0.72rem;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s;
    white-space: nowrap;
  }
  .btn-copy:hover { background: #718096; }

  .code-header + .code-block {
    border-radius: 0 0 6px 6px;
    margin-top: 0;
  }

  .form-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
    margin-bottom: 1.25rem;
  }

  .form-grid label {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 0.8rem;
    font-weight: 600;
    color: #555;
  }

  .form-grid label.full { grid-column: 1 / -1; }

  .form-grid input {
    padding: 0.5rem 0.75rem;
    border: 1px solid #ddd;
    border-radius: 6px;
    font-size: 0.875rem;
    font-family: inherit;
  }
  .form-grid input:focus { outline: 2px solid #e8500a; border-color: transparent; }

  .form-grid small { font-size: 0.72rem; color: #888; font-weight: 400; }

  .steps-list {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    margin-bottom: 1.25rem;
  }

  .step-item {
    display: flex;
    gap: 1rem;
    align-items: flex-start;
  }

  .step-num {
    width: 26px;
    height: 26px;
    border-radius: 50%;
    background: #1a1a2e;
    color: white;
    font-size: 0.75rem;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    margin-top: 1px;
  }

  .step-item > div { font-size: 0.875rem; line-height: 1.6; color: #333; }
  .step-item strong { display: block; margin-bottom: 2px; color: #1a1a2e; }

  .step-item ul {
    margin: 6px 0 0 1rem;
    padding: 0;
  }
  .step-item li { margin-bottom: 2px; }
  .step-item a { color: #e8500a; }

  .code-block {
    background: #1a1a2e;
    color: #e2e8f0;
    border-radius: 6px;
    padding: 0.75rem 1rem;
    font-size: 0.78rem;
    font-family: 'Courier New', monospace;
    margin: 0.5rem 0 0;
    overflow-x: auto;
    white-space: pre;
  }

  .wms-label {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 0.8rem;
    font-weight: 600;
    color: #555;
    margin-bottom: 1.25rem;
  }
  .wms-label input {
    max-width: 320px;
    padding: 0.5rem 0.75rem;
    border: 1px solid #ddd;
    border-radius: 6px;
    font-size: 0.875rem;
    font-family: inherit;
  }

  .wizard-actions {
    display: flex;
    gap: 0.75rem;
    justify-content: flex-end;
    margin-top: 0.5rem;
  }

  /* ── City cards ── */
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

  .city-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 1rem;
  }
  .city-header strong { font-size: 1rem; color: #1a1a2e; }
  .slug { font-size: 0.78rem; color: #888; margin-left: 4px; }

  .badge {
    font-size: 0.7rem;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 12px;
    text-transform: uppercase;
    white-space: nowrap;
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
  .city-meta .label { font-weight: 600; color: #333; margin-right: 4px; }
  .city-meta code {
    font-family: monospace;
    font-size: 0.75rem;
    background: #f5f5f5;
    padding: 1px 4px;
    border-radius: 3px;
  }

  .city-actions { display: flex; gap: 8px; flex-wrap: wrap; }

  /* ── Buttons ── */
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

  @media (max-width: 640px) {
    .form-grid { grid-template-columns: 1fr; }
    .form-grid label.full { grid-column: 1; }
    .cities-grid { grid-template-columns: 1fr; }
  }
</style>
