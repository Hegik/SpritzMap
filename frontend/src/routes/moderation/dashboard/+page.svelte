<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api/client';

  // ── types ─────────────────────────────────────────────────────────────────
  interface DayCount { date: string; count: number }
  interface UsersStats { registrations: DayCount[]; deletions: DayCount[]; base_count: number }
  interface DrinkMeta { id: number; name: string; color_hex: string }
  interface EntriesStats { drinks: DrinkMeta[]; days: { date: string; counts: Record<string, number> }[] }
  interface DayPrice { date: string; avg_price: number }
  interface PricesStats { berlin: DayPrice[]; lor: DayPrice[] }
  interface LOR { lor_schluessel: string; pr_name: string }
  interface PriceChange {
    entry_id: number; location_name: string; drink_name: string;
    new_price: number; prev_price: number; delta: number;
    reported_at: string; username: string | null; user_id: number | null;
  }

  // ── filter state ──────────────────────────────────────────────────────────
  const NOW = new Date();
  const YEARS = Array.from({ length: 4 }, (_, i) => NOW.getFullYear() - i);
  const MONTH_NAMES = [
    'Januar','Februar','März','April','Mai','Juni',
    'Juli','August','September','Oktober','November','Dezember',
  ];

  let granularity = $state<'year' | 'month'>('month');
  let selYear  = $state(NOW.getFullYear());
  let selMonth = $state(NOW.getMonth() + 1);

  // ── data state ────────────────────────────────────────────────────────────
  let usersData   = $state<UsersStats | null>(null);
  let entriesData = $state<EntriesStats | null>(null);
  let pricesData  = $state<PricesStats | null>(null);
  let lors        = $state<LOR[]>([]);
  let changes     = $state<PriceChange[]>([]);
  let selLor      = $state('');

  let loadingU = $state(false); let errU = $state('');
  let loadingE = $state(false); let errE = $state('');
  let loadingP = $state(false); let errP = $state('');
  let loadingC = $state(false);

  let chart1Mode = $state<'activity' | 'cumulative'>('activity');
  let expandedId = $state<number | null>(null);
  let actionErr  = $state('');

  // ── ApexCharts ────────────────────────────────────────────────────────────
  let Apex: any;
  let apexLoaded = $state(false);
  let el1 = $state<HTMLDivElement | undefined>(undefined);
  let el2 = $state<HTMLDivElement | undefined>(undefined);
  let el3 = $state<HTMLDivElement | undefined>(undefined);

  // "YYYY-MM-DD" → UTC timestamp
  const ts = (d: string) => new Date(d + 'T00:00:00Z').getTime();

  function buildUserDays(data: UsersStats) {
    const regMap = Object.fromEntries(data.registrations.map(r => [r.date, r.count]));
    const delMap = Object.fromEntries(data.deletions.map(d => [d.date, d.count]));
    const allDates = [...new Set([
      ...data.registrations.map(r => r.date),
      ...data.deletions.map(d => d.date),
    ])].sort();
    if (!allDates.length) return [];
    const days: { date: string; reg: number; del: number }[] = [];
    const cur = new Date(allDates[0] + 'T00:00:00Z');
    const end = new Date(allDates.at(-1)! + 'T00:00:00Z');
    while (cur <= end) {
      const d = cur.toISOString().slice(0, 10);
      days.push({ date: d, reg: regMap[d] ?? 0, del: delMap[d] ?? 0 });
      cur.setUTCDate(cur.getUTCDate() + 1);
    }
    return days;
  }

  const baseChart = (extra: object) => ({
    fontFamily: 'inherit',
    toolbar: { show: false },
    animations: { enabled: true, speed: 350, animateGradually: { enabled: false } },
    ...extra,
  });
  const xDateAxis = {
    type: 'datetime' as const,
    labels: { datetimeUTC: true, format: 'dd.MM' },
    axisBorder: { show: false },
    axisTicks: { show: false },
  };
  const gridOpts = { strokeDashArray: 4, borderColor: '#f0f0f0', xaxis: { lines: { show: false } } };
  const ttBase   = { theme: 'light' as const, x: { format: 'dd.MM.yyyy' } };

  // ── Chart 1 — Nutzerentwicklung ───────────────────────────────────────────
  $effect(() => {
    if (!apexLoaded || !el1 || !usersData) return;
    const data = usersData;
    const mode = chart1Mode;
    const days = buildUserDays(data);
    if (!days.length) return;

    let opts: object;
    if (mode === 'activity') {
      opts = {
        chart: baseChart({ type: 'bar', height: 240 }),
        series: [
          { name: 'Registrierungen', data: days.map(d => [ts(d.date), d.reg]) },
          { name: 'Löschungen',      data: days.map(d => [ts(d.date), -d.del]) },
        ],
        colors: ['#43a047', '#e53935'],
        dataLabels: { enabled: false },
        plotOptions: { bar: { borderRadius: 2, columnWidth: '70%' } },
        xaxis: xDateAxis,
        yaxis: { labels: { formatter: (v: number) => String(Math.abs(Math.round(v))) } },
        tooltip: { ...ttBase, y: { formatter: (v: number) => String(Math.abs(Math.round(v))) } },
        grid: gridOpts,
        legend: { position: 'top' as const, fontSize: '12px', fontWeight: 400 },
      };
    } else {
      let cum = data.base_count;
      const cumData = days.map(d => { cum += d.reg - d.del; return [ts(d.date), cum]; });
      opts = {
        chart: baseChart({ type: 'area', height: 240 }),
        series: [{ name: 'Nutzer gesamt', data: cumData }],
        colors: ['#e8500a'],
        dataLabels: { enabled: false },
        stroke: { curve: 'smooth' as const, width: 2 },
        fill: { type: 'gradient', gradient: { opacityFrom: 0.25, opacityTo: 0.02 } },
        xaxis: xDateAxis,
        tooltip: ttBase,
        grid: gridOpts,
        legend: { show: false },
      };
    }

    const chart = new Apex(el1, opts);
    chart.render();
    return () => chart.destroy();
  });

  // ── Chart 2 — Einträge pro Tag ────────────────────────────────────────────
  $effect(() => {
    if (!apexLoaded || !el2 || !entriesData || !entriesData.days.length) return;
    const { drinks, days } = entriesData;

    const chart = new Apex(el2, {
      chart: baseChart({ type: 'bar', stacked: true, height: 240 }),
      series: drinks.map(dr => ({
        name: dr.name,
        data: days.map(d => [ts(d.date), d.counts[String(dr.id)] ?? 0]),
      })),
      colors: drinks.map(dr => dr.color_hex),
      dataLabels: { enabled: false },
      plotOptions: { bar: { borderRadius: 0, columnWidth: '80%' } },
      xaxis: xDateAxis,
      tooltip: { ...ttBase, shared: true },
      grid: gridOpts,
      legend: { position: 'top' as const, fontSize: '12px', fontWeight: 400 },
    });
    chart.render();
    return () => chart.destroy();
  });

  // ── Chart 3 — Durchschnittspreise ─────────────────────────────────────────
  $effect(() => {
    if (!apexLoaded || !el3 || !pricesData || !pricesData.berlin.length) return;
    const { berlin, lor } = pricesData;
    const lorName = lors.find(l => l.lor_schluessel === selLor)?.pr_name ?? 'LOR';
    const series: { name: string; data: [number, number][] }[] = [
      { name: 'Berlin gesamt', data: berlin.map(p => [ts(p.date), +p.avg_price.toFixed(2)]) },
    ];
    if (selLor && lor.length) {
      series.push({ name: lorName, data: lor.map(p => [ts(p.date), +p.avg_price.toFixed(2)]) });
    }

    const chart = new Apex(el3, {
      chart: baseChart({ type: 'line', height: 240 }),
      series,
      colors: selLor ? ['#aaa', '#e8500a'] : ['#e8500a'],
      dataLabels: { enabled: false },
      stroke: { curve: 'smooth' as const, width: 2 },
      markers: { size: 4, hover: { size: 6 } },
      xaxis: xDateAxis,
      yaxis: { labels: { formatter: (v: number) => v.toFixed(2) + ' €' } },
      tooltip: { ...ttBase, y: { formatter: (v: number) => v.toFixed(2) + ' €' } },
      grid: gridOpts,
      legend: { show: series.length > 1, position: 'top' as const, fontSize: '12px', fontWeight: 400 },
    });
    chart.render();
    return () => chart.destroy();
  });

  // ── load functions ────────────────────────────────────────────────────────
  function fParams() {
    const p = new URLSearchParams({ granularity, year: String(selYear) });
    if (granularity === 'month') p.set('month', String(selMonth));
    return p.toString();
  }

  async function loadAll() {
    const q = fParams();
    usersData = null; errU = ''; loadingU = true;
    entriesData = null; errE = ''; loadingE = true;
    await Promise.all([
      api.get<UsersStats>(`/moderation/graph-users?${q}`)
        .then(d => { usersData = d; })
        .catch(e => { errU = e instanceof Error ? e.message : 'Fehler'; })
        .finally(() => { loadingU = false; }),
      api.get<EntriesStats>(`/moderation/graph-entries?${q}`)
        .then(d => { entriesData = d; })
        .catch(e => { errE = e instanceof Error ? e.message : 'Fehler'; })
        .finally(() => { loadingE = false; }),
      loadPrices(q),
    ]);
  }

  async function loadPrices(baseQ?: string) {
    const p = new URLSearchParams(baseQ ?? fParams());
    if (selLor) p.set('lor_schluessel', selLor);
    pricesData = null; errP = ''; loadingP = true;
    try { pricesData = await api.get<PricesStats>(`/moderation/graph-prices?${p}`); }
    catch (e) { errP = e instanceof Error ? e.message : 'Fehler'; }
    finally { loadingP = false; }
  }

  onMount(async () => {
    const m = await import('apexcharts');
    Apex = m.default;
    apexLoaded = true;
    lors = await api.get<LOR[]>('/moderation/lors').catch(() => []);
    loadingC = true;
    changes = await api.get<PriceChange[]>('/moderation/price-feed?limit=20').catch(() => []);
    loadingC = false;
    loadAll();
  });

  // ── Widget 4 actions ──────────────────────────────────────────────────────
  async function deleteEntry(id: number) {
    actionErr = '';
    try {
      await api.post('/moderation/entries/bulk-delete', { entry_ids: [id] });
      changes = changes.filter(c => c.entry_id !== id);
      expandedId = null;
    } catch (e) { actionErr = e instanceof Error ? e.message : 'Fehler'; }
  }

  async function suspendUser(uid: number) {
    actionErr = '';
    try {
      await api.patch(`/admin/users/${uid}/activate`, { is_active: false });
      expandedId = null;
    } catch (e) { actionErr = e instanceof Error ? e.message : 'Fehler'; }
  }

  function fmtDate(iso: string) {
    return new Date(iso).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
  }
