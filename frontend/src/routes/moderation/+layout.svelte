<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { isLoggedIn, isModerator, user } from '$lib/stores/auth';
  import { t } from '$lib/i18n';

  let { children } = $props();

  onMount(() => {
    if (!$isLoggedIn || !$isModerator) {
      goto('/');
    }
  });
</script>

<div class="mod-shell">
  <aside class="sidebar">
    <div class="sidebar-header">
      <span class="sidebar-title">{$t.moderation.panel_title}</span>
    </div>

    <nav class="sidebar-nav">
      <a
        href="/moderation/dashboard"
        class:active={$page.url.pathname.startsWith('/moderation/dashboard')}
      >
        <span class="nav-icon">📊</span>
        {$t.moderation.nav_dashboard}
      </a>
      <a
        href="/moderation/entries"
        class:active={$page.url.pathname.startsWith('/moderation/entries')}
      >
        <span class="nav-icon">📋</span>
        {$t.moderation.nav_entries}
      </a>
      {#if $user?.role === 'admin'}
        <a
          href="/moderation/users"
          class:active={$page.url.pathname.startsWith('/moderation/users')}
        >
          <span class="nav-icon">👥</span>
          {$t.moderation.nav_users}
        </a>
      {/if}
    </nav>

    <div class="sidebar-footer">
      <a href="/" class="back-link">{$t.moderation.back_to_map}</a>
    </div>
  </aside>

  <main class="mod-content">
    {@render children()}
  </main>
</div>

<style>
  .mod-shell {
    display: flex;
    height: 100vh;
    overflow: hidden;
    background: #f5f5f5;
  }

  .sidebar {
    width: 220px;
    flex-shrink: 0;
    background: #1a1a2e;
    color: #ccc;
    display: flex;
    flex-direction: column;
    overflow-y: auto;
  }

  .sidebar-header {
    padding: 1.25rem 1rem 1rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  }

  .sidebar-title {
    font-size: 0.8rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #e8500a;
  }

  .sidebar-nav {
    flex: 1;
    padding: 0.75rem 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .sidebar-nav a {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.6rem 1rem;
    color: #aaa;
    text-decoration: none;
    font-size: 0.875rem;
    border-radius: 0;
    transition: background 0.15s, color 0.15s;
  }

  .sidebar-nav a:hover {
    background: rgba(255, 255, 255, 0.07);
    color: #fff;
  }

  .sidebar-nav a.active {
    background: rgba(232, 80, 10, 0.2);
    color: #e8500a;
    font-weight: 600;
  }

  .nav-icon {
    font-size: 1rem;
    width: 1.2rem;
    text-align: center;
  }

  .sidebar-footer {
    padding: 1rem;
    border-top: 1px solid rgba(255, 255, 255, 0.1);
  }

  .back-link {
    color: #888;
    text-decoration: none;
    font-size: 0.8rem;
    transition: color 0.15s;
  }
  .back-link:hover { color: #ccc; }

  .mod-content {
    flex: 1;
    overflow-y: auto;
    padding: 2rem;
  }
</style>
