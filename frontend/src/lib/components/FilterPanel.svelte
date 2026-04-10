<script lang="ts">
  import { drinks, selectedDrinkId, selectedPriceTier } from '$lib/stores/map';

  const priceTiers = ['€', '€€', '€€€'];

  function selectDrink(id: number | null) {
    selectedDrinkId.set(id);
  }

  function selectTier(tier: string) {
    selectedPriceTier.update((current) => (current === tier ? null : tier));
  }
</script>

<aside class="filter-panel">
  <h2>Filter</h2>

  <section>
    <h3>Getränk</h3>
    <button
      class:active={$selectedDrinkId === null}
      onclick={() => selectDrink(null)}
    >
      Alle
    </button>
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
    <h3>Preis</h3>
    {#each priceTiers as tier}
      <button
        class:active={$selectedPriceTier === tier}
        onclick={() => selectTier(tier)}
      >
        {tier}
      </button>
    {/each}
  </section>
</aside>

<style>
  .filter-panel {
    background: white;
    border-radius: 8px;
    padding: 1rem;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    min-width: 160px;
  }

  h2 {
    font-size: 1rem;
    font-weight: 700;
    margin: 0 0 0.75rem;
  }

  h3 {
    font-size: 0.75rem;
    text-transform: uppercase;
    color: #888;
    margin: 0.75rem 0 0.4rem;
  }

  section {
    display: flex;
    flex-direction: column;
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
