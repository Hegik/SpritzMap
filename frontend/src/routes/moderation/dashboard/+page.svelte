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
  let selYear = $state(NOW.getFullYear());
  let selMonth = $state(NOW.getMonth() + 1);

  // ── data ──────────────────────────────────────────────────────────────────
  let usersData  = $state<UsersStats | null>(null);
  let entriesData = $state<EntriesStats | null>(null);
  let pricesData = $state<PricesStats | null>(null);
  let lors       = $state<LOR[]>([]);
  let changes    = $state<PriceChange[]>([]);
  let selLor     = $state('');

  let loadingU = $state(false); let errU = $state('');
  let loadingE = $state(false); let errE = $state('');
  let loadingP = $state(false); let errP = $state('');
  let loadingC = $state(false);

  let chart1Mode = $state<'activity' | 'cumulative'>('activity');
  let expandedId = $state<number | null>(null);
  let actionErr  = $state('');

  // ── helpers ───────────────────────────────────────────────────────────────
  function fParams() {
    const p = new URLSearchParams({ granularity, year: String(selYear) });
    if (granularity === 'month') p.set('month', String(selMonth));
    return p.toString();
  }

  async function loadAll() {
    const q = fParams();
    loadingU = true; errU = '';
    loadingE = true; errE = '';
    await Promise.all([
      api.get<UsersStats>(`/moderation/charts/users?${q}`)
        .then(d => { usersData = d; })
        .catch(e => { errU = e instanceof Error ? e.message : 'Fehler'; })
        .finally(() => { loadingU = false; }),
      api.get<EntriesStats>(`/moderation/charts/entries?${q}`)
        .then(d => { entriesData = d; })
        .catch(e => { errE = e instanceof Error ? e.message : 'Fehler'; })
        .finally(() => { loadingE = false; }),
      loadPrices(q),
    ]);
  }

  async function loadPrices(baseQ?: string) {
    const p = new URLSearchParams(baseQ ?? fParams());
    if (selLor) p.set('lor_schluessel', selLor);
    loadingP = true; errP = '';
    try { pricesData = await api.get<PricesStats>(`/moderation/charts/prices?${p}`); }
    catch (e) { errP = e instanceof Error ? e.message : 'Fehler'; }
    finally { loadingP = false; }
  }

  onMount(async () => {
    lors = await api.get<LOR[]>('/moderation/charts/lors').catch(() => []);
    loadingC = true;
    changes = await api.get<PriceChange[]>('/moderation/charts/price-changes?limit=20').catch(() => []);
    loadingC = false;
    loadAll();
  });

  // ── SVG layout constants ──────────────────────────────────────────────────
  const W = 500; const H = 170;
  const PL = 42; const PT = 8; const PB = 22;
  const CW = W - PL;
  const CH = H - PT - PB;

  // ── Chart 1 ───────────────────────────────────────────────────────────────
  const c1 = $derived.by(() => {
    if (!usersData) return null;
    const { registrations, deletions, base_count } = usersData;
    const regMap = Object.fromEntries(registrations.map(r => [r.date, r.count]));
    const delMap = Object.fromEntries(deletions.map(d => [d.date, d.count]));

    const allDates = [
      ...registrations.map(r => r.date),
      ...deletions.map(d => d.date),
    ].sort();
    if (!allDates.length) return { days: [] as ReturnType<typeof buildDays>, actBars: [], cumPts: [], cumLine: '', zeroY: 0, yLabels: [] };

    function buildDays() {
      const days: { date: string; reg: number; del: number; cum: number }[] = [];
      let cum = base_count;
      const cur = new Date(allDates[0] + 'T00:00:00Z');
      const end = new Date(allDates[allDates.length - 1] + 'T00:00:00Z');
      while (cur <= end) {
        const d = cur.toISOString().slice(0, 10);
        const reg = regMap[d] ?? 0;
        const del = delMap[d] ?? 0;
        cum += reg - del;
        days.push({ date: d, reg, del, cum });
        cur.setUTCDate(cur.getUTCDate() + 1);
      }
      return days;
    }

    const days = buildDays();
    const n = days.length;
    const maxVal = Math.max(...days.map(d => Math.max(d.reg, d.del)), 1);
    const minCum = Math.min(...days.map(d => d.cum));
    const maxCum = Math.max(...days.map(d => d.cum), minCum + 1);
    const cumRng = maxCum - minCum;
    const bw = Math.max(1.5, CW / n - 0.5);
    const xOf = (i: number) => PL + i * (CW / n);
    const zeroY = PT + CH / 2;

    const actBars = days.map((d, i) => ({
      x: xOf(i), bw,
      regY: zeroY - (d.reg / maxVal) * (CH / 2),
      regH: (d.reg / maxVal) * (CH / 2),
      delH: (d.del / maxVal) * (CH / 2),
      date: d.date, reg: d.reg, del: d.del,
    }));

    const cumPts = days.map((d, i) => ({
      x: n > 1 ? PL + (i / (n - 1)) * CW : PL + CW / 2,
      y: PT + (1 - (d.cum - minCum) / cumRng) * CH,
      date: d.date, count: d.cum,
    }));

    const yLabels = [
      { v: maxCum, y: PT + 4 },
      { v: Math.round((maxCum + minCum) / 2), y: PT + CH / 2 + 4 },
      { v: minCum, y: PT + CH + 2 },
    ];

    return {
      days, actBars, zeroY, yLabels,
      cumPts, cumLine: cumPts.map(p => `${p.x},${p.y}`).join(' '),
    };
  });

  // ── Chart 2 ───────────────────────────────────────────────────────────────
  const c2 = $derived.by(() => {
    if (!entriesData || !entriesData.days.length) return null;
    const { drinks, days } = entriesData;
    const maxTotal = Math.max(...days.map(d => Object.values(d.counts).reduce((a, b) => a + b, 0)), 1);
    const n = days.length;
    const bw = Math.max(1.5, CW / n - 0.5);
    const bars = days.map((day, i) => {
      const x = PL + i * (CW / n);
      let yOff = PT + CH;
      const segs = drinks
        .filter(dr => (day.counts[String(dr.id)] ?? 0) > 0)
        .map(dr => {
          const cnt = day.counts[String(dr.id)];
          const h = (cnt / maxTotal) * CH;
          yOff -= h;
          return { y: yOff, h, color: dr.color_hex, name: dr.name, cnt };
        });
      const total = Object.values(day.counts).reduce((a, b) => a + b, 0);
      return { x, bw, segs, date: day.date, total };
    });
    return { bars, drinks, maxTotal };
  });

  // ── Chart 3 ───────────────────────────────────────────────────────────────
  const c3 = $derived.by(() => {
    if (!pricesData || !pricesData.berlin.length) return null;
    const { berlin, lor } = pricesData;
    const allP = [...berlin.map(p => p.avg_price), ...lor.map(p => p.avg_price)];
    const minP = Math.min(...allP) * 0.95;
    const maxP = Math.max(...allP) * 1.05;
    const rng = maxP - minP || 1;
    const allDates = [...new Set([...berlin.map(p => p.date), ...lor.map(p => p.date)])].sort();
    const n = allDates.length;
    if (!n) return null;
    const xOf = (i: number) => n > 1 ? PL + (i / (n - 1)) * CW : PL + CW / 2;
    const yOf = (p: number) => PT + (1 - (p - minP) / rng) * CH;
    const bMap = Object.fromEntries(berlin.map(p => [p.date, p.avg_price]));
    const lMap = Object.fromEntries(lor.map(p => [p.date, p.avg_price]));
    type Pt = { x: number; y: number; p: number; date: string };
    const bPts = allDates.map((d, i) => bMap[d] != null ? { x: xOf(i), y: yOf(bMap[d]), p: bMap[d], date: d } : null).filter(Boolean) as Pt[];
    const lPts = allDates.map((d, i) => lMap[d] != null ? { x: xOf(i), y: yOf(lMap[d]), p: lMap[d], date: d } : null).filter(Boolean) as Pt[];
    const yLbls = [maxP, (maxP + minP) / 2, minP].map(v => ({ v: v.toFixed(2), y: yOf(v) }));
    const xLbls = n > 1
      ? [0, Math.floor((n - 1) / 2), n - 1].map(i => ({ l: allDates[i].slice(5), x: xOf(i) }))
      : [{ l: allDates[0].slice(5), x: xOf(0) }];
    return { bPts, lPts, bLine: bPts.map(p => `${p.x},${p.y}`).join(' '), lLine: lPts.map(p => `${p.x},${p.y}`).join(' '), yLbls, xLbls };
  });

  // ── Widget 4 ──────────────────────────────────────────────────────────────
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
          <button class="tog" class:tog-active={chart1Mode === 'activity'} onclick={() => chart1Mode = 'activity'}>Aktivität</button>
          <button class="tog" class:tog-active={chart1Mode === 'cumulative'} onclick={() => chart1Mode = 'cumulative'}>Kumuliert</button>
        </div>
      </div>
      {#if errU}
        <p class="cerr">{errU}</p>
      {:else if loadingU}
        <p class="cload">Lade…</p>
      {:else if !c1 || !c1.days.length}
        <p class="cempty">Keine Daten im gewählten Zeitraum</p>
      {:else}
        <svg viewBox="0 0 {W} {H}" class="svg">
          <!-- y-axis labels -->
          {#each c1.yLabels as lbl}
            <text x={PL - 4} y={lbl.y} text-anchor="end" font-size="10" fill="#aaa">{lbl.v}</text>
          {/each}
          <!-- baseline -->
          <line x1={PL} y1={PT + CH} x2={W} y2={PT + CH} stroke="#e0e0e0" stroke-width="1" />

          {#if chart1Mode === 'activity'}
            <line x1={PL} y1={c1.zeroY} x2={W} y2={c1.zeroY} stroke="#ddd" stroke-width="1" stroke-dasharray="4,3" />
            {#each c1.actBars as b}
              {#if b.regH > 0.5}
                <rect x={b.x} y={b.regY} width={b.bw} height={b.regH} fill="#43a047" opacity="0.8">
                  <title>{b.date}: +{b.reg} Registrierungen</title>
                </rect>
              {/if}
              {#if b.delH > 0.5}
                <rect x={b.x} y={c1.zeroY} width={b.bw} height={b.delH} fill="#e53935" opacity="0.8">
                  <title>{b.date}: -{b.del} Löschungen</title>
                </rect>
              {/if}
            {/each}
          {:else}
            {#if c1.cumPts.length > 1}
              <polyline points={c1.cumLine} fill="none" stroke="#e8500a" stroke-width="2" stroke-linejoin="round" />
            {/if}
            {#each c1.cumPts as p}
              <circle cx={p.x} cy={p.y} r="2" fill="#e8500a">
                <title>{p.date}: {p.count}</title>
              </circle>
            {/each}
          {/if}
        </svg>
        {#if chart1Mode === 'activity'}
          <div class="legend">
            <span class="l-dot" style="background:#43a047"></span><span class="l-lbl">Registrierungen</span>
            <span class="l-dot" style="background:#e53935"></span><span class="l-lbl">Löschungen</span>
          </div>
        {/if}
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
        <p class="cload">Lade…</p>
      {:else if !c2}
        <p class="cempty">Keine Daten im gewählten Zeitraum</p>
      {:else}
        <svg viewBox="0 0 {W} {H}" class="svg">
          <text x={PL - 4} y={PT + 10} text-anchor="end" font-size="10" fill="#aaa">{c2.maxTotal}</text>
          <line x1={PL} y1={PT + CH} x2={W} y2={PT + CH} stroke="#e0e0e0" stroke-width="1" />
          {#each c2.bars as b}
            {#each b.segs as s}
              <rect x={b.x} y={s.y} width={b.bw} height={s.h} fill={s.color} opacity="0.85">
                <title>{b.date} · {s.name}: {s.cnt}</title>
              </rect>
            {/each}
          {/each}
        </svg>
        <div class="legend">
          {#each c2.drinks as dr}
            <span class="l-dot" style="background:{dr.color_hex}"></span>
            <span class="l-lbl">{dr.name}</span>
          {/each}
        </div>
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
        <p class="cload">Lade…</p>
      {:else if !c3}
        <p class="cempty">Keine Daten im gewählten Zeitraum</p>
      {:else}
        <svg viewBox="0 0 {W} {H}" class="svg">
          {#each c3.yLbls as lbl}
            <line x1={PL} y1={lbl.y} x2={W} y2={lbl.y} stroke="#f0f0f0" stroke-width="1" />
            <text x={PL - 4} y={lbl.y + 4} text-anchor="end" font-size="10" fill="#aaa">{lbl.v}</text>
          {/each}
          {#each c3.xLbls as lbl}
            <text x={lbl.x} y={H - 4} text-anchor="middle" font-size="10" fill="#bbb">{lbl.l}</text>
          {/each}
          {#if c3.bLine}
            <polyline points={c3.bLine} fill="none" stroke="#bbb" stroke-width="2" stroke-linejoin="round" />
          {/if}
          {#each c3.bPts as p}
            <circle cx={p.x} cy={p.y} r="2.5" fill="#bbb">
              <title>Berlin {p.date}: {p.p.toFixed(2)} €</title>
            </circle>
          {/each}
          {#if c3.lLine && selLor}
            <polyline points={c3.lLine} fill="none" stroke="#e8500a" stroke-width="2" stroke-linejoin="round" />
            {#each c3.lPts as p}
              <circle cx={p.x} cy={p.y} r="2.5" fill="#e8500a">
                <title>LOR {p.date}: {p.p.toFixed(2)} €</title>
              </circle>
            {/each}
          {/if}
        </svg>
        <div class="legend">
          <span class="l-dot" style="background:#bbb"></span><span class="l-lbl">Berlin gesamt</span>
          {#if selLor}
            <span class="l-dot" style="background:#e8500a"></span>
            <span class="l-lbl">{lors.find(l => l.lor_schluessel === selLor)?.pr_name ?? 'LOR'}</span>
          {/if}
        </div>
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
        <p class="cload">Lade…</p>
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
    gap: 0;
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

  /* SVG */
  .svg {
    width: 100%;
    height: auto;
    display: block;
  }

  /* Legend */
  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem 0.75rem;
    margin-top: 0.4rem;
    align-items: center;
  }
  .l-dot {
    display: inline-block;
    width: 10px; height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .l-lbl { font-size: 0.78rem; color: #666; }

  /* Feed */
  .feed-box { display: flex; flex-direction: column; }
  .feed {
    list-style: none;
    margin: 0; padding: 0;
    overflow-y: auto;
    max-height: 280px;
  }
  .feed-item {
    border-bottom: 1px solid #f0f0f0;
  }
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
  .delta-up { color: #43a047; }
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
  .feed-chevron {
    font-size: 0.65rem;
    color: #bbb;
    padding-top: 3px;
  }

  .feed-actions {
    display: flex;
    gap: 0.5rem;
    padding: 0.4rem 0.25rem 0.5rem 0.25rem;
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
  .cload  { color: #aaa; font-size: 0.82rem; padding: 0.5rem 0; }
  .cempty { color: #aaa; font-size: 0.82rem; padding: 0.5rem 0; }
</style>
