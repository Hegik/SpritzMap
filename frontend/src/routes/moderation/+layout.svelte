<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { isLoggedIn, isModerator, user, userLoaded } from '$lib/stores/auth';
  import { t } from '$lib/i18n';

  let { children } = $props();

  // Erst entscheiden, wenn das Profil geladen ist – sonst fliegt man beim Neuladen raus
  $effect(() => {
    if ($userLoaded && (!$isLoggedIn || !$isModerator)) goto('/');
  });

  const navItems = $derived([
    { href: '/moderation/dashboard', label: $t.moderation.nav_dashboard, icon: '📊' },
    { href: '/moderation/entries',   label: $t.moderation.nav_entries,   icon: '📋' },
    ...($user?.role === 'admin'
      ? [
          { href: '/moderation/users', label: $t.moderation.nav_users, icon: '👥' },
          { href: '/moderation/cities', label: 'Städte', icon: '🏙️' },
        ]
      : []),
  ]);

  function onMobileSelect(e: Event) {
    goto((e.target as HTMLSelectElement).value);
  }
</script>

<div class="mod-shell">
  <!-- Desktop sidebar -->
  <aside class="sidebar">
    <div class="sidebar-header">
      <span class="sidebar-title">{$t.moderation.panel_title}</span>
    </div>

    <nav class="sidebar-nav">
      {#each navItems as item}
        <a href={item.href} class:active={$page.url.pathname.startsWith(item.href)}>
          <span class="nav-icon">{item.icon}</span>
          {item.label}
        </a>
      {/each}
    </nav>

    <div class="sidebar-footer">
      <a href="/" class="back-link">{$t.moderation.back_to_map}</a>
    </div>
  </aside>

  <div class="main-wrap">
    <!-- Mobile topbar -->
    <div class="mobile-topbar">
      <span class="mobile-title">{$t.moderation.panel_title}</span>
      <select class="mobile-nav-select" value={$page.url.pathname} onchange={onMobileSelect}>
        {#each navItems as item}
          <option value={item.href}>{item.icon} {item.label}</option>
        {/each}
      </select>
      <a href="/" class="mobile-back">{$t.moderation.back_to_map}</a>
    </div>

    <main class="mod-content">
      {#if $userLoaded && $isModerator}{@render children()}{/if}
    </main>
  </div>
</div>

<style>
  .mod-shell {
    display: flex;
    height: 100vh;
    overflow: hidden;
    background: #f5f5f5;
  }

  /* ── Desktop sidebar ──────────────────────────────────────── */
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

  .nav-icon { font-size: 1rem; width: 1.2rem; text-align: center; }

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

  /* ── Main area ────────────────────────────────────────────── */
  .main-wrap {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .mod-content {
    flex: 1;
    overflow-y: auto;
    padding: 2rem;
  }

  /* ── Mobile topbar (hidden on desktop) ───────────────────── */
  .mobile-topbar { display: none; }

  @media (max-width: 640px) {
    .sidebar { display: none; }

    .mobile-topbar {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      padding: 0.6rem 1rem;
      background: #1a1a2e;
      flex-shrink: 0;
      flex-wrap: wrap;
    }

    .mobile-title {
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      color: #e8500a;
      flex-shrink: 0;
    }

    .mobile-nav-select {
      flex: 1;
      min-width: 0;
      padding: 0.35rem 0.5rem;
      border-radius: 6px;
      border: 1px solid rgba(255,255,255,0.2);
      background: rgba(255,255,255,0.08);
      color: #fff;
      font-size: 0.875rem;
      cursor: pointer;
    }

    .mobile-back {
      color: #888;
      text-decoration: none;
      font-size: 0.75rem;
      white-space: nowrap;
    }
    .mobile-back:hover { color: #ccc; }

    .mod-content { padding: 1rem; }
  }
</style>
