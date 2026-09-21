<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { authStore, isLoggedIn, user } from '$lib/stores/auth';
  import { api, mediaUrl } from '$lib/api/client';
  import PhotoLightbox from '$lib/components/PhotoLightbox.svelte';
  import type { GlassType, Photo } from '$lib/types/photo';
  import { t } from '$lib/i18n';
  import AppHeader from '$lib/components/AppHeader.svelte';
  import { authConfig, loadAuthConfig } from '$lib/stores/authConfig';
  import { buildIconHtml, buildUnavailableIconHtml } from '$lib/utils/markerIcon';

  const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

  // ── Mein Profil ──────────────────────────────────────────────
  let editingProfile = $state(false);
  let profileUsername = $state('');
  let profileEmail = $state('');
  let profilePassword = $state('');
  let profileStatus = $state<'idle' | 'loading' | 'success' | 'error'>('idle');
  let profileError = $state('');

  // ── Passwort ändern ──────────────────────────────────────────
  let currentPassword = $state('');
  let newPassword = $state('');
  let newPassword2 = $state('');
  let passwordStatus = $state<'idle' | 'loading' | 'success' | 'error'>('idle');
  let passwordError = $state('');

  // ── Konto löschen ────────────────────────────────────────────
  let showDeleteConfirm = $state(false);
  let deleteStatus = $state<'idle' | 'loading'>('idle');
  let deleteError = $state('');

  // ── Meine Einträge ───────────────────────────────────────────
  const ENTRIES_PAGE_SIZE = 12;

  interface EntryItem {
    id: number;
    location_id: number;
    location_name: string;
    drink_id: number;
    drink_name: string;
    drink_color_hex: string;
    price: number;
    price_tier: string | null;
    color_value: number;
    reported_at: string;
    note: string | null;
    unavailable: boolean;
    is_current: boolean;
    glass_type: GlassType | null;
    ai_glass_type: GlassType | null;
    photos: Photo[];
  }

  const GLASS_TYPES: GlassType[] = ['wine', 'tumbler', 'other'];
  let lightboxOpen = $state(false);
  let lightboxPhotos = $state<Photo[]>([]);
  let lightboxIndex = $state(0);

  // Glasform nachträglich korrigieren – ändert keine Zeitstempel, ist keine neue Preismeldung
  async function setGlassType(entry: EntryItem, glass: GlassType) {
    const next = entry.glass_type === glass ? null : glass;
    const previous = entry.glass_type;
    entry.glass_type = next;
    try {
      await api.patch(`/prices/${entry.id}/glass-type`, { glass_type: next });
    } catch {
      entry.glass_type = previous;
    }
  }

  let entries = $state<EntryItem[]>([]);
  let entriesTotal = $state(0);
  let entriesPage = $state(1);
  let entriesLoading = $state(false);
  let deleteEntryTarget = $state<EntryItem | null>(null);
  let deleteEntryStatus = $state<'idle' | 'loading'>('idle');

  async function loadEntries(page = 1) {
    entriesLoading = true;
    try {
      const data = await api.get<{ total: number; page: number; items: EntryItem[] }>(
        `/auth/me/entries?page=${page}&page_size=${ENTRIES_PAGE_SIZE}`,
      );
      entries = data.items;
      entriesTotal = data.total;
      entriesPage = page;
    } finally {
      entriesLoading = false;
    }
  }

  async function confirmDeleteEntry() {
    if (!deleteEntryTarget) return;
    deleteEntryStatus = 'loading';
    try {
      await api.delete(`/prices/${deleteEntryTarget.id}`);
      deleteEntryTarget = null;
      // stay on current page, but step back if it becomes empty
      const newTotal = entriesTotal - 1;
      const maxPage = Math.max(1, Math.ceil(newTotal / ENTRIES_PAGE_SIZE));
      await loadEntries(Math.min(entriesPage, maxPage));
    } finally {
      deleteEntryStatus = 'idle';
    }
  }

  // Mit Authentik verwaltet der SpritzMap-Login Name, E-Mail, Passwort und 2FA
  const managed = $derived($authConfig.mode !== 'legacy');

  onMount(() => {
    loadAuthConfig();
    if (!$isLoggedIn) { goto('/'); return; }
    profileUsername = $user?.username ?? '';
    profileEmail = $user?.email ?? '';
    loadEntries(1);
  });

  function startEdit() {
    profileUsername = $user?.username ?? '';
    profileEmail = $user?.email ?? '';
    profilePassword = '';
    profileStatus = 'idle';
    profileError = '';
    editingProfile = true;
  }

  function cancelEdit() {
    editingProfile = false;
    profileStatus = 'idle';
    profileError = '';
  }

  async function submitProfile() {
    profileStatus = 'loading';
    profileError = '';
    try {
      const updated = await api.put<{ id: number; email: string; username: string; role: 'user' | 'moderator' | 'admin'; is_active: boolean }>(
        '/auth/me',
        {
          username: profileUsername !== $user?.username ? profileUsername : null,
          email: profileEmail !== $user?.email ? profileEmail : null,
          current_password: profilePassword,
        }
      );
      authStore.setUser(updated);
      profileStatus = 'success';
      editingProfile = false;
    } catch (e: unknown) {
      profileError = e instanceof Error ? e.message : $t.account.error_generic;
      profileStatus = 'error';
    }
  }

  async function submitPassword() {
    passwordError = '';
    if (newPassword !== newPassword2) {
      passwordError = $t.account.error_password_mismatch;
      return;
    }
    if (newPassword.length < 8) {
      passwordError = $t.account.error_password_too_short;
      return;
    }
    passwordStatus = 'loading';
    try {
      await api.put('/auth/me/password', {
        current_password: currentPassword,
        new_password: newPassword,
      });
      passwordStatus = 'success';
      currentPassword = '';
      newPassword = '';
      newPassword2 = '';
    } catch (e: unknown) {
      passwordError = e instanceof Error ? e.message : $t.account.error_generic;
      passwordStatus = 'error';
    }
  }

  async function exportData() {
    const token = localStorage.getItem('token');
    const res = await fetch(`${API_URL}/auth/me/export`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'spritzmap-meine-daten.json';
    a.click();
    URL.revokeObjectURL(url);
  }

  async function deleteAccount() {
    deleteStatus = 'loading';
    deleteError = '';
    try {
      const res = await api.delete<{ unenrollment_url?: string | null }>('/auth/me');
      authStore.logout();
      // SpritzMap-Daten sind weg; das Login-Konto löscht der Nutzer im SpritzMap-Login selbst
      if (res?.unenrollment_url) window.location.href = res.unenrollment_url;
      else goto('/');
    } catch (e: unknown) {
      deleteError = e instanceof Error ? e.message : $t.account.error_generic;
      deleteStatus = 'idle';
    }
  }
</script>

<svelte:head>
  <title>{$t.account.page_title} – SpritzMap</title>
</svelte:head>

<div class="page">
  <AppHeader />

  <div class="cards">

    <!-- ── Mein Profil ── -->
    <section class="card">
      <h2>{$t.account.section_profile}</h2>

      {#if !editingProfile}
        <dl>
          <dt>{$t.account.label_username}</dt>
          <dd>{$user?.username}</dd>
          <dt>{$t.account.label_email}</dt>
          <dd>{$user?.email}</dd>
        </dl>
        {#if managed}
          <p class="hint">{$t.account.managed_hint}</p>
          <a class="btn-primary" href={$authConfig.account_url} target="_blank" rel="noopener">{$t.account.btn_manage_account}</a>
        {:else}
          <button class="btn-primary" onclick={startEdit}>{$t.account.btn_edit}</button>
        {/if}
      {:else}
        <form onsubmit={(e) => { e.preventDefault(); submitProfile(); }}>
          <label>
            {$t.account.label_username}
            <input type="text" bind:value={profileUsername} minlength={3} maxlength={50} required />
          </label>
          <label>
            {$t.account.label_email}
            <input type="email" bind:value={profileEmail} required />
          </label>
          <label>
            {$t.account.label_current_password_confirm}
            <input type="password" bind:value={profilePassword} required />
          </label>
          {#if profileError}<p class="error">{profileError}</p>{/if}
          {#if profileStatus === 'success'}<p class="success">{$t.account.success_profile}</p>{/if}
          <div class="btn-row">
            <button type="submit" class="btn-primary" disabled={profileStatus === 'loading'}>
              {profileStatus === 'loading' ? '…' : $t.account.btn_save}
            </button>
            <button type="button" class="btn-ghost" onclick={cancelEdit}>{$t.account.btn_cancel}</button>
          </div>
        </form>
      {/if}
    </section>

    <!-- ── Passwort ändern (nur ohne Authentik) ── -->
    {#if !managed}
    <section class="card">
      <h2>{$t.account.section_password}</h2>
      <form onsubmit={(e) => { e.preventDefault(); submitPassword(); }}>
        <label>
          {$t.account.label_current_password}
          <input type="password" bind:value={currentPassword} required />
        </label>
        <label>
          {$t.account.label_new_password}
          <input type="password" bind:value={newPassword} minlength={8} required />
        </label>
        <label>
          {$t.account.label_new_password_repeat}
          <input type="password" bind:value={newPassword2} minlength={8} required />
        </label>
        {#if passwordError}<p class="error">{passwordError}</p>{/if}
        {#if passwordStatus === 'success'}<p class="success">{$t.account.success_password}</p>{/if}
        <button type="submit" class="btn-primary" disabled={passwordStatus === 'loading'}>
          {passwordStatus === 'loading' ? '…' : $t.account.btn_change_password}
        </button>
      </form>
    </section>
    {/if}

    <!-- ── Meine Einträge ── -->
    <section class="card entries-card">
      <h2>{$t.account.section_entries}</h2>

      {#if entriesLoading}
        <p class="info">Lade…</p>
      {:else if entries.length === 0}
        <p class="info">{$t.account.entries_empty}</p>
      {:else}
        <div class="entries-grid">
          {#each entries as entry (entry.id)}
            <div class="entry-card">
              <button
                class="entry-delete-btn"
                aria-label="Eintrag löschen"
                onclick={() => (deleteEntryTarget = entry)}
              >✕</button>

              <div class="entry-icon">
                {#if entry.unavailable}
                  {@html buildUnavailableIconHtml(80)}
                {:else}
                  {@html buildIconHtml(entry.drink_color_hex, entry.color_value, 80)}
                {/if}
              </div>

              <div class="entry-info">
                <strong class="entry-location">{entry.location_name}</strong>
                <span class="entry-drink">{entry.drink_name}</span>
                {#if entry.unavailable}
                  <span class="entry-price unavail">{$t.account.entries_unavailable}</span>
                {:else}
                  <span class="entry-price">
                    {entry.price.toFixed(2)} €
                    {#if entry.price_tier}<span class="entry-tier">{entry.price_tier}</span>{/if}
                  </span>
                {/if}
                {#if !entry.unavailable}
                  <div class="entry-glass">
                    {#each GLASS_TYPES as g}
                      <button
                        class="glass-chip"
                        class:active={entry.glass_type === g}
                        onclick={() => setGlassType(entry, g)}
                      >{$t.glass[g]}</button>
                    {/each}
                    {#if entry.ai_glass_type && entry.glass_type === entry.ai_glass_type}
                      <span class="ai-badge">{$t.submit.ai_badge}</span>
                    {/if}
                  </div>
                {/if}
                {#if entry.photos?.length}
                  <div class="entry-photos">
                    {#each entry.photos as photo, i (photo.id)}
                      <button
                        class="entry-photo"
                        onclick={() => { lightboxPhotos = entry.photos; lightboxIndex = i; lightboxOpen = true; }}
                      >
                        <img src={mediaUrl(photo.thumb_url)} alt={$t.photos.photo_alt} loading="lazy" />
                      </button>
                    {/each}
                  </div>
                {/if}
                {#if entry.note}
                  <span class="entry-note">„{entry.note}"</span>
                {/if}
                <time class="entry-date">
                  {new Date(entry.reported_at).toLocaleDateString('de-DE')}
                </time>
              </div>
            </div>
          {/each}
        </div>

        {#if entriesTotal > ENTRIES_PAGE_SIZE}
          <div class="pagination">
            <button
              class="btn-ghost pag-btn"
              disabled={entriesPage <= 1}
              onclick={() => loadEntries(entriesPage - 1)}
            >{$t.account.entries_page_prev}</button>
            <span class="pag-label">{entriesPage} / {Math.ceil(entriesTotal / ENTRIES_PAGE_SIZE)}</span>
            <button
              class="btn-ghost pag-btn"
              disabled={entriesPage >= Math.ceil(entriesTotal / ENTRIES_PAGE_SIZE)}
              onclick={() => loadEntries(entriesPage + 1)}
            >{$t.account.entries_page_next}</button>
          </div>
        {/if}
      {/if}
    </section>

    <!-- ── Meine Daten ── -->
    <section class="card">
      <h2>{$t.account.section_data}</h2>
      <p class="info">{$t.account.data_info}</p>
      <button class="btn-primary" onclick={exportData}>{$t.account.btn_export}</button>
    </section>

    <!-- ── Konto löschen ── -->
    <section class="card danger-card">
      <h2>{$t.account.section_delete}</h2>
      <p class="info">{$t.account.delete_warning}</p>
      <button class="btn-danger" onclick={() => (showDeleteConfirm = true)}>
        {$t.account.btn_delete_account}
      </button>
    </section>

  </div>
</div>

<!-- ── Eintrag löschen Dialog ── -->
{#if deleteEntryTarget}
  <div
    class="overlay"
    onclick={() => (deleteEntryTarget = null)}
    onkeydown={(e) => e.key === 'Escape' && (deleteEntryTarget = null)}
    role="dialog"
    aria-modal="true"
    tabindex="-1"
  >
    <div
      class="dialog"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="presentation"
    >
      <h3>{$t.account.entries_delete_title}</h3>
      <p>{$t.account.entries_delete_body(deleteEntryTarget.location_name)}</p>
      <div class="btn-row">
        <button class="btn-danger" onclick={confirmDeleteEntry} disabled={deleteEntryStatus === 'loading'}>
          {deleteEntryStatus === 'loading' ? '…' : $t.account.entries_delete_confirm}
        </button>
        <button class="btn-ghost" onclick={() => (deleteEntryTarget = null)}>
          {$t.account.btn_cancel}
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- ── Bestätigungsdialog ── -->
<PhotoLightbox
  bind:open={lightboxOpen}
  bind:photos={lightboxPhotos}
  bind:index={lightboxIndex}
  ondeleted={() => loadEntries(entriesPage)}
/>

{#if showDeleteConfirm}
  <div
    class="overlay"
    onclick={() => (showDeleteConfirm = false)}
    onkeydown={(e) => e.key === 'Escape' && (showDeleteConfirm = false)}
    role="dialog"
    aria-modal="true"
    tabindex="-1"
  >
    <div
      class="dialog"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="presentation"
    >
      <h3>{$t.account.delete_confirm_title}</h3>
      <p>{$t.account.delete_confirm_body}</p>
      {#if deleteError}<p class="error">{deleteError}</p>{/if}
      <div class="btn-row">
        <button class="btn-danger" onclick={deleteAccount} disabled={deleteStatus === 'loading'}>
          {deleteStatus === 'loading' ? '…' : $t.account.delete_confirm_btn}
        </button>
        <button class="btn-ghost" onclick={() => (showDeleteConfirm = false)}>
          {$t.account.btn_cancel_delete}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .hint { margin: 0.5rem 0 1rem; color: #666; font-size: 0.875rem; line-height: 1.4; }
  a.btn-primary { display: inline-block; text-decoration: none; }
  .page {
    min-height: 100dvh;
    background: #f5f5f5;
    font-family: system-ui, sans-serif;
  }

  .cards {
    max-width: 860px;
    margin: 0 auto;
    padding: 1.5rem 1rem 3rem;
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    align-items: stretch;
  }

  .card:not(.entries-card) {
    max-width: 560px;
    align-self: center;
    width: 100%;
  }

  .card {
    background: white;
    border-radius: 12px;
    padding: 1.5rem;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  }

  .danger-card {
    border: 1.5px solid #f5c6c6;
  }

  h2 {
    font-size: 1rem;
    font-weight: 600;
    margin: 0 0 1rem;
    color: #222;
  }

  h3 {
    font-size: 1rem;
    font-weight: 600;
    margin: 0 0 0.5rem;
    color: #222;
  }

  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 0.3rem 1rem;
    margin: 0 0 1rem;
    font-size: 0.875rem;
  }

  dt { color: #888; }
  dd { margin: 0; color: #222; font-weight: 500; word-break: break-all; }

  form {
    display: flex;
    flex-direction: column;
    gap: 0.875rem;
  }

  label {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 0.875rem;
    font-weight: 500;
    color: #444;
  }

  input {
    padding: 8px 12px;
    border: 1.5px solid #ddd;
    border-radius: 6px;
    font-size: 1rem;
    outline: none;
  }
  input:focus { border-color: #e8500a; }

  .btn-row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .btn-primary {
    padding: 9px 18px;
    background: #e8500a;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 0.9rem;
    font-weight: 600;
    cursor: pointer;
  }
  .btn-primary:hover { background: #d04508; }
  .btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }

  .btn-ghost {
    padding: 9px 18px;
    background: transparent;
    color: #555;
    border: 1.5px solid #ddd;
    border-radius: 6px;
    font-size: 0.9rem;
    cursor: pointer;
  }
  .btn-ghost:hover { border-color: #aaa; color: #222; }

  .btn-danger {
    padding: 9px 18px;
    background: transparent;
    color: #c0392b;
    border: 1.5px solid #c0392b;
    border-radius: 6px;
    font-size: 0.9rem;
    font-weight: 600;
    cursor: pointer;
  }
  .btn-danger:hover { background: #c0392b; color: white; }
  .btn-danger:disabled { opacity: 0.6; cursor: not-allowed; }

  .info {
    font-size: 0.875rem;
    color: #555;
    line-height: 1.5;
    margin: 0 0 1rem;
  }

  .error { color: #c0392b; font-size: 0.85rem; margin: 0; }
  .success { color: #27ae60; font-size: 0.85rem; margin: 0; }

  /* Overlay / Dialog */
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.45);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .dialog {
    background: white;
    border-radius: 12px;
    padding: 1.75rem;
    width: min(400px, 92vw);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  /* Entries */
  .entries-card {
    max-width: 860px;
    width: 100%;
    align-self: center;
  }

  .entries-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.75rem;
    margin-bottom: 1rem;
  }

  @media (max-width: 600px) {
    .entries-grid {
      grid-template-columns: repeat(2, 1fr);
    }
  }

  .entry-card {
    position: relative;
    background: #fafafa;
    border: 1.5px solid #ececec;
    border-radius: 10px;
    padding: 0.75rem 0.6rem 0.6rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem;
    text-align: center;
  }

  .entry-delete-btn {
    position: absolute;
    top: 6px;
    right: 6px;
    width: 22px;
    height: 22px;
    border: none;
    background: #e0e0e0;
    color: #666;
    border-radius: 50%;
    font-size: 0.7rem;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    line-height: 1;
    padding: 0;
    transition: background 0.15s, color 0.15s;
  }

  .entry-delete-btn:hover {
    background: #c0392b;
    color: white;
  }

  .entry-icon {
    flex-shrink: 0;
  }

  .entry-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
    width: 100%;
  }

  .entry-location {
    font-size: 0.8rem;
    font-weight: 600;
    color: #222;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .entry-drink {
    font-size: 0.75rem;
    color: #888;
  }

  .entry-price {
    font-size: 0.82rem;
    font-weight: 600;
    color: #e8500a;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
  }

  .entry-price.unavail {
    color: #aaa;
    font-weight: 400;
    font-style: italic;
  }

  .entry-tier {
    font-size: 0.7rem;
    color: #aaa;
    font-weight: 400;
  }

  .entry-note {
    font-size: 0.72rem;
    color: #999;
    font-style: italic;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .entry-glass {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px;
    margin-top: 4px;
  }

  .glass-chip {
    padding: 2px 8px;
    border: 1px solid #ddd;
    border-radius: 999px;
    background: white;
    font-size: 0.72rem;
    color: #666;
    cursor: pointer;
  }

  .glass-chip.active { border-color: #e8500a; background: #fff3ec; color: #b33c00; font-weight: 600; }

  .ai-badge {
    padding: 1px 6px;
    border-radius: 4px;
    background: #eef2ff;
    color: #4150a8;
    font-size: 0.65rem;
    font-weight: 600;
  }

  .entry-photos { display: flex; gap: 4px; margin-top: 4px; }

  .entry-photo {
    padding: 0;
    border: none;
    background: none;
    cursor: zoom-in;
  }

  .entry-photo img {
    width: 44px;
    height: 44px;
    object-fit: cover;
    border-radius: 4px;
    display: block;
  }

  .entry-date {
    font-size: 0.7rem;
    color: #bbb;
    margin-top: 2px;
  }

  .pagination {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    margin-top: 0.25rem;
  }

  .pag-btn {
    padding: 6px 14px;
    font-size: 0.85rem;
  }

  .pag-btn:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }

  .pag-label {
    font-size: 0.85rem;
    color: #666;
    min-width: 50px;
    text-align: center;
  }
</style>
