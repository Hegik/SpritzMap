<script lang="ts">
  import { onMount } from 'svelte';
  import { buildIconHtml, buildNodataIconHtml } from '$lib/utils/markerIcon';
  import { t } from '$lib/i18n';

  let {
    zoom,
    wmsMaxZoom,
    hasWms,
    drinkColor,
    showUnpriced,
  }: {
    zoom: number;
    wmsMaxZoom: number;
    hasWms: boolean;
    drinkColor: string;
    showUnpriced: boolean;
  } = $props();

  interface PriceTier { label: string; min: number | null; max: number | null }

  const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
  const STORAGE_KEY = 'spritzmap_legend_open';

  let open = $state(false);
  let tiers = $state<PriceTier[]>([]);

  // Gleiche Opacity-Formel wie im SLD: 0.08 + index/100 × 0.72
  const areaGradient = $derived(`linear-gradient(to right, ${drinkColor}14, ${drinkColor}cc)`);
  const showArea = $derived(hasWms && zoom < wmsMaxZoom);
  const markers = $derived([
    { value: 30, label: $t.legend.marker_weak },
    { value: 128, label: $t.legend.marker_medium },
    { value: 230, label: $t.legend.marker_strong },
  ].map((m) => ({ ...m, html: buildIconHtml(drinkColor, m.value, 28) })));

  const fmt = (n: number) => n.toFixed(2).replace('.', ',');

  function tierText(tier: PriceTier): string {
    if (tier.max != null) return $t.legend.tier_up_to(fmt(tier.max));
    return $t.legend.tier_from(fmt(tier.min ?? 0));
  }

  function toggle() {
    open = !open;
    try { localStorage.setItem(STORAGE_KEY, open ? '1' : '0'); } catch {}
  }

  onMount(async () => {
    // Desktop standardmäßig offen, Handy eingeklappt; letzte Wahl merken
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      open = stored != null ? stored === '1' : window.matchMedia('(min-width: 641px)').matches;
    } catch {
      open = window.matchMedia('(min-width: 641px)').matches;
    }
    const res = await fetch(`${API_URL}/config/price-tiers`).catch(() => null);
    if (res?.ok) tiers = await res.json();
  });
</script>

<div class="legend" class:open>
  <button class="toggle" onclick={toggle} aria-expanded={open} aria-label={$t.legend.toggle_aria}>
    {$t.legend.title} <span class="chev">{open ? '▾' : '▸'}</span>
  </button>

  {#if open}
    <div class="body">
      {#if showArea}
        <section>
          <h4>{$t.legend.section_area}</h4>
          <div class="gradient" style="background: {areaGradient}"></div>
          <div class="gradient-labels"><span>{$t.legend.area_low}</span><span>{$t.legend.area_high}</span></div>
          <div class="row"><span class="swatch nodata"></span>{$t.legend.area_nodata}</div>
          <p class="hint">{$t.legend.zoom_hint}</p>
        </section>
      {:else}
        <section>
          <h4>{$t.legend.section_markers}</h4>
          {#each markers as m}
            <div class="row"><span class="icon">{@html m.html}</span>{m.label}</div>
          {/each}
          {#if showUnpriced}
            <div class="row"><span class="icon">{@html buildNodataIconHtml(28)}</span>{$t.legend.marker_nodata}</div>
          {/if}
        </section>
      {/if}

      {#if tiers.length}
        <section>
          <h4>{$t.legend.section_tiers}</h4>
          {#each tiers as tier}
            <div class="row"><b class="tier">{tier.label}</b>{tierText(tier)}</div>
          {/each}
        </section>
      {/if}
    </div>
  {/if}
</div>

<style>
  .legend {
    position: absolute;
    right: 0.65rem;
    bottom: 2.75rem; /* über der MapLibre-Attribution samt „i“-Button */
    z-index: 10;
    background: rgba(255, 255, 255, 0.95);
    border-radius: 10px;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.15);
    font-size: 0.78rem;
    color: #444;
    max-width: 210px;
  }

  .toggle {
    width: 100%;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    background: none;
    border: none;
    padding: 6px 10px;
    font-size: 0.8rem;
    font-weight: 600;
    color: #333;
    cursor: pointer;
  }

  .body { padding: 0 10px 8px; }

  section + section { margin-top: 8px; border-top: 1px solid #eee; padding-top: 6px; }

  h4 {
    margin: 0 0 4px;
    font-size: 0.7rem;
    font-weight: 600;
    color: #999;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .row { display: flex; align-items: center; gap: 6px; min-height: 22px; }
  .icon { display: inline-flex; width: 28px; height: 28px; }
  .tier { display: inline-block; min-width: 2.2em; color: #e8500a; }

  .gradient { height: 10px; border-radius: 3px; border: 1px solid #ddd; }
  .gradient-labels { display: flex; justify-content: space-between; font-size: 0.68rem; color: #888; margin: 2px 0 4px; }
  .swatch { width: 14px; height: 10px; border-radius: 2px; border: 1px dashed #bbb; }
  .hint { margin: 4px 0 0; font-size: 0.68rem; color: #999; font-style: italic; }

  @media (max-width: 640px) {
    .legend { bottom: calc(var(--filter-bar-h, 0px) + 2.5rem); }
  }
</style>
