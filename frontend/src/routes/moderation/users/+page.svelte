<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { user } from '$lib/stores/auth';
  import { api } from '$lib/api/client';
  import { t } from '$lib/i18n';

  interface ManagedUser {
    id: number;
    username: string;
    email: string;
    role: 'user' | 'moderator' | 'admin';
    is_active: boolean;
    is_verified: boolean;
  }

  // ── access guard ──────────────────────────────────────────────────────────
  onMount(async () => {
    if ($user?.role !== 'admin') {
      goto('/moderation/dashboard');
      return;
    }
    await load();
  });

  // ── state ─────────────────────────────────────────────────────────────────
  let users = $state<ManagedUser[]>([]);
  let total = $state(0);
  let page = $state(1);
  const limit = 50;
  let loading = $state(false);
  let error = $state('');
  let search = $state('');

  // ── load ──────────────────────────────────────────────────────────────────
  async function load() {
    loading = true;
    error = '';
    try {
      const params = new URLSearchParams({ page: String(page), limit: String(limit) });
      if (search) params.set('search', search);
      const data = await api.get<{ total: number; items: ManagedUser[] }>(`/admin/users?${params}`);
      users = data.items;
      total = data.total;
    } catch (e) {
      error = e instanceof Error ? e.message : $t.moderation.error_generic;
    } finally {
      loading = false;
    }
  }

  function applySearch() { page = 1; load(); }

  // ── role change ───────────────────────────────────────────────────────────
  async function changeRole(userId: number, role: string) {
    try {
      await api.patch(`/admin/users/${userId}/role`, { role });
      const u = users.find((u) => u.id === userId);
      if (u) u.role = role as ManagedUser['role'];
    } catch (e) {
      error = e instanceof Error ? e.message : $t.moderation.error_generic;
    }
  }

  // ── suspend / activate ────────────────────────────────────────────────────
  async function toggleActive(userId: number, isActive: boolean) {
    try {
      await api.patch(`/admin/users/${userId}/activate`, { is_active: isActive });
      const u = users.find((u) => u.id === userId);
      if (u) u.is_active = isActive;
    } catch (e) {
      error = e instanceof Error ? e.message : $t.moderation.error_generic;
    }
  }

  // ── delete user ───────────────────────────────────────────────────────────
  let confirmDeleteUserId = $state<number | null>(null);

  function askDeleteUser(userId: number) {
    confirmDeleteUserId = userId;
  }

  async function confirmDeleteUser() {
    if (confirmDeleteUserId === null) return;
    try {
      await api.delete(`/admin/users/${confirmDeleteUserId}`);
      users = users.filter((u) => u.id !== confirmDeleteUserId);
      total -= 1;
    } catch (e) {
      error = e instanceof Error ? e.message : $t.moderation.error_generic;
    } finally {
      confirmDeleteUserId = null;
    }
  }

  const totalPages = $derived(Math.max(1, Math.ceil(total / limit)));

  const roleLabel: Record<string, string> = {
    user: 'Nutzer',
    moderator: 'Moderator',
    admin: 'Admin',
  };
</script>

