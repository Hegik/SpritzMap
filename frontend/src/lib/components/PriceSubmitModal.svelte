<script lang="ts">
  import { drinks, selectedDrinkId } from '$lib/stores/map';
  import { api } from '$lib/api/client';
  import { buildIconHtml } from '$lib/utils/markerIcon';
  import { t } from '$lib/i18n';
  import { compressImage, fileExtension, type CompressedImage } from '$lib/utils/imageProcessing';
  import { estimateColorValue, type Region } from '$lib/utils/colorAnalysis';
  import { detectGlass } from '$lib/utils/glassDetection';
  import { glassIconSvg } from '$lib/utils/glassIcons';
  import type { GlassType } from '$lib/types/photo';

  let {
    open = $bindable(false),
    locationId = null,
    locationName = '',
    isEmptyLocation = false,
    locationCoords = null,
    onsubmitted = () => {},
  }: {
    open: boolean;
    locationId: number | null;
    locationName: string;
    isEmptyLocation?: boolean;
    locationCoords?: [number, number] | null;
    onsubmitted?: () => void;
  } = $props();

  // Leichte Absicherung gegen Einträge „aus der Ferne“: beim Öffnen Standort prüfen und bei > 100 m
  // einen Hinweis zeigen. Nur ein Hinweis – ohne Standortfreigabe oder GPS geht es normal weiter.
  const MAX_DISTANCE_M = 100;
  let distanceCheck = $state<'checking' | 'far' | 'ok'>('ok');
  let distanceM = $state(0);

  function distanceMeters([lng1, lat1]: [number, number], [lng2, lat2]: [number, number]): number {
    const rad = Math.PI / 180;
    const dLat = (lat2 - lat1) * rad;
    const dLng = (lng2 - lng1) * rad;
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLng / 2) ** 2;
    return 2 * 6371000 * Math.asin(Math.sqrt(a));
  }

  function checkDistance() {
    const target = locationCoords;
    if (!target || !navigator.geolocation) {
      distanceCheck = 'ok';
      return;
    }
    distanceCheck = 'checking';
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        if (!open || distanceCheck !== 'checking') return;
        const d = distanceMeters([pos.coords.longitude, pos.coords.latitude], target);
        distanceM = d;
        // Ungenauigkeit der Ortung zugunsten des Nutzers abziehen
        distanceCheck = d - (pos.coords.accuracy || 0) > MAX_DISTANCE_M ? 'far' : 'ok';
      },
      () => {
        if (distanceCheck === 'checking') distanceCheck = 'ok';
      },
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 30000 },
    );
  }

  $effect(() => {
    if (open) checkDistance();
  });

  function formatDistance(m: number): string {
    return m >= 1000 ? `${(m / 1000).toFixed(1).replace('.', ',')} km` : `${Math.round(m / 10) * 10} m`;
  }

  let drinkId = $state(0);
  let price = $state('');
  let colorValue = $state(128);
  let note = $state('');
  let error = $state('');
  let success = $state(false);
  let loading = $state(false);

  // Foto + KI-Vorschläge (alles im Browser berechnet)
  const GLASS_TYPES: GlassType[] = ['wine', 'tumbler', 'other'];
  let photo = $state<CompressedImage | null>(null);
  let photoPreviewUrl = $state<string | null>(null);
  let analyzing = $state(false);
  let photoWarning = $state('');
  let glassType = $state<GlassType | null>(null);
  let aiGlassType = $state<GlassType | null>(null);
  let aiColorValue = $state<number | null>(null);
  let aiRegion: Region | undefined;
  let colorTouched = $state(false);

  // Fortschrittsbalken: echte Stufen, innerhalb einer Stufe läuft der Balken asymptotisch auf deren Ende zu
  // (der Modell-Download von coco-ssd meldet selbst keinen Fortschritt)
  type AnalysisStage = 'compress' | 'model' | 'detect' | 'color';
  const STAGE_RANGE: Record<AnalysisStage, [number, number]> = {
    compress: [0, 20],
    model: [20, 75],
    detect: [75, 95],
    color: [95, 100],
  };
  let analysisStage = $state<AnalysisStage>('compress');
  let progress = $state(0);
  let progressTimer: ReturnType<typeof setInterval> | undefined;

  function setStage(stage: AnalysisStage) {
    analysisStage = stage;
    progress = Math.max(progress, STAGE_RANGE[stage][0]);
  }

  function startProgress() {
    clearInterval(progressTimer);
    progress = 0;
    setStage('compress');
    progressTimer = setInterval(() => {
      const end = STAGE_RANGE[analysisStage][1];
      progress += (end - progress) * 0.05;
    }, 100);
  }

  function stopProgress() {
    clearInterval(progressTimer);
    progressTimer = undefined;
  }

  // Neues Foto oder Schließen macht eine laufende Analyse ungültig
  let analysisRun = 0;

  function resetPhoto() {
    analysisRun++;
    stopProgress();
    if (photoPreviewUrl) URL.revokeObjectURL(photoPreviewUrl);
    photo?.bitmap.close();
    photo = null;
    photoPreviewUrl = null;
    analyzing = false;
    photoWarning = '';
    glassType = null;
    aiGlassType = null;
    aiColorValue = null;
    aiRegion = undefined;
    colorTouched = false;
  }

  $effect(() => {
    if (!open) {
      resetPhoto();
      price = '';
      note = '';
      colorValue = 128;
      error = '';
    }
  });

  async function onPhotoSelected(e: Event) {
    const input = e.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    resetPhoto();
    const run = analysisRun;
    analyzing = true;
    startProgress();
    let compressed: CompressedImage;
    try {
      compressed = await compressImage(file);
    } catch {
      if (run !== analysisRun) return;
      stopProgress();
      analyzing = false;
      photoWarning = $t.submit.photo_error_read;
      return;
    }
    if (run !== analysisRun) {
      compressed.bitmap.close();
      return;
    }
    photo = compressed;
    photoPreviewUrl = URL.createObjectURL(compressed.thumb);

    // Stufe 2 (Glasform) liefert den Messbereich für Stufe 1 (Farbwert); schlägt sie fehl, Bildmitte nutzen
    try {
      const glass = await detectGlass(compressed.bitmap, (stage) => run === analysisRun && setStage(stage));
      if (run !== analysisRun) return;
      if (glass) {
        aiGlassType = glass.glassType;
        glassType = glass.glassType;
        aiRegion = glass.region;
      }
    } catch (err) {
      console.warn('[SpritzMap] Glaserkennung fehlgeschlagen', err);
      if (run !== analysisRun) return;
    }
    setStage('color');
    applyColorSuggestion();
    stopProgress();
    analyzing = false;
  }

  function applyColorSuggestion() {
    if (!photo) return;
    aiColorValue = estimateColorValue(photo.bitmap, selectedDrinkColor, aiRegion);
    if (aiColorValue !== null && !colorTouched) colorValue = aiColorValue;
  }

  // Sorte gewechselt → Farbvorschlag mit dem neuen Farbton neu berechnen
  let lastDrinkColor = '';
  $effect(() => {
    const c = selectedDrinkColor;
    if (c === lastDrinkColor) return;
    lastDrinkColor = c;
    if (photo && !analyzing) applyColorSuggestion();
  });

  async function markUnavailable() {
    if (!locationId || !drinkId) return;
    loading = true;
    try {
      await api.post('/prices/unavailable', { location_id: locationId, drink_id: drinkId });
      success = true;
      onsubmitted();
      setTimeout(() => { open = false; success = false; }, 1500);
    } catch (e: unknown) {
      error = e instanceof Error ? e.message : $t.submit.error_generic;
    } finally {
      loading = false;
    }
  }

  async function markNoSpritz() {
    if (!locationId) return;
    loading = true;
    try {
      await api.post(`/locations/${locationId}/no-spritz`, {});
      success = true;
      onsubmitted();
      setTimeout(() => { open = false; success = false; }, 1500);
    } catch (e: unknown) {
      error = e instanceof Error ? e.message : $t.submit.error_generic;
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    if ($drinks.length) drinkId = $selectedDrinkId ?? $drinks[0]?.id ?? 0;
  });

  const selectedDrinkColor = $derived(
    $drinks.find((d) => d.id === drinkId)?.color_hex ?? '#ff6e00'
  );

  const previewHtml = $derived(buildIconHtml(selectedDrinkColor, colorValue, 180));

  async function submit() {
    error = '';
    photoWarning = '';
    loading = true;
    try {
      const entry = await api.post<{ id: number }>('/prices/', {
        location_id: locationId,
        drink_id: drinkId,
        price: parseFloat(price),
        color_value: colorValue,
        note: note || null,
        glass_type: glassType,
        ai_color_value: aiColorValue,
        ai_glass_type: aiGlassType,
      });

      // Preis ist gespeichert – ein fehlgeschlagener Foto-Upload macht ihn nicht ungültig
      if (photo && locationId) {
        try {
          const form = new FormData();
          form.append('location_id', String(locationId));
          form.append('price_entry_id', String(entry.id));
          form.append('file', photo.full, `photo.${fileExtension(photo.full)}`);
          form.append('thumb', photo.thumb, `thumb.${fileExtension(photo.thumb)}`);
          await api.upload('/photos', form);
        } catch {
          photoWarning = $t.submit.photo_error_upload;
        }
      }

      success = true;
      onsubmitted();
      setTimeout(() => { open = false; success = false; }, photoWarning ? 3500 : 1500);
    } catch (e: unknown) {
      error = e instanceof Error ? e.message : $t.submit.error_save;
    } finally {
      loading = false;
    }
  }
