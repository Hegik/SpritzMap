<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api/client';
  import { t } from '$lib/i18n';

  interface Entry {
    id: number;
    location_name: string;
    drink_name: string;
    username: string | null;
    price: number;
    reported_at: string;
    is_current: boolean;
    note: string | null;
  }

  interface Drink { id: number; name: string }

  // ── state ─────────────────────────────────────────────────────────────────
  let entries = $state<Entry[]>([]);
  let total = $state(0);
  let page = $state(1);
  const limit = 50;
  let loading = $state(false);
  let error = $state('');

  // filters
  let filterDrinkId = $state('');
  let filterLocation = $state('');
  let filterUser = $state('');
  let filterDateFrom = $state('');
  let filterDateTo = $state('');

  let drinks = $state<Drink[]>([]);

  // selection
  let selected = $state<Set<number>>(new Set());
  let confirmDelete = $state(false);
  let deleteTarget = $state<number | null>(null); // null = bulk

  // ── load ──────────────────────────────────────────────────────────────────
  async function load() {
    loading = true;
    error = '';
    try {
      const params = new URLSearchParams({ page: String(page), limit: String(limit) });
      if (filterDrinkId) params.set('drink_id', filterDrinkId);
      if (filterLocation) params.set('location_name', filterLocation);
      if (filterUser) params.set('username', filterUser);
      if (filterDateFrom) params.set('date_from', filterDateFrom);
      if (filterDateTo) params.set('date_to', filterDateTo);
      const data = await api.get<{ total: number; items: Entry[] }>(`/moderation/entries?${params}`);
      entries = data.items;
      total = data.total;
      selected = new Set();
    } catch (e) {
      error = e instanceof Error ? e.message : $t.moderation.error_generic;
    } finally {
      loading = false;
    }
  }

  onMount(async () => {
    const drinksData = await api.get<Drink[]>('/drinks/').catch(() => []);
    drinks = drinksData;
    await load();
  });

  function applyFilters() {
    page = 1;
    load();
  }

  function resetFilters() {
    filterDrinkId = '';
    filterLocation = '';
    filterUser = '';
    filterDateFrom = '';
    filterDateTo = '';
    page = 1;
    load();
  }

  // ── selection ─────────────────────────────────────────────────────────────
  function toggleAll(e: Event) {
    const checked = (e.target as HTMLInputElement).checked;
    selected = checked ? new Set(entries.map((e) => e.id)) : new Set();
  }

  function toggleOne(id: number) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    selected = next;
  }

  // ── delete ────────────────────────────────────────────────────────────────
  function askDelete(id: number | null) {
    deleteTarget = id;
    confirmDelete = true;
  }

  async function confirmDeleteAction() {
    confirmDelete = false;
    const ids = deleteTarget !== null ? [deleteTarget] : [...selected];
    if (!ids.length) return;
    try {
      await api.post('/moderation/entries/bulk-delete', { entry_ids: ids });
      deleteTarget = null;
      await load();
    } catch (e) {
      error = e instanceof Error ? e.message : $t.moderation.error_generic;
    }
  }

  // ── pagination ────────────────────────────────────────────────────────────
  const totalPages = $derived(Math.max(1, Math.ceil(total / limit)));

  function formatDate(iso: string) {
    return new Date(iso).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
  }
</script>

