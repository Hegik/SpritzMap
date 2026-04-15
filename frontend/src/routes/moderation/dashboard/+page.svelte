<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api/client';
  import { t } from '$lib/i18n';

  interface DrinkStat { drink_name: string; color_hex: string; count: number }
  interface DayStat { date: string; count: number }
  interface Stats {
    total_entries: number;
    entries_by_drink: DrinkStat[];
    entries_last_30_days: DayStat[];
    total_users: number;
    total_locations_with_price: number;
  }

  let stats = $state<Stats | null>(null);
  let error = $state('');

  const drinkChartBars = $derived(stats ? drinkBars(stats.entries_by_drink) : []);
  const dayChartBars = $derived(stats ? dayBars(stats.entries_last_30_days) : []);

  onMount(async () => {
    try {
      stats = await api.get<Stats>('/moderation/stats');
    } catch (e) {
      error = e instanceof Error ? e.message : $t.moderation.error_generic;
    }
  });

  // ── SVG bar chart helpers ─────────────────────────────────────────────────

  const CHART_W = 480;
  const CHART_H = 160;
  const BAR_GAP = 4;

  function drinkBars(items: DrinkStat[]) {
    if (!items.length) return [];
    const max = Math.max(...items.map((d) => d.count));
    const barW = Math.max(8, (CHART_W - BAR_GAP * (items.length - 1)) / items.length);
    return items.map((d, i) => ({
      x: i * (barW + BAR_GAP),
      y: CHART_H - (d.count / max) * CHART_H,
      w: barW,
      h: (d.count / max) * CHART_H,
      color: d.color_hex,
      label: d.drink_name,
      count: d.count,
    }));
  }

  function dayBars(items: DayStat[]) {
    // Fill all 30 days even if no data
    const today = new Date();
    const days: { date: string; count: number }[] = [];
    for (let i = 29; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(today.getDate() - i);
      const key = d.toISOString().slice(0, 10);
      const found = items.find((x) => x.date === key);
      days.push({ date: key, count: found?.count ?? 0 });
    }
    const max = Math.max(...days.map((d) => d.count), 1);
    const barW = (CHART_W - BAR_GAP * 29) / 30;
    return days.map((d, i) => ({
      x: i * (barW + BAR_GAP),
      y: CHART_H - (d.count / max) * CHART_H,
      w: barW,
      h: (d.count / max) * CHART_H,
      date: d.date,
      count: d.count,
    }));
  }
</script>

<div class="dashboard">
  <h1 class="page-title">Dashboard</h1>

  {#if error}
    <p class="error">{error}</p>
  {:else if !stats}
    <p class="loading">{$t.moderation.loading}</p>
  {:else}
    <!-- Stat cards -->
    <div class="stat-cards">
      <div class="card">
        <span class="card-value">{stats.total_entries.toLocaleString('de-DE')}</span>
        <span class="card-label">{$t.moderation.stat_total_entries}</span>
      </div>
      <div class="card">
        <span class="card-value">{stats.total_users.toLocaleString('de-DE')}</span>
        <span class="card-label">{$t.moderation.stat_total_users}</span>
      </div>
      <div class="card">
        <span class="card-value">{stats.total_locations_with_price.toLocaleString('de-DE')}</span>
        <span class="card-label">{$t.moderation.stat_locations}</span>
      </div>
    </div>

    <!-- Charts row -->
    <div class="charts-row">
      <!-- Entries by drink -->
      <div class="chart-box">
        <h2 class="chart-title">{$t.moderation.chart_by_drink}</h2>
        {#if drinkChartBars.length === 0}
          <p class="empty">Keine Daten</p>
        {:else}
          <svg viewBox="0 0 {CHART_W} {CHART_H + 32}" class="chart-svg">
            {#each drinkChartBars as b}
              <rect x={b.x} y={b.y} width={b.w} height={b.h} fill={b.color} rx="2" opacity="0.85">
                <title>{b.label}: {b.count}</title>
              </rect>
              <text
                x={b.x + b.w / 2}
                y={CHART_H + 14}
                text-anchor="middle"
                font-size="11"
                fill="#555"
              >{b.label.length > 8 ? b.label.slice(0, 7) + '…' : b.label}</text>
              <text
                x={b.x + b.w / 2}
                y={b.y > 12 ? b.y - 4 : b.y + 12}
                text-anchor="middle"
                font-size="10"
                fill="#333"
              >{b.count}</text>
            {/each}
          </svg>
        {/if}
      </div>

      <!-- Entries last 30 days -->
      <div class="chart-box">
        <h2 class="chart-title">{$t.moderation.chart_last_30_days}</h2>
        <svg viewBox="0 0 {CHART_W} {CHART_H + 32}" class="chart-svg">
          {#each dayChartBars as b}
            {#if b.count > 0}
              <rect x={b.x} y={b.y} width={b.w} height={b.h} fill="#e8500a" rx="1" opacity="0.75">
                <title>{b.date}: {b.count}</title>
              </rect>
            {/if}
          {/each}
          <!-- x-axis labels every 7 days -->
          {#each dayChartBars.filter((_, i) => i % 7 === 0) as b}
            <text
              x={b.x + b.w / 2}
              y={CHART_H + 14}
              text-anchor="middle"
              font-size="10"
              fill="#777"
            >{b.date.slice(5)}</text>
          {/each}
          <!-- baseline -->
          <line x1="0" y1={CHART_H} x2={CHART_W} y2={CHART_H} stroke="#e0e0e0" stroke-width="1" />
        </svg>
      </div>
    </div>
  {/if}
</div>

<style>
  .dashboard { max-width: 900px; }

  .page-title {
    font-size: 1.5rem;
    font-weight: 700;
    color: #1a1a2e;
    margin: 0 0 1.5rem;
  }

  .loading { color: #888; }
  .error { color: #c00; }

  .stat-cards {
    display: flex;
    gap: 1rem;
    margin-bottom: 2rem;
    flex-wrap: wrap;
  }

  .card {
    background: white;
    border-radius: 10px;
    padding: 1.25rem 1.5rem;
    min-width: 160px;
    flex: 1;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .card-value {
    font-size: 2rem;
    font-weight: 700;
    color: #e8500a;
    line-height: 1;
  }

  .card-label {
    font-size: 0.8rem;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .charts-row {
    display: flex;
    gap: 1.5rem;
    flex-wrap: wrap;
  }

  .chart-box {
    background: white;
    border-radius: 10px;
    padding: 1.25rem 1.5rem;
    flex: 1;
    min-width: 280px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
  }

  .chart-title {
    font-size: 0.8rem;
    font-weight: 600;
    color: #666;
    margin: 0 0 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .chart-svg {
    width: 100%;
    height: auto;
    display: block;
  }

  .empty { color: #aaa; font-size: 0.875rem; }
</style>