</script>

{#if open}
  <div
    class="overlay"
    onclick={() => (open = false)}
    onkeydown={(e) => e.key === 'Escape' && (open = false)}
    role="dialog"
    aria-modal="true"
    tabindex="-1"
  >
    <div
      class="modal"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="presentation"
    >
      <h2>{$t.submit.heading}</h2>
      <p class="location-name">{locationName}</p>

      {#if distanceCheck === 'checking'}
        <p class="hint center">{$t.submit.distance_checking}</p>
        <button type="button" class="btn-unavailable" onclick={() => (distanceCheck = 'ok')}>
          {$t.submit.distance_skip}
        </button>
      {:else if distanceCheck === 'far'}
        <div class="distance-warning">
          <p class="distance-title">{$t.submit.distance_title(formatDistance(distanceM))}</p>
          <p>{$t.submit.distance_text}</p>
        </div>
        <button type="button" class="btn-primary" onclick={() => (open = false)}>{$t.submit.distance_cancel}</button>
        <button type="button" class="btn-unavailable" onclick={() => (distanceCheck = 'ok')}>
          {$t.submit.distance_continue}
        </button>
      {:else if success}
        <p class="success">{$t.submit.success}</p>
        {#if photoWarning}<p class="warning">{photoWarning}</p>{/if}
      {:else}
        <form onsubmit={(e) => { e.preventDefault(); submit(); }}>
          <label>
            {$t.submit.label_drink}
            <select bind:value={drinkId}>
              {#each $drinks as drink}
                <option value={drink.id}>{drink.name}</option>
              {/each}
            </select>
          </label>

          <label>
            {$t.submit.label_price}
            <input
              type="number"
              bind:value={price}
              step="0.10"
              min="0.50"
              max="50"
              required
              placeholder={$t.submit.placeholder_price}
            />
          </label>

          <div class="photo-field">
            <span class="field-label">{$t.submit.label_photo}</span>
            <div class="photo-row">
              {#if photoPreviewUrl}
                <img class="photo-preview" src={photoPreviewUrl} alt={$t.submit.photo_preview_alt} />
              {/if}
              <label class="photo-btn">
                {photoPreviewUrl ? $t.submit.btn_photo_change : $t.submit.btn_photo_add}
                <input type="file" accept="image/*" capture="environment" onchange={onPhotoSelected} hidden />
              </label>
              {#if photoPreviewUrl && !analyzing}
                <button type="button" class="photo-remove" onclick={resetPhoto}>{$t.submit.btn_photo_remove}</button>
              {/if}
            </div>
            {#if analyzing}
              <div
                class="progress"
                role="progressbar"
                aria-label={$t.submit.analyzing}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(progress)}
              >
                <div class="progress-fill" style="width: {progress}%"></div>
              </div>
              <p class="hint">{$t.submit.analyze_stage[analysisStage]}</p>
            {:else if photo && aiColorValue === null && aiGlassType === null}
              <p class="hint">{$t.submit.ai_nothing_found}</p>
            {/if}
            {#if photoWarning && !success}<p class="warning">{photoWarning}</p>{/if}
          </div>

          <div class="preview-wrapper">
            {@html previewHtml}
          </div>

          <label>
            <span>
              {$t.submit.label_intensity} ({colorValue})
              {#if aiColorValue !== null && !colorTouched}<span class="ai-badge">{$t.submit.ai_badge}</span>{/if}
            </span>
            <div class="color-slider-wrapper">
              <span style="opacity: 0.2; color: {selectedDrinkColor}">●</span>
              <input type="range" bind:value={colorValue} min={0} max={255} oninput={() => (colorTouched = true)} />
              <span style="color: {selectedDrinkColor}">●</span>
            </div>
          </label>

          <div class="glass-field">
            <span class="field-label">
              {$t.submit.label_glass}
              {#if aiGlassType !== null && glassType === aiGlassType}<span class="ai-badge">{$t.submit.ai_badge}</span>{/if}
            </span>
            <div class="chips">
              {#each GLASS_TYPES as g}
                <button
                  type="button"
                  class="chip glass-chip"
                  class:active={glassType === g}
                  aria-pressed={glassType === g}
                  onclick={() => (glassType = glassType === g ? null : g)}
                >{@html glassIconSvg(g, 26)}<span>{$t.glass[g]}</span></button>
              {/each}
            </div>
          </div>

          <label>
            {$t.submit.label_note}
            <input type="text" bind:value={note} maxlength={500} placeholder={$t.submit.placeholder_note} />
          </label>

          {#if error}
            <p class="error">{error}</p>
          {/if}

          <button type="submit" disabled={loading}>
            {loading ? $t.submit.btn_loading : $t.submit.btn_submit}
          </button>
        </form>

        <div class="divider"></div>

        <button class="btn-unavailable" disabled={loading} onclick={markUnavailable}>
          {$t.submit.btn_unavailable}
        </button>

        {#if isEmptyLocation}
          <button class="btn-no-spritz" disabled={loading} onclick={markNoSpritz}>
            {$t.submit.btn_no_spritz}
          </button>
        {/if}
      {/if}
    </div>
  </div>
{/if}

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.45);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .modal {
    background: white;
    border-radius: 12px;
    padding: 2rem;
    width: min(380px, 92vw);
    max-height: 92dvh;
    overflow-y: auto;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  }

  h2 { margin: 0 0 0.25rem; font-size: 1.2rem; }
  .location-name { margin: 0 0 1.25rem; color: #666; font-size: 0.9rem; }

  form { display: flex; flex-direction: column; gap: 1rem; }

  label { display: flex; flex-direction: column; gap: 4px; font-size: 0.875rem; font-weight: 500; }

  input, select {
    padding: 8px 12px;
    border: 1.5px solid #ddd;
    border-radius: 6px;
    font-size: 1rem;
  }

  input:focus, select:focus { outline: none; border-color: #555; }

  .preview-wrapper {
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 8px 0 4px;
  }

  .color-slider-wrapper {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 1.2rem;
  }

  .color-slider-wrapper input { flex: 1; padding: 0; border: none; }

  button[type='submit'], .btn-primary {
    padding: 10px;
    background: #e8500a;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
  }

  .btn-primary { width: 100%; margin-bottom: 6px; }
  button[type='submit']:disabled { opacity: 0.6; }
  .center { text-align: center; padding: 1rem 0; }

  .distance-warning {
    margin-bottom: 1rem;
    padding: 12px 14px;
    border-radius: 8px;
    background: #fff8e6;
    border: 1px solid #f3d27a;
    color: #5c4300;
    font-size: 0.875rem;
    line-height: 1.4;
  }
  .distance-warning p { margin: 0; }
  .distance-title { font-weight: 600; margin-bottom: 4px !important; }
  .error { color: #c00; font-size: 0.875rem; margin: 0; }
  .success { color: green; font-weight: 600; text-align: center; padding: 1rem; }

  .warning { color: #b26a00; font-size: 0.85rem; margin: 0; text-align: center; }
  .hint { color: #888; font-size: 0.8rem; margin: 0; }
  .field-label { font-size: 0.875rem; font-weight: 500; }

  .photo-field, .glass-field { display: flex; flex-direction: column; gap: 6px; }
  .photo-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .photo-preview { width: 56px; height: 56px; object-fit: cover; border-radius: 6px; border: 1px solid #ddd; }
  .photo-btn {
    display: inline-block;
    padding: 6px 12px;
    border: 1.5px dashed #bbb;
    border-radius: 6px;
    font-size: 0.85rem;
    font-weight: 500;
    color: #555;
    cursor: pointer;
  }
  .photo-remove { background: none; border: none; color: #999; font-size: 0.8rem; cursor: pointer; text-decoration: underline; }

  .chips { display: flex; gap: 6px; flex-wrap: wrap; }
  .chip {
    padding: 5px 12px;
    border: 1.5px solid #ddd;
    border-radius: 999px;
    background: white;
    font-size: 0.85rem;
    cursor: pointer;
  }
  .glass-chip {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 8px 6px 6px;
    border-radius: 10px;
    color: #555;
    font-size: 0.78rem;
  }
  .chip.active { border-color: #e8500a; background: #fff3ec; color: #b33c00; font-weight: 600; }

  .progress {
    height: 6px;
    border-radius: 999px;
    background: #f1e6df;
    overflow: hidden;
  }
  .progress-fill {
    height: 100%;
    border-radius: inherit;
    background: linear-gradient(90deg, #e8500a, #ff9a3c, #e8500a);
    background-size: 200% 100%;
    animation: progress-shimmer 1.2s linear infinite;
    transition: width 0.15s linear;
  }
  @keyframes progress-shimmer {
    from { background-position: 200% 0; }
    to { background-position: 0 0; }
  }

  .ai-badge {
    margin-left: 6px;
    padding: 1px 6px;
    border-radius: 4px;
    background: #eef2ff;
    color: #4150a8;
    font-size: 0.7rem;
    font-weight: 600;
    vertical-align: middle;
  }

  .divider { border-top: 1px solid #eee; margin: 0.75rem 0; }

  .btn-unavailable {
    width: 100%;
    padding: 8px;
    background: none;
    border: 1.5px solid #ddd;
    border-radius: 6px;
    font-size: 0.85rem;
    color: #666;
    cursor: pointer;
    margin-bottom: 6px;
  }

  .btn-unavailable:hover { border-color: #aaa; color: #333; }

  .btn-no-spritz {
    width: 100%;
    padding: 8px;
    background: none;
    border: 1.5px solid #f44336;
    border-radius: 6px;
    font-size: 0.85rem;
    color: #f44336;
    cursor: pointer;
  }

  .btn-no-spritz:hover { background: #fff5f5; }
</style>