<div class="entries-page">
  <h1 class="page-title">{$t.moderation.nav_entries}</h1>

  <!-- Filter bar -->
  <div class="filter-bar">
    <select bind:value={filterDrinkId} class="filter-input">
      <option value="">{$t.moderation.filter_drink} – alle</option>
      {#each drinks as d}
        <option value={String(d.id)}>{d.name}</option>
      {/each}
    </select>
    <input
      type="text"
      placeholder={$t.moderation.filter_location}
      bind:value={filterLocation}
      class="filter-input"
    />
    <input
      type="text"
      placeholder={$t.moderation.filter_user}
      bind:value={filterUser}
      class="filter-input"
    />
    <label class="date-label">
      {$t.moderation.filter_date_from}
      <input type="date" bind:value={filterDateFrom} class="filter-input date-input" />
    </label>
    <label class="date-label">
      {$t.moderation.filter_date_to}
      <input type="date" bind:value={filterDateTo} class="filter-input date-input" />
    </label>
    <button class="btn-primary" onclick={applyFilters}>Suchen</button>
    <button class="btn-ghost" onclick={resetFilters}>Zurücksetzen</button>
  </div>

  <!-- Bulk action bar -->
  {#if selected.size > 0}
    <div class="bulk-bar">
      <span>{selected.size} ausgewählt</span>
      <button class="btn-danger" onclick={() => askDelete(null)}>
        {$t.moderation.btn_bulk_delete(selected.size)}
      </button>
    </div>
  {/if}

  {#if error}
    <p class="error">{error}</p>
  {:else if loading}
    <p class="loading">{$t.moderation.loading}</p>
  {:else if entries.length === 0}
    <p class="empty">{$t.moderation.no_entries}</p>
  {:else}
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th class="col-check">
              <input
                type="checkbox"
                checked={selected.size === entries.length}
                indeterminate={selected.size > 0 && selected.size < entries.length}
                onchange={toggleAll}
              />
            </th>
            <th>{$t.moderation.col_location}</th>
            <th>{$t.moderation.col_drink}</th>
            <th>{$t.moderation.col_price}</th>
            <th>{$t.moderation.col_user}</th>
            <th>{$t.moderation.col_date}</th>
            <th>{$t.moderation.col_status}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {#each entries as entry}
            <tr class:removed={!entry.is_current}>
              <td class="col-check">
                <input
                  type="checkbox"
                  checked={selected.has(entry.id)}
                  onchange={() => toggleOne(entry.id)}
                />
              </td>
              <td>{entry.location_name}</td>
              <td>{entry.drink_name}</td>
              <td>{entry.price.toFixed(2)} €</td>
              <td>{entry.username ?? '–'}</td>
              <td>{formatDate(entry.reported_at)}</td>
              <td>
                <span class="badge" class:badge-active={entry.is_current} class:badge-removed={!entry.is_current}>
                  {entry.is_current ? $t.moderation.status_current : $t.moderation.status_removed}
                </span>
              </td>
              <td>
                {#if entry.is_current}
                  <button class="icon-btn" title="Löschen" onclick={() => askDelete(entry.id)}>🗑</button>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div class="pagination">
      <button class="btn-ghost" disabled={page === 1} onclick={() => { page -= 1; load(); }}>‹</button>
      <span>Seite {page} / {totalPages} <small>({total} gesamt)</small></span>
      <button class="btn-ghost" disabled={page >= totalPages} onclick={() => { page += 1; load(); }}>›</button>
    </div>
  {/if}
</div>

<!-- Confirm delete dialog -->
{#if confirmDelete}
  <div class="dialog-backdrop" role="presentation" onclick={() => confirmDelete = false}></div>
  <div class="dialog" role="dialog">
    <p>
      {deleteTarget !== null
        ? 'Diesen Eintrag wirklich löschen?'
        : `${selected.size} ${selected.size === 1 ? 'Eintrag' : 'Einträge'} wirklich löschen?`}
    </p>
    <div class="dialog-actions">
      <button class="btn-danger" onclick={confirmDeleteAction}>{$t.moderation.btn_confirm_delete}</button>
      <button class="btn-ghost" onclick={() => confirmDelete = false}>{$t.moderation.btn_cancel}</button>
    </div>
  </div>
{/if}

<style>
  .entries-page { max-width: 1100px; }

  .page-title {
    font-size: 1.5rem;
    font-weight: 700;
    color: #1a1a2e;
    margin: 0 0 1.25rem;
  }

  .filter-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    align-items: flex-end;
    background: white;
    padding: 1rem;
    border-radius: 10px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    margin-bottom: 1rem;
  }

  .filter-input {
    padding: 0.4rem 0.6rem;
    border: 1px solid #ddd;
    border-radius: 6px;
    font-size: 0.85rem;
    background: white;
    min-width: 120px;
  }

  .date-label {
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-size: 0.75rem;
    color: #777;
  }
  .date-input { min-width: 130px; }

  .bulk-bar {
    display: flex;
    align-items: center;
    gap: 1rem;
    background: #fff3ec;
    border: 1px solid #f4c09a;
    border-radius: 8px;
    padding: 0.6rem 1rem;
    margin-bottom: 0.75rem;
    font-size: 0.875rem;
  }

  .table-wrap {
    background: white;
    border-radius: 10px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    overflow: auto;
    margin-bottom: 1rem;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.875rem;
  }

  thead th {
    background: #f9f9f9;
    padding: 0.6rem 0.75rem;
    text-align: left;
    font-weight: 600;
    color: #555;
    border-bottom: 1px solid #eee;
    white-space: nowrap;
  }

  tbody td {
    padding: 0.55rem 0.75rem;
    border-bottom: 1px solid #f0f0f0;
    color: #333;
  }

  tbody tr:last-child td { border-bottom: none; }
  tbody tr:hover { background: #fafafa; }
  tbody tr.removed { opacity: 0.5; }

  .col-check { width: 36px; }

  .badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 600;
  }
  .badge-active { background: #e6f4ea; color: #2d7a3a; }
  .badge-removed { background: #f5f5f5; color: #999; }

  .icon-btn {
    background: none;
    border: none;
    cursor: pointer;
    font-size: 1rem;
    padding: 2px 4px;
    border-radius: 4px;
    opacity: 0.7;
  }
  .icon-btn:hover { opacity: 1; background: #fce8e8; }

  .pagination {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    justify-content: center;
    font-size: 0.875rem;
    color: #555;
  }

  .loading, .empty { color: #888; padding: 1rem 0; }
  .error { color: #c00; }

  /* Buttons */
  .btn-primary {
    padding: 0.4rem 0.9rem;
    background: #e8500a;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
  }
  .btn-primary:hover { background: #c93e00; }

  .btn-ghost {
    padding: 0.4rem 0.75rem;
    background: white;
    color: #555;
    border: 1px solid #ddd;
    border-radius: 6px;
    font-size: 0.85rem;
    cursor: pointer;
  }
  .btn-ghost:hover:not(:disabled) { background: #f5f5f5; }
  .btn-ghost:disabled { opacity: 0.4; cursor: default; }

  .btn-danger {
    padding: 0.4rem 0.9rem;
    background: #d32f2f;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
  }
  .btn-danger:hover { background: #b71c1c; }

  /* Dialog */
  .dialog-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.4);
    z-index: 200;
  }

  .dialog {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: white;
    border-radius: 12px;
    padding: 1.5rem 2rem;
    z-index: 201;
    box-shadow: 0 8px 32px rgba(0,0,0,0.2);
    min-width: 280px;
  }

  .dialog p { margin: 0 0 1.25rem; font-size: 0.95rem; }

  .dialog-actions { display: flex; gap: 0.75rem; justify-content: flex-end; }
</style>
