<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { authStore, isLoggedIn, user } from '$lib/stores/auth';
  import { api } from '$lib/api/client';
  import { t } from '$lib/i18n';

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

  onMount(() => {
    if (!$isLoggedIn) { goto('/'); return; }
    profileUsername = $user?.username ?? '';
    profileEmail = $user?.email ?? '';
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
      await api.delete('/auth/me');
      authStore.logout();
      goto('/');
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
  <div class="topbar">
    <a href="/" class="back-link">{$t.account.back_to_map}</a>
    <h1>{$t.account.page_title}</h1>
  </div>

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
        <button class="btn-primary" onclick={startEdit}>{$t.account.btn_edit}</button>
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

    <!-- ── Passwort ändern ── -->
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

<!-- ── Bestätigungsdialog ── -->
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
  .page {
    min-height: 100dvh;
    background: #f5f5f5;
    font-family: system-ui, sans-serif;
  }

  .topbar {
    background: #e8500a;
    padding: 0 1.25rem;
    height: 48px;
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .back-link {
    color: rgba(255, 255, 255, 0.85);
    font-size: 0.875rem;
    text-decoration: none;
    white-space: nowrap;
  }
  .back-link:hover { color: white; }

  h1 {
    color: white;
    font-size: 1.1rem;
    font-weight: 600;
    margin: 0;
  }

  .cards {
    max-width: 560px;
    margin: 0 auto;
    padding: 1.5rem 1rem 3rem;
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
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
</style>
