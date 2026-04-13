<script lang="ts">
  import { drinks, selectedDrinkId, selectedPriceTier } from '$lib/stores/map';
  import { t } from '$lib/i18n';

  const priceTiers = ['€', '€€', '€€€'];
  let collapsed = $state(false);

  function selectDrink(id: number) {
    selectedDrinkId.set(id);
  }

  function selectTier(tier: string) {
    selectedPriceTier.update((current) => (current === tier ? null : tier));
  }
</script>

<aside class="filter-panel" class:collapsed>
  <button class="toggle" onclick={() => (collapsed = !collapsed)} aria-label={$t.filter.toggle_aria}>
    <span class="toggle-icon">{collapsed ? '▲' : '▼'}</span>
    <span class="toggle-label">{$t.filter.label}</span>
  </button>

  <div class="content">
    <section>
      <h3>{$t.filter.drink}</h3>
      {#each $drinks as drink}
        <button
          class:active={$selectedDrinkId === drink.id}
          style="--drink-color: {drink.color_hex}"
          onclick={() => selectDrink(drink.id)}
        >
          <span class="dot"></span>
          {drink.name}
        </button>
      {/each}
    </section>

    <section>
      <h3>{$t.filter.price}</h3>
      <div class="tier-row">
        {#each priceTiers as tier}
          <button
            class:active={$selectedPriceTier === tier}
            onclick={() => selectTier(tier)}
          >
            {tier}
          </button>
        {/each}
      </div>
    </section>
  </div>
</aside>

<style>
  .filter-panel {
    position: absolute;
    z-index: 5;
    background: white;
    border-radius: 10px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.18);
    overflow: hidden;
  }

  /* ── Desktop: floating top-left ── */
  @media (min-width: 641px) {
    .filter-panel {
      top: 1rem;
      right: 1rem;
      min-width: 170px;
    }

    .toggle {
      display: none;
    }

    .content {
      padding: 1rem;
      display: flex;
      flex-direction: column;
      gap: 0;
    }
  }

  /* ── Mobile: bottom sheet ── */
  @media (max-width: 640px) {
    .filter-panel {
      bottom: 0;
      left: 0;
      right: 0;
      border-radius: 14px 14px 0 0;
      transition: transform 0.3s ease;
    }

    .filter-panel.collapsed .content {
      display: none;
    }

    .toggle {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      width: 100%;
      padding: 12px 16px;
      background: none;
      border: none;
      border-bottom: 1px solid #f0f0f0;
      cursor: pointer;
      font-size: 0.95rem;
      font-weight: 600;
      color: #333;
    }

    .filter-panel.collapsed .toggle {
      border-bottom: none;
    }

    .toggle-icon {
      font-size: 0.7rem;
      color: #888;
    }

    .content {
      padding: 0.75rem 1rem 1rem;
      display: flex;
      flex-direction: row;
      gap: 1.5rem;
      overflow-x: auto;
    }
  }

  h3 {
    font-size: 0.72rem;
    text-transform: uppercase;
    color: #888;
    margin: 0.75rem 0 0.4rem;
    white-space: nowrap;
  }

  @media (max-width: 640px) {
    h3 { margin-top: 0; }
  }

  section {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .tier-row {
    display: flex;
    flex-direction: row;
    gap: 4px;
  }

  button {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    border: 1.5px solid #e0e0e0;
    border-radius: 6px;
    background: white;
    cursor: pointer;
    font-size: 0.875rem;
    transition: all 0.15s;
    white-space: nowrap;
  }

  button:hover {
    border-color: #aaa;
  }

  button.active {
    border-color: #555;
    background: #f5f5f5;
    font-weight: 600;
  }

  .dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--drink-color, #ccc);
    flex-shrink: 0;
  }
</style>