<div class="users-page">
  <h1 class="page-title">{$t.moderation.nav_users}</h1>

  <!-- Search -->
  <div class="search-bar">
    <input
      type="text"
      placeholder="Nutzername oder E-Mail suchen…"
      bind:value={search}
      class="search-input"
      onkeydown={(e) => e.key === 'Enter' && applySearch()}
    />
    <button class="btn-primary" onclick={applySearch}>Suchen</button>
    {#if search}
      <button class="btn-ghost" onclick={() => { search = ''; applySearch(); }}>Zurücksetzen</button>
    {/if}
  </div>

  {#if error}
    <p class="error">{error}</p>
  {:else if loading}
    <p class="loading">{$t.moderation.loading}</p>
  {:else if users.length === 0}
    <p class="empty">{$t.moderation.no_users}</p>
  {:else}
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>{$t.moderation.col_username}</th>
            <th>{$t.moderation.col_email}</th>
            <th>{$t.moderation.col_role}</th>
            <th>{$t.moderation.col_active}</th>
            <th>Verifiziert</th>
            <th>Aktionen</th>
          </tr>
        </thead>
        <tbody>
          {#each users as u}
            {@const isSelf = u.id === $user?.id}
            <tr class:suspended={!u.is_active}>
              <td class="username-cell">
                {u.username}
                {#if isSelf}<span class="self-badge">Ich</span>{/if}
              </td>
              <td class="email-cell">{u.email}</td>
              <td>
                {#if isSelf}
                  <span class="role-static">{roleLabel[u.role]}</span>
                {:else}
                  <select
                    value={u.role}
                    onchange={(e) => changeRole(u.id, (e.target as HTMLSelectElement).value)}
                    class="role-select"
                  >
                    <option value="user">Nutzer</option>
                    <option value="moderator">Moderator</option>
                    <option value="admin">Admin</option>
                  </select>
                {/if}
              </td>
              <td>
                <span class="badge" class:badge-active={u.is_active} class:badge-removed={!u.is_active}>
                  {u.is_active ? 'Aktiv' : 'Suspendiert'}
                </span>
              </td>
              <td>
                <span class="badge" class:badge-active={u.is_verified} class:badge-removed={!u.is_verified}>
                  {u.is_verified ? 'Ja' : 'Nein'}
                </span>
              </td>
              <td class="actions-cell">
                {#if !isSelf}
                  {#if u.is_active}
                    <button class="btn-warn" onclick={() => toggleActive(u.id, false)}>
                      {$t.moderation.btn_suspend}
                    </button>
                  {:else}
                    <button class="btn-ghost-sm" onclick={() => toggleActive(u.id, true)}>
                      {$t.moderation.btn_activate}
                    </button>
                  {/if}
                  <button class="icon-btn" title="Konto löschen" onclick={() => askDeleteUser(u.id)}>🗑</button>
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

{#if confirmDeleteUserId !== null}
  <div class="dialog-backdrop" role="presentation" onclick={() => confirmDeleteUserId = null}></div>
  <div class="dialog" role="dialog">
    <p>Konto wirklich löschen? Die Einträge des Nutzers bleiben anonymisiert erhalten.</p>
    <div class="dialog-actions">
      <button class="btn-danger" onclick={confirmDeleteUser}>Ja, Konto löschen</button>
      <button class="btn-ghost" onclick={() => confirmDeleteUserId = null}>Abbrechen</button>
    </div>
  </div>
{/if}

<style>
  .users-page { max-width: 900px; }

  .page-title {
    font-size: 1.5rem;
    font-weight: 700;
    color: #1a1a2e;
    margin: 0 0 1.25rem;
  }

  .search-bar {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    margin-bottom: 1rem;
    flex-wrap: wrap;
  }

  .search-input {
    padding: 0.4rem 0.7rem;
    border: 1px solid #ddd;
    border-radius: 6px;
    font-size: 0.875rem;
    min-width: 240px;
    flex: 1;
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
  tbody tr.suspended { opacity: 0.55; }

  .username-cell { font-weight: 500; }
  .email-cell { color: #666; font-size: 0.82rem; }

  .self-badge {
    margin-left: 6px;
    font-size: 0.7rem;
    background: #e8500a;
    color: white;
    padding: 1px 6px;
    border-radius: 10px;
    font-weight: 600;
  }

  .role-static { font-size: 0.875rem; color: #555; }

  .role-select {
    padding: 2px 6px;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 0.85rem;
    background: white;
    cursor: pointer;
  }

  .badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 600;
  }
  .badge-active { background: #e6f4ea; color: #2d7a3a; }
  .badge-removed { background: #f5e0e0; color: #c00; }

  .loading, .empty { color: #888; padding: 1rem 0; }
  .error { color: #c00; }

  .pagination {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    justify-content: center;
    font-size: 0.875rem;
    color: #555;
  }

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

  .btn-warn {
    padding: 3px 10px;
    background: #fff3e0;
    color: #e65100;
    border: 1px solid #ffcc80;
    border-radius: 5px;
    font-size: 0.8rem;
    font-weight: 600;
    cursor: pointer;
  }
  .btn-warn:hover { background: #ffe0b2; }

  .btn-ghost-sm {
    padding: 3px 10px;
    background: white;
    color: #555;
    border: 1px solid #ddd;
    border-radius: 5px;
    font-size: 0.8rem;
    cursor: pointer;
  }
  .btn-ghost-sm:hover { background: #f0f0f0; }

  .actions-cell { display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; }

  .icon-btn {
    background: none;
    border: none;
    cursor: pointer;
    font-size: 1rem;
    padding: 2px 4px;
    border-radius: 4px;
    opacity: 0.6;
  }
  .icon-btn:hover { opacity: 1; background: #fce8e8; }

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
    min-width: 300px;
  }

  .dialog p { margin: 0 0 1.25rem; font-size: 0.95rem; }
  .dialog-actions { display: flex; gap: 0.75rem; justify-content: flex-end; }
</style>