</script>

<div class="dash">
  <h1 class="page-title">Dashboard</h1>

  <!-- Filter bar -->
  <div class="filter-bar">
    <div class="radio-group">
      <label class:active={granularity === 'month'}>
        <input type="radio" bind:group={granularity} value="month" /> Monat
      </label>
      <label class:active={granularity === 'year'}>
        <input type="radio" bind:group={granularity} value="year" /> Jahr
      </label>
    </div>
    {#if granularity === 'month'}
      <select bind:value={selMonth} class="f-sel">
        {#each MONTH_NAMES as name, i}
          <option value={i + 1}>{name}</option>
        {/each}
      </select>
    {/if}
    <select bind:value={selYear} class="f-sel">
      {#each YEARS as y}
        <option value={y}>{y}</option>
      {/each}
    </select>
    <button class="btn-primary" onclick={loadAll}>Laden</button>
  </div>

  <!-- 2×2 chart grid -->
  <div class="chart-grid">

    <!-- Chart 1: User development -->
    <div class="chart-box">
      <div class="chart-header">
        <span class="chart-title">Nutzerentwicklung</span>
        <div class="toggle-grp">
          <button class="tog" class:tog-active={chart1Mode === 'activity'}   onclick={() => chart1Mode = 'activity'}>Aktivität</button>
          <button class="tog" class:tog-active={chart1Mode === 'cumulative'} onclick={() => chart1Mode = 'cumulative'}>Kumuliert</button>
        </div>
      </div>
      {#if errU}
        <p class="cerr">{errU}</p>
      {:else if loadingU}
        <div class="chart-skeleton"></div>
      {:else if !usersData}
        <p class="cempty">Keine Daten im gewählten Zeitraum</p>
      {:else}
        <div bind:this={el1}></div>
      {/if}
    </div>

    <!-- Chart 2: Stacked entries -->
    <div class="chart-box">
      <div class="chart-header">
        <span class="chart-title">Einträge pro Tag</span>
      </div>
      {#if errE}
        <p class="cerr">{errE}</p>
      {:else if loadingE}
        <div class="chart-skeleton"></div>
      {:else if !entriesData || !entriesData.days.length}
        <p class="cempty">Keine Daten im gewählten Zeitraum</p>
      {:else}
        <div bind:this={el2}></div>
      {/if}
    </div>

    <!-- Chart 3: Average prices -->
    <div class="chart-box">
      <div class="chart-header">
        <span class="chart-title">Durchschnittspreise</span>
        <select bind:value={selLor} onchange={() => loadPrices()} class="f-sel f-sel-sm">
          <option value="">Berlin gesamt</option>
          {#each lors as lor}
            <option value={lor.lor_schluessel}>{lor.pr_name}</option>
          {/each}
        </select>
      </div>
      {#if errP}
        <p class="cerr">{errP}</p>
      {:else if loadingP}
        <div class="chart-skeleton"></div>
      {:else if !pricesData || !pricesData.berlin.length}
        <p class="cempty">Keine Daten im gewählten Zeitraum</p>
      {:else}
        <div bind:this={el3}></div>
      {/if}
    </div>

    <!-- Widget 4: Price change feed -->
    <div class="chart-box feed-box">
      <div class="chart-header">
        <span class="chart-title">Letzte Preisänderungen</span>
      </div>
      {#if actionErr}
        <p class="cerr">{actionErr}</p>
      {/if}
      {#if loadingC}
        <div class="chart-skeleton"></div>
      {:else if !changes.length}
        <p class="cempty">Keine Preisänderungen gefunden</p>
      {:else}
        <ul class="feed">
          {#each changes as c}
            <li class="feed-item" class:expanded={expandedId === c.entry_id}>
              <button class="feed-row" onclick={() => expandedId = expandedId === c.entry_id ? null : c.entry_id}>
                <span class="delta" class:delta-up={c.delta > 0} class:delta-down={c.delta < 0}>
                  {c.delta > 0 ? '▲' : '▼'} {c.delta > 0 ? '+' : ''}{c.delta.toFixed(2)} €
                </span>
                <span class="feed-info">
                  <span class="feed-loc">{c.location_name}</span>
                  <span class="feed-sub">{c.drink_name} · {c.prev_price.toFixed(2)} → {c.new_price.toFixed(2)} € · {c.username ?? '–'} · {fmtDate(c.reported_at)}</span>
                </span>
                <span class="feed-chevron">{expandedId === c.entry_id ? '▲' : '▼'}</span>
              </button>
              {#if expandedId === c.entry_id}
                <div class="feed-actions">
                  <button class="btn-danger-sm" onclick={() => deleteEntry(c.entry_id)}>Eintrag löschen</button>
                  {#if c.user_id}
                    <button class="btn-warn-sm" onclick={() => suspendUser(c.user_id!)}>Nutzer sperren</button>
                  {/if}
                </div>
              {/if}
            </li>
          {/each}
        </ul>
      {/if}
    </div>

  </div>
</div>

<style>
  .dash { max-width: 1140px; }

  .page-title {
    font-size: 1.5rem;
    font-weight: 700;
    color: #1a1a2e;
    margin: 0 0 1.25rem;
  }

  /* Filter bar */
  .filter-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem;
    background: white;
    padding: 0.75rem 1rem;
    border-radius: 10px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    margin-bottom: 1.25rem;
  }

  .radio-group {
    display: flex;
    border: 1px solid #ddd;
    border-radius: 6px;
    overflow: hidden;
  }
  .radio-group label {
    padding: 0.35rem 0.75rem;
    font-size: 0.85rem;
    cursor: pointer;
    background: white;
    color: #555;
    transition: background 0.15s;
  }
  .radio-group label.active { background: #e8500a; color: white; }
  .radio-group input { display: none; }

  .f-sel {
    padding: 0.35rem 0.5rem;
    border: 1px solid #ddd;
    border-radius: 6px;
    font-size: 0.85rem;
    background: white;
    color: #333;
  }
  .f-sel-sm { max-width: 160px; }

  .btn-primary {
    padding: 0.35rem 0.9rem;
    background: #e8500a;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
  }
  .btn-primary:hover { background: #c93e00; }

  /* Grid */
  .chart-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.25rem;
  }
  @media (max-width: 720px) {
    .chart-grid { grid-template-columns: 1fr; }
  }

  .chart-box {
    background: white;
    border-radius: 10px;
    padding: 1.1rem 1.25rem 0.75rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    min-width: 0;
  }

  .chart-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    margin-bottom: 0.6rem;
    flex-wrap: wrap;
  }

  .chart-title {
    font-size: 0.78rem;
    font-weight: 600;
    color: #666;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  /* Toggle */
  .toggle-grp {
    display: flex;
    border: 1px solid #ddd;
    border-radius: 6px;
    overflow: hidden;
  }
  .tog {
    padding: 0.25rem 0.6rem;
    font-size: 0.78rem;
    background: white;
    border: none;
    cursor: pointer;
    color: #666;
  }
  .tog-active { background: #1a1a2e; color: white; }

  /* Skeleton loader */
  .chart-skeleton {
    height: 240px;
    border-radius: 6px;
    background: linear-gradient(90deg, #f5f5f5 25%, #ebebeb 50%, #f5f5f5 75%);
    background-size: 200% 100%;
    animation: shimmer 1.4s infinite;
  }
  @keyframes shimmer {
    0%   { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }

  /* Feed */
  .feed-box { display: flex; flex-direction: column; }
  .feed {
    list-style: none;
    margin: 0; padding: 0;
    overflow-y: auto;
    max-height: 280px;
  }
  .feed-item { border-bottom: 1px solid #f0f0f0; }
  .feed-item:last-child { border-bottom: none; }
  .feed-item.expanded { background: #fafafa; }

  .feed-row {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
    width: 100%;
    background: none;
    border: none;
    cursor: pointer;
    padding: 0.5rem 0.25rem;
    text-align: left;
  }
  .feed-row:hover { background: #f5f5f5; }

  .delta {
    font-size: 0.8rem;
    font-weight: 700;
    white-space: nowrap;
    min-width: 70px;
    padding-top: 1px;
  }
  .delta-up   { color: #43a047; }
  .delta-down { color: #e53935; }

  .feed-info {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 1px;
    min-width: 0;
  }
  .feed-loc {
    font-size: 0.83rem;
    font-weight: 600;
    color: #333;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .feed-sub {
    font-size: 0.75rem;
    color: #888;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .feed-chevron { font-size: 0.65rem; color: #bbb; padding-top: 3px; }

  .feed-actions {
    display: flex;
    gap: 0.5rem;
    padding: 0.4rem 0.25rem 0.5rem;
  }
  .btn-danger-sm {
    padding: 0.3rem 0.7rem;
    background: #d32f2f;
    color: white;
    border: none;
    border-radius: 5px;
    font-size: 0.78rem;
    font-weight: 600;
    cursor: pointer;
  }
  .btn-danger-sm:hover { background: #b71c1c; }

  .btn-warn-sm {
    padding: 0.3rem 0.7rem;
    background: #f57c00;
    color: white;
    border: none;
    border-radius: 5px;
    font-size: 0.78rem;
    font-weight: 600;
    cursor: pointer;
  }
  .btn-warn-sm:hover { background: #e65100; }

  /* States */
  .cerr   { color: #c00; font-size: 0.82rem; padding: 0.5rem 0; }
  .cempty { color: #aaa; font-size: 0.82rem; padding: 0.5rem 0; }
</style>
