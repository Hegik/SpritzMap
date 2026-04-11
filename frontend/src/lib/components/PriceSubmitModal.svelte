<script lang="ts">
  import { drinks } from '$lib/stores/map';
  import { api } from '$lib/api/client';

  let {
    open = $bindable(false),
    locationId = null,
    locationName = '',
    isEmptyLocation = false,
    onsubmitted = () => {},
  }: {
    open: boolean;
    locationId: number | null;
    locationName: string;
    isEmptyLocation?: boolean;
    onsubmitted?: () => void;
  } = $props();

  let drinkId = $state(0);
  let price = $state('');
  let colorValue = $state(128);
  let note = $state('');
  let error = $state('');
  let success = $state(false);
  let loading = $state(false);

  async function markUnavailable() {
    if (!locationId || !drinkId) return;
    loading = true;
    try {
      await api.post('/prices/unavailable', { location_id: locationId, drink_id: drinkId });
      success = true;
      onsubmitted();
      setTimeout(() => { open = false; success = false; }, 1500);
    } catch (e: unknown) {
      error = e instanceof Error ? e.message : 'Fehler';
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
      error = e instanceof Error ? e.message : 'Fehler';
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    if ($drinks.length && !drinkId) drinkId = $drinks[0]?.id ?? 0;
  });

  async function submit() {
    error = '';
    loading = true;
    try {
      await api.post('/prices/', {
        location_id: locationId,
        drink_id: drinkId,
        price: parseFloat(price),
        color_value: colorValue,
        note: note || null,
      });
      success = true;
      onsubmitted();
      setTimeout(() => { open = false; success = false; }, 1500);
    } catch (e: unknown) {
      error = e instanceof Error ? e.message : 'Fehler beim Speichern';
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
      role="document"
    >
      <h2>Preis melden</h2>
      <p class="location-name">{locationName}</p>

      {#if success}
        <p class="success">Gespeichert!</p>
      {:else}
        <form onsubmit={(e) => { e.preventDefault(); submit(); }}>
          <label>
            Getränk
            <select bind:value={drinkId}>
              {#each $drinks as drink}
                <option value={drink.id}>{drink.name}</option>
              {/each}
            </select>
          </label>

          <label>
            Preis (€)
            <input
              type="number"
              bind:value={price}
              step="0.10"
              min="0.50"
              max="50"
              required
              placeholder="z.B. 7.50"
            />
          </label>

          <label>
            Farb-Intensität ({colorValue})
            <div class="color-slider-wrapper">
              <span style="opacity: 0.2">●</span>
              <input type="range" bind:value={colorValue} min={0} max={255} />
              <span>●</span>
            </div>
          </label>

          <label>
            Notiz (optional)
            <input type="text" bind:value={note} maxlength={500} placeholder="z.B. nur am Wochenende" />
          </label>

          {#if error}
            <p class="error">{error}</p>
          {/if}

          <button type="submit" disabled={loading}>
            {loading ? 'Speichern…' : 'Preis melden'}
          </button>
        </form>

        <div class="divider"></div>

        <button class="btn-unavailable" disabled={loading} onclick={markUnavailable}>
          Diese Sorte gibt es hier nicht
        </button>

        {#if isEmptyLocation}
          <button class="btn-no-spritz" disabled={loading} onclick={markNoSpritz}>
            Hier gibt es generell keinen Spritz
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

  .color-slider-wrapper {
    display: flex;
    align-items: center;
    gap: 8px;
    color: #e8500a;
    font-size: 1.2rem;
  }

  .color-slider-wrapper input { flex: 1; padding: 0; border: none; }

  button[type='submit'] {
    padding: 10px;
    background: #e8500a;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
  }

  button[type='submit']:disabled { opacity: 0.6; }
  .error { color: #c00; font-size: 0.875rem; margin: 0; }
  .success { color: green; font-weight: 600; text-align: center; padding: 1rem; }

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
