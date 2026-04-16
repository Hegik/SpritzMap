<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api/client';

  // ── types ─────────────────────────────────────────────────────────────────
  interface DayCount  { date: string; count: number }
  interface GroupMeta { id: string; name: string; color_hex: string }
  interface UsersStats   { registrations: DayCount[]; deletions: DayCount[]; base_count: number }
  interface EntriesStats { groups: GroupMeta[]; days: { date: string; counts: Record<string, number> }[] }
  interface DayPrice     { date: string; avg_price: number; min_price: number; max_price: number }
  interface PricesStats  { berlin: DayPrice[]; lor: DayPrice[] }
  interface LOR          { lor_schluessel: string; pr_name: string }
  interface DrinkMeta    { id: number; name: string; color_hex: string }
  interface DrinkTrendsStats { drinks: DrinkMeta[]; days: { date: string; prices: Record<string, number> }[] }
  interface HistogramBucket  { bucket_start: number; label: string; counts: Record<string, number> }
  interface HistogramStats   { drinks: DrinkMeta[]; buckets: HistogramBucket[] }
  interface ModerationActStats { days: { date: string; counts: Record<string, number> }[]; actions: string[] }
  interface TopLocation  { location_name: string; entry_count: number; avg_price: number }
  interface FreshnessItem { label: string; count: number }
  interface HeatmapRow   { dow: number; hour: number; count: number }
  interface LocationTypeItem { location_type: string; label: string; color_hex: string; count: number; avg_price: number }
  interface PriceChange {
    entry_id: number; location_name: string; drink_name: string;
    new_price: number; prev_price: number; delta: number;
    reported_at: string; username: string | null; user_id: number | null;
  }

  // ── filter state ──────────────────────────────────────────────────────────
  const NOW = new Date();
  const YEARS = Array.from({ length: 4 }, (_, i) => NOW.getFullYear() - i);
  const MONTH_NAMES = ['Januar','Februar','März','April','Mai','Juni','Juli','August','September','Oktober','November','Dezember'];

  let granularity  = $state<'year' | 'month'>('month');
  let selYear      = $state(NOW.getFullYear());
  let selMonth     = $state(NOW.getMonth() + 1);

  // ── data state ────────────────────────────────────────────────────────────
  // time-filtered
  let usersData      = $state<UsersStats | null>(null);
  let entriesData    = $state<EntriesStats | null>(null);
  let pricesData     = $state<PricesStats | null>(null);
  let drinkTrends    = $state<DrinkTrendsStats | null>(null);
  let modActData     = $state<ModerationActStats | null>(null);
  // all-time
  let histogramData  = $state<HistogramStats | null>(null);
  let topLocations   = $state<TopLocation[] | null>(null);
  let freshnessData  = $state<FreshnessItem[] | null>(null);
  let heatmapRaw     = $state<HeatmapRow[] | null>(null);
  let locTypesData   = $state<LocationTypeItem[] | null>(null);
  // aux
  let lors           = $state<LOR[]>([]);
  let drinks         = $state<DrinkMeta[]>([]);
  let changes        = $state<PriceChange[]>([]);

  // UI controls
  let selLor           = $state('');
  let selPriceDrink    = $state('');   // drink filter for avg-prices chart
  let selHistDrink     = $state('');   // drink filter for histogram
  let entriesGroupBy   = $state<'drink' | 'location_type'>('drink');
  let chart1Mode       = $state<'activity' | 'cumulative'>('activity');
  let expandedId       = $state<number | null>(null);
  let actionErr        = $state('');

  // loading / error state
  let loadingU  = $state(false); let errU  = $state('');
  let loadingE  = $state(false); let errE  = $state('');
  let loadingP  = $state(false); let errP  = $state('');
  let loadingDT = $state(false); let errDT = $state('');
  let loadingMA = $state(false); let errMA = $state('');
  let loadingC  = $state(false);

  // ── ApexCharts ────────────────────────────────────────────────────────────
  let Apex: any;
  let apexLoaded = $state(false);
  // chart container refs — $state so effects track mount/unmount
  let el1  = $state<HTMLDivElement | undefined>(undefined);
  let el2  = $state<HTMLDivElement | undefined>(undefined);
  let el3  = $state<HTMLDivElement | undefined>(undefined);
  let el4  = $state<HTMLDivElement | undefined>(undefined); // drink trends
  let el5  = $state<HTMLDivElement | undefined>(undefined); // histogram
  let el6  = $state<HTMLDivElement | undefined>(undefined); // mod activity
  let el7  = $state<HTMLDivElement | undefined>(undefined); // top locations
  let el8  = $state<HTMLDivElement | undefined>(undefined); // freshness donut
  let el9  = $state<HTMLDivElement | undefined>(undefined); // heatmap
  let el10 = $state<HTMLDivElement | undefined>(undefined); // location types

  // ── helpers ───────────────────────────────────────────────────────────────
  const ts = (d: string) => new Date(d + 'T00:00:00Z').getTime();

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
  const gridOpts  = { strokeDashArray: 4, borderColor: '#f0f0f0', xaxis: { lines: { show: false } } };
  const ttBase    = { theme: 'light' as const, x: { format: 'dd.MM.yyyy' }, intersect: false };
  const ttMoney   = { ...ttBase, y: { formatter: (v: number) => v.toFixed(2) + ' €' } };

  function buildUserDays(data: UsersStats) {
    const regMap = Object.fromEntries(data.registrations.map(r => [r.date, r.count]));
    const delMap = Object.fromEntries(data.deletions.map(d => [d.date, d.count]));
    const allDates = [...new Set([...data.registrations.map(r => r.date), ...data.deletions.map(d => d.date)])].sort();
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
          { name: 'Registrierungen', data: days.map(d => d.reg) },
          { name: 'Löschungen',      data: days.map(d => -d.del) },
        ],
        colors: ['#43a047', '#e53935'],
        dataLabels: { enabled: false },
        plotOptions: { bar: { borderRadius: 2, columnWidth: '70%' } },
        xaxis: { ...xDateAxis, categories: days.map(d => ts(d.date)) },
        yaxis: { labels: { formatter: (v: number) => String(Math.abs(Math.round(v))) } },
        tooltip: { ...ttBase, shared: true, y: { formatter: (v: number) => String(Math.abs(Math.round(v))) } },
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
    const { groups, days } = entriesData;
    const chart = new Apex(el2, {
      chart: baseChart({ type: 'bar', stacked: true, height: 240 }),
      series: groups.map(g => ({
        name: g.name,
        data: days.map(d => d.counts[g.id] ?? 0),
      })),
      colors: groups.map(g => g.color_hex),
      dataLabels: { enabled: false },
      plotOptions: { bar: { borderRadius: 0, columnWidth: '80%' } },
      xaxis: { ...xDateAxis, categories: days.map(d => ts(d.date)) },
      tooltip: { ...ttBase, shared: true },
      grid: gridOpts,
      legend: { position: 'top' as const, fontSize: '12px', fontWeight: 400 },
    });
    chart.render();
    return () => chart.destroy();
  });

  // ── Chart 3 — Durchschnittspreise mit Min/Max-Band ────────────────────────
  $effect(() => {
    if (!apexLoaded || !el3 || !pricesData || !pricesData.berlin.length) return;
    const { berlin, lor } = pricesData;
    const lorName = lors.find(l => l.lor_schluessel === selLor)?.pr_name ?? 'LOR';

    const series: any[] = [
      {
        name: 'Preisspanne Berlin',
        type: 'rangeArea',
        data: berlin.map(p => ({ x: ts(p.date), y: [+p.min_price.toFixed(2), +p.max_price.toFixed(2)] })),
      },
      {
        name: 'Ø Berlin',
        type: 'line',
        data: berlin.map(p => [ts(p.date), +p.avg_price.toFixed(2)]),
      },
    ];
    if (selLor && lor.length) {
      series.push({
        name: `Preisspanne ${lorName}`,
        type: 'rangeArea',
        data: lor.map(p => ({ x: ts(p.date), y: [+p.min_price.toFixed(2), +p.max_price.toFixed(2)] })),
      });
      series.push({
        name: `Ø ${lorName}`,
        type: 'line',
        data: lor.map(p => [ts(p.date), +p.avg_price.toFixed(2)]),
      });
    }

    const baseColors = selLor ? ['#aaa', '#777', '#e8500a', '#c93e00'] : ['#aaa', '#555'];
    const chart = new Apex(el3, {
      chart: baseChart({ type: 'line', height: 240 }),
      series,
      colors: baseColors,
      dataLabels: { enabled: false },
      stroke: { curve: 'smooth' as const, width: series.map((s: any) => s.type === 'line' ? 2 : 0) },
      fill: { opacity: series.map((s: any) => s.type === 'rangeArea' ? 0.15 : 1) },
      markers: { size: series.map((s: any) => s.type === 'line' ? 3 : 0), hover: { size: 5 } },
      xaxis: xDateAxis,
      yaxis: { labels: { formatter: (v: number) => v.toFixed(2) + ' €' } },
      tooltip: { ...ttMoney, shared: false },
      grid: gridOpts,
      legend: { position: 'top' as const, fontSize: '12px', fontWeight: 400 },
    });
    chart.render();
    return () => chart.destroy();
  });

  // ── Chart 4 — Preisverlauf pro Sorte ─────────────────────────────────────
  $effect(() => {
    if (!apexLoaded || !el4 || !drinkTrends || !drinkTrends.days.length) return;
    const { drinks: dks, days } = drinkTrends;
    const chart = new Apex(el4, {
      chart: baseChart({ type: 'line', height: 260 }),
      series: dks.map(dr => ({
        name: dr.name,
        data: days.map(d => [ts(d.date), d.prices[String(dr.id)] != null ? +d.prices[String(dr.id)].toFixed(2) : null]),
      })),
      colors: dks.map(dr => dr.color_hex),
      dataLabels: { enabled: false },
      stroke: { curve: 'smooth' as const, width: 2 },
      markers: { size: 3, hover: { size: 5 } },
      xaxis: xDateAxis,
      yaxis: { labels: { formatter: (v: number) => v.toFixed(2) + ' €' } },
      tooltip: { ...ttMoney, shared: true },
      grid: gridOpts,
      legend: { position: 'top' as const, fontSize: '12px', fontWeight: 400 },
    });
    chart.render();
    return () => chart.destroy();
  });

  // ── Chart 5 — Preisverteilung Histogramm ──────────────────────────────────
  $effect(() => {
    if (!apexLoaded || !el5 || !histogramData || !histogramData.buckets.length) return;
    const { drinks: dks, buckets } = histogramData;
    const drinkId = selHistDrink;

    let series: any[];
    let colors: string[];

    if (drinkId) {
      const dr = dks.find(d => String(d.id) === drinkId);
      series = [{
        name: dr?.name ?? 'Sorte',
        data: buckets.map(b => b.counts[drinkId] ?? 0),
      }];
      colors = [dr?.color_hex ?? '#e8500a'];
    } else {
      series = dks.map(dr => ({
        name: dr.name,
        data: buckets.map(b => b.counts[String(dr.id)] ?? 0),
      }));
      colors = dks.map(dr => dr.color_hex);
    }

    const chart = new Apex(el5, {
      chart: baseChart({ type: 'bar', stacked: true, height: 240 }),
      series,
      colors,
      dataLabels: { enabled: false },
      plotOptions: { bar: { borderRadius: 2, columnWidth: '90%' } },
      xaxis: { categories: buckets.map(b => b.label), labels: { rotate: -45, style: { fontSize: '10px' } } },
      tooltip: { ...ttBase, x: { formatter: (_: any, opts: any) => buckets[opts.dataPointIndex]?.label ?? '' } },
      grid: gridOpts,
      legend: { position: 'top' as const, fontSize: '12px', fontWeight: 400 },
    });
    chart.render();
    return () => chart.destroy();
  });

  // ── Chart 6 — Moderationsaktivität ───────────────────────────────────────
  $effect(() => {
    if (!apexLoaded || !el6 || !modActData || !modActData.days.length) return;
    const { days, actions } = modActData;
    const ACTION_COLORS: Record<string, string> = {
      created: '#90a4ae', updated: '#42a5f5', confirmed: '#66bb6a',
      flagged: '#ffa726', deleted: '#ef5350',
    };
    const ACTION_LABELS: Record<string, string> = {
      created: 'Erstellt', updated: 'Aktualisiert', confirmed: 'Bestätigt',
      flagged: 'Markiert', deleted: 'Gelöscht',
    };
    const chart = new Apex(el6, {
      chart: baseChart({ type: 'bar', stacked: true, height: 240 }),
      series: actions.map(a => ({
        name: ACTION_LABELS[a] ?? a,
        data: days.map(d => d.counts[a] ?? 0),
      })),
      colors: actions.map(a => ACTION_COLORS[a] ?? '#999'),
      dataLabels: { enabled: false },
      plotOptions: { bar: { borderRadius: 0, columnWidth: '80%' } },
      xaxis: { ...xDateAxis, categories: days.map(d => ts(d.date)) },
      tooltip: { ...ttBase, shared: true },
      grid: gridOpts,
      legend: { position: 'top' as const, fontSize: '12px', fontWeight: 400 },
    });
    chart.render();
    return () => chart.destroy();
  });

  // ── Chart 7 — Top-Standorte ────────────────────────────────────────────────
  $effect(() => {
    if (!apexLoaded || !el7 || !topLocations || !topLocations.length) return;
    const sorted = [...topLocations].sort((a, b) => a.entry_count - b.entry_count);
    const chart = new Apex(el7, {
      chart: baseChart({ type: 'bar', height: Math.max(280, sorted.length * 28) }),
      series: [{ name: 'Einträge', data: sorted.map(l => l.entry_count) }],
      colors: ['#e8500a'],
      dataLabels: { enabled: false },
      plotOptions: { bar: { horizontal: true, borderRadius: 3 } },
      xaxis: { labels: { style: { fontSize: '11px' } } },
      yaxis: { labels: { style: { fontSize: '11px' }, maxWidth: 200 } },
      categories: sorted.map(l => l.location_name),
      xaxis2: { categories: sorted.map(l => l.location_name) },
      tooltip: {
        theme: 'light' as const,
        intersect: false,
        y: {
          formatter: (v: number, opts: any) => {
            const loc = sorted[opts.dataPointIndex];
            return `${v} Einträge  ·  Ø ${loc?.avg_price.toFixed(2)} €`;
          },
        },
      },
      grid: { ...gridOpts, xaxis: { lines: { show: true } }, yaxis: { lines: { show: false } } },
      legend: { show: false },
    });
    chart.render();
    return () => chart.destroy();
  });

  // ── Chart 8 — Freshness Donut ─────────────────────────────────────────────
  $effect(() => {
    if (!apexLoaded || !el8 || !freshnessData) return;
    const data = freshnessData.filter(f => f.count > 0);
    if (!data.length) return;
    const chart = new Apex(el8, {
      chart: baseChart({ type: 'donut', height: 240 }),
      series: data.map(f => f.count),
      labels: data.map(f => f.label),
      colors: ['#43a047', '#1976d2', '#ffa000', '#d32f2f'],
      dataLabels: { enabled: true, formatter: (val: number) => val.toFixed(1) + '%' },
      tooltip: { theme: 'light' as const, y: { formatter: (v: number) => v + ' Einträge' } },
      legend: { position: 'bottom' as const, fontSize: '12px' },
      plotOptions: { pie: { donut: { size: '65%' } } },
    });
    chart.render();
    return () => chart.destroy();
  });

  // ── Chart 9 — Wochentag × Stunde Heatmap ─────────────────────────────────
  $effect(() => {
    if (!apexLoaded || !el9 || !heatmapRaw) return;
    const DOW_NAMES = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
    const DOW_ORDER = [1, 2, 3, 4, 5, 6, 0];
    const cellMap: Record<number, Record<number, number>> = {};
    for (const row of heatmapRaw) {
      if (!cellMap[row.dow]) cellMap[row.dow] = {};
      cellMap[row.dow][row.hour] = row.count;
    }
    const series = DOW_ORDER.map((dow, i) => ({
      name: DOW_NAMES[i],
      data: Array.from({ length: 24 }, (_, h) => ({ x: String(h) + ':00', y: cellMap[dow]?.[h] ?? 0 })),
    }));
    const chart = new Apex(el9, {
      chart: baseChart({ type: 'heatmap', height: 220 }),
      series,
      dataLabels: { enabled: false },
      colors: ['#e8500a'],
      xaxis: { labels: { style: { fontSize: '10px' } } },
      tooltip: {
        theme: 'light' as const,
        y: { formatter: (v: number) => v + ' Einträge' },
      },
      grid: { padding: { right: 0 } },
      legend: { show: false },
    });
    chart.render();
    return () => chart.destroy();
  });

  // ── Chart 10 — Standorttypen Donut ───────────────────────────────────────
  $effect(() => {
    if (!apexLoaded || !el10 || !locTypesData || !locTypesData.length) return;
    const data = locTypesData;
    const chart = new Apex(el10, {
      chart: baseChart({ type: 'donut', height: 240 }),
      series: data.map(d => d.count),
      labels: data.map(d => d.label),
      colors: data.map(d => d.color_hex),
      dataLabels: { enabled: true, formatter: (val: number) => val.toFixed(1) + '%' },
      tooltip: {
        theme: 'light' as const,
        y: {
          formatter: (v: number, opts: any) => {
            const item = data[opts.dataPointIndex];
            return `${v} Einträge  ·  Ø ${item?.avg_price.toFixed(2)} €`;
          },
        },
      },
      legend: { position: 'bottom' as const, fontSize: '12px' },
      plotOptions: { pie: { donut: { size: '65%' } } },
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
    usersData = null;   errU  = ''; loadingU  = true;
    entriesData = null; errE  = ''; loadingE  = true;
    drinkTrends = null; errDT = ''; loadingDT = true;
    modActData  = null; errMA = ''; loadingMA = true;
    await Promise.all([
      api.get<UsersStats>(`/moderation/graph-users?${q}`)
        .then(d => { usersData = d; }).catch(e => { errU = e.message; }).finally(() => { loadingU = false; }),
      api.get<EntriesStats>(`/moderation/graph-entries?${q}&group_by=${entriesGroupBy}`)
        .then(d => { entriesData = d; }).catch(e => { errE = e.message; }).finally(() => { loadingE = false; }),
      api.get<DrinkTrendsStats>(`/moderation/graph-drink-trends?${q}`)
        .then(d => { drinkTrends = d; }).catch(e => { errDT = e.message; }).finally(() => { loadingDT = false; }),
      api.get<ModerationActStats>(`/moderation/graph-moderation-activity?${q}`)
        .then(d => { modActData = d; }).catch(e => { errMA = e.message; }).finally(() => { loadingMA = false; }),
      loadPrices(q),
    ]);
  }

  async function loadPrices(baseQ?: string) {
    const p = new URLSearchParams(baseQ ?? fParams());
    if (selLor) p.set('lor_schluessel', selLor);
    if (selPriceDrink) p.set('drink_id', selPriceDrink);
    pricesData = null; errP = ''; loadingP = true;
    try { pricesData = await api.get<PricesStats>(`/moderation/graph-prices?${p}`); }
    catch (e: any) { errP = e.message; }
    finally { loadingP = false; }
  }

  async function loadEntries() {
    const q = fParams();
    entriesData = null; errE = ''; loadingE = true;
    try { entriesData = await api.get<EntriesStats>(`/moderation/graph-entries?${q}&group_by=${entriesGroupBy}`); }
    catch (e: any) { errE = e.message; }
    finally { loadingE = false; }
  }

  async function loadHistogram() {
    const p = new URLSearchParams();
    if (selHistDrink) p.set('drink_id', selHistDrink);
    histogramData = null;
    try { histogramData = await api.get<HistogramStats>(`/moderation/graph-price-histogram?${p}`); }
    catch { /* silent */ }
  }

  onMount(async () => {
    const m = await import('apexcharts');
    Apex = m.default;
    apexLoaded = true;

    lors = await api.get<LOR[]>('/moderation/lors').catch(() => []);
    drinks = await api.get<DrinkMeta[]>('/drinks/').catch(() => []);
    loadingC = true;
    changes = await api.get<PriceChange[]>('/moderation/price-feed?limit=20').catch(() => []);
    loadingC = false;

    await Promise.all([
      loadAll(),
      api.get<TopLocation[]>('/moderation/graph-top-locations').then(d => { topLocations = d; }).catch(() => {}),
      api.get<FreshnessItem[]>('/moderation/graph-freshness').then(d => { freshnessData = d; }).catch(() => {}),
      api.get<HeatmapRow[]>('/moderation/graph-heatmap').then(d => { heatmapRaw = d; }).catch(() => {}),
      api.get<LocationTypeItem[]>('/moderation/graph-location-types').then(d => { locTypesData = d; }).catch(() => {}),
      api.get<HistogramStats>('/moderation/graph-price-histogram').then(d => { histogramData = d; }).catch(() => {}),
    ]);
  });

  // ── Widget actions ────────────────────────────────────────────────────────
  async function deleteEntry(id: number) {
    actionErr = '';
    try {
      await api.post('/moderation/entries/bulk-delete', { entry_ids: [id] });
      changes = changes.filter(c => c.entry_id !== id);
      expandedId = null;
    } catch (e: any) { actionErr = e.message; }
  }

  async function suspendUser(uid: number) {
    actionErr = '';
    try {
      await api.patch(`/admin/users/${uid}/activate`, { is_active: false });
      expandedId = null;
    } catch (e: any) { actionErr = e.message; }
  }

  function fmtDate(iso: string) {
    return new Date(iso).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
  }
</script>

<div class="dash">
  <h1 class="page-title">Dashboard</h1>

  <!-- ── Global filter bar ───────────────────────────────────────────────── -->
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
        {#each MONTH_NAMES as name, i}<option value={i + 1}>{name}</option>{/each}
      </select>
    {/if}
    <select bind:value={selYear} class="f-sel">
      {#each YEARS as y}<option value={y}>{y}</option>{/each}
    </select>
    <button class="btn-primary" onclick={loadAll}>Laden</button>
  </div>

  <!-- ── Section: Nutzer & Aktivität ─────────────────────────────────────── -->
  <h2 class="section-title">Nutzer & Aktivität</h2>
  <div class="chart-grid">

    <div class="chart-box">
      <div class="chart-header">
        <span class="chart-title">Nutzerentwicklung</span>
        <div class="toggle-grp">
          <button class="tog" class:tog-active={chart1Mode === 'activity'}   onclick={() => chart1Mode = 'activity'}>Aktivität</button>
          <button class="tog" class:tog-active={chart1Mode === 'cumulative'} onclick={() => chart1Mode = 'cumulative'}>Kumuliert</button>
        </div>
      </div>
      {#if errU}<p class="cerr">{errU}</p>
      {:else if loadingU}<div class="chart-skeleton"></div>
      {:else if !usersData}<p class="cempty">Keine Daten</p>
      {:else}<div bind:this={el1}></div>{/if}
    </div>

    <div class="chart-box">
      <div class="chart-header">
        <span class="chart-title">Moderationsaktivität</span>
      </div>
      {#if errMA}<p class="cerr">{errMA}</p>
      {:else if loadingMA}<div class="chart-skeleton"></div>
      {:else if !modActData || !modActData.days.length}<p class="cempty">Keine Daten</p>
      {:else}<div bind:this={el6}></div>{/if}
    </div>

  </div>

  <!-- ── Section: Einträge ────────────────────────────────────────────────── -->
  <h2 class="section-title">Einträge</h2>
  <div class="chart-grid">

    <div class="chart-box">
      <div class="chart-header">
        <span class="chart-title">Einträge pro Tag</span>
        <div class="toggle-grp">
          <button class="tog" class:tog-active={entriesGroupBy === 'drink'}
            onclick={() => { entriesGroupBy = 'drink'; loadEntries(); }}>Sorte</button>
          <button class="tog" class:tog-active={entriesGroupBy === 'location_type'}
            onclick={() => { entriesGroupBy = 'location_type'; loadEntries(); }}>Standorttyp</button>
        </div>
      </div>
      {#if errE}<p class="cerr">{errE}</p>
      {:else if loadingE}<div class="chart-skeleton"></div>
      {:else if !entriesData || !entriesData.days.length}<p class="cempty">Keine Daten</p>
      {:else}<div bind:this={el2}></div>{/if}
    </div>

    <div class="chart-box">
      <div class="chart-header">
        <span class="chart-title">Preisverlauf pro Sorte</span>
      </div>
      {#if errDT}<p class="cerr">{errDT}</p>
      {:else if loadingDT}<div class="chart-skeleton"></div>
      {:else if !drinkTrends || !drinkTrends.days.length}<p class="cempty">Keine Daten</p>
      {:else}<div bind:this={el4}></div>{/if}
    </div>

  </div>

  <!-- ── Section: Preise ──────────────────────────────────────────────────── -->
  <h2 class="section-title">Preise</h2>
  <div class="chart-grid">

    <div class="chart-box">
      <div class="chart-header">
        <span class="chart-title">Durchschnittspreise</span>
        <div class="hdr-controls">
          <select bind:value={selPriceDrink} onchange={() => loadPrices()} class="f-sel f-sel-sm">
            <option value="">Alle Sorten</option>
            {#each drinks as d}<option value={String(d.id)}>{d.name}</option>{/each}
          </select>
          <select bind:value={selLor} onchange={() => loadPrices()} class="f-sel f-sel-sm">
            <option value="">Berlin gesamt</option>
            {#each lors as lor}<option value={lor.lor_schluessel}>{lor.pr_name}</option>{/each}
          </select>
        </div>
      </div>
      {#if errP}<p class="cerr">{errP}</p>
      {:else if loadingP}<div class="chart-skeleton"></div>
      {:else if !pricesData || !pricesData.berlin.length}<p class="cempty">Keine Daten</p>
      {:else}<div bind:this={el3}></div>{/if}
    </div>

    <div class="chart-box">
      <div class="chart-header">
        <span class="chart-title">Preisverteilung (alle Einträge)</span>
        <select bind:value={selHistDrink} onchange={loadHistogram} class="f-sel f-sel-sm">
          <option value="">Alle Sorten</option>
          {#each drinks as d}<option value={String(d.id)}>{d.name}</option>{/each}
        </select>
      </div>
      {#if !histogramData}<div class="chart-skeleton"></div>
      {:else if !histogramData.buckets.length}<p class="cempty">Keine Daten</p>
      {:else}<div bind:this={el5}></div>{/if}
    </div>

  </div>

  <!-- ── Section: Analyse ─────────────────────────────────────────────────── -->
  <h2 class="section-title">Analyse</h2>
  <div class="chart-grid">

    <div class="chart-box span-2">
      <div class="chart-header">
        <span class="chart-title">Top-Standorte nach Eintragsanzahl</span>
      </div>
      {#if !topLocations}<div class="chart-skeleton" style="height:280px"></div>
      {:else if !topLocations.length}<p class="cempty">Keine Daten</p>
      {:else}<div bind:this={el7}></div>{/if}
    </div>

    <div class="chart-box">
      <div class="chart-header">
        <span class="chart-title">Datenlage — Eintragsalter</span>
      </div>
      {#if !freshnessData}<div class="chart-skeleton"></div>
      {:else if !freshnessData.some(f => f.count > 0)}<p class="cempty">Keine Daten</p>
      {:else}<div bind:this={el8}></div>{/if}
    </div>

    <div class="chart-box">
      <div class="chart-header">
        <span class="chart-title">Einträge nach Standorttyp</span>
      </div>
      {#if !locTypesData}<div class="chart-skeleton"></div>
      {:else if !locTypesData.length}<p class="cempty">Keine Daten</p>
      {:else}<div bind:this={el10}></div>{/if}
    </div>

  </div>

  <!-- ── Section: Muster ──────────────────────────────────────────────────── -->
  <h2 class="section-title">Muster</h2>
  <div class="chart-grid">

    <div class="chart-box span-2">
      <div class="chart-header">
        <span class="chart-title">Einreichungen nach Wochentag & Uhrzeit</span>
      </div>
      {#if !heatmapRaw}<div class="chart-skeleton" style="height:220px"></div>
      {:else if !heatmapRaw.length}<p class="cempty">Keine Daten</p>
      {:else}<div bind:this={el9}></div>{/if}
    </div>

  </div>

  <!-- ── Section: Feed ────────────────────────────────────────────────────── -->
  <h2 class="section-title">Preisänderungs-Feed</h2>
  <div class="chart-grid">

    <div class="chart-box span-2 feed-box">
      {#if actionErr}<p class="cerr">{actionErr}</p>{/if}
      {#if loadingC}<div class="chart-skeleton" style="height:120px"></div>
      {:else if !changes.length}<p class="cempty">Keine Preisänderungen gefunden</p>
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

  .section-title {
    font-size: 0.7rem;
    font-weight: 700;
    color: #999;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 1.75rem 0 0.75rem;
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
    margin-bottom: 0.25rem;
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
  .span-2 { grid-column: 1 / -1; }
  @media (max-width: 720px) {
    .chart-grid { grid-template-columns: 1fr; }
    .span-2 { grid-column: unset; }
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

  .hdr-controls {
    display: flex;
    gap: 0.4rem;
    flex-wrap: wrap;
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

  /* Skeleton */
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
  .feed { list-style: none; margin: 0; padding: 0; max-height: 320px; overflow-y: auto; }
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

  .delta { font-size: 0.8rem; font-weight: 700; white-space: nowrap; min-width: 70px; padding-top: 1px; }
  .delta-up   { color: #43a047; }
  .delta-down { color: #e53935; }

  .feed-info { flex: 1; display: flex; flex-direction: column; gap: 1px; min-width: 0; }
  .feed-loc  { font-size: 0.83rem; font-weight: 600; color: #333; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .feed-sub  { font-size: 0.75rem; color: #888; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .feed-chevron { font-size: 0.65rem; color: #bbb; padding-top: 3px; }

  .feed-actions { display: flex; gap: 0.5rem; padding: 0.4rem 0.25rem 0.5rem; }
  .btn-danger-sm {
    padding: 0.3rem 0.7rem; background: #d32f2f; color: white;
    border: none; border-radius: 5px; font-size: 0.78rem; font-weight: 600; cursor: pointer;
  }
  .btn-danger-sm:hover { background: #b71c1c; }
  .btn-warn-sm {
    padding: 0.3rem 0.7rem; background: #f57c00; color: white;
    border: none; border-radius: 5px; font-size: 0.78rem; font-weight: 600; cursor: pointer;
  }
  .btn-warn-sm:hover { background: #e65100; }

  /* States */
  .cerr   { color: #c00; font-size: 0.82rem; padding: 0.5rem 0; }
  .cempty { color: #aaa; font-size: 0.82rem; padding: 0.5rem 0; }
</style>
