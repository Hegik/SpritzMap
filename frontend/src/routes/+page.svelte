<script lang="ts">
  import { onMount } from 'svelte';
  import SpritzMap from '$lib/components/SpritzMap.svelte';
  import FilterPanel from '$lib/components/FilterPanel.svelte';
  import AuthModal from '$lib/components/AuthModal.svelte';
  import { authStore, isLoggedIn } from '$lib/stores/auth';
  import { drinks } from '$lib/stores/map';
  import { api } from '$lib/api/client';

  let authOpen = $state(false);

  onMount(async () => {
    const list = await api.get<typeof $drinks>('/drinks/');
    drinks.set(list);

    if ($isLoggedIn) {
      try {
        const me = await api.get<{ id: number; email: string; username: string; role: 'user' | 'moderator' | 'admin' }>('/auth/me');
        authStore.setUser(me);
      } catch {
        authStore.logout();
      }
    }
  });
</script>

<svelte:head>
  <title>SpritzMap — Spritz Preise in Berlin</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
</svelte:head>

<div class="app">
  <header>
    <div class="logo">
      🍹 <span>SpritzMap</span>
    </div>
    <nav>
      {#if $isLoggedIn}
        <span class="username">{$authStore.user?.username}</span>
        <button onclick={() => authStore.logout()}>Abmelden</button>
      {:else}
        <button class="cta" onclick={() => (authOpen = true)}>Anmelden</button>
      {/if}
    </nav>
  </header>

  <main>
    <div class="sidebar">
      <FilterPanel />
    </div>
    <div class="map-wrap">
      <SpritzMap />
    </div>
  </main>
</div>

<AuthModal bind:open={authOpen} />

<style>
  :global(*, *::before, *::after) { box-sizing: border-box; margin: 0; padding: 0; }
  :global(body) { font-family: system-ui, sans-serif; }

  .app {
    display: flex;
    flex-direction: column;
    height: 100dvh;
  }

  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1.25rem;
    background: white;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1);
    z-index: 10;
  }

  .logo {
    font-size: 1.2rem;
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  nav { display: flex; align-items: center; gap: 12px; }

  .username { font-size: 0.875rem; color: #555; }

  button {
    padding: 6px 14px;
    border: 1.5px solid #ccc;
    border-radius: 6px;
    background: white;
    cursor: pointer;
    font-size: 0.875rem;
  }

  button.cta {
    background: #e8500a;
    color: white;
    border-color: #e8500a;
    font-weight: 600;
  }

  main { display: flex; flex: 1; overflow: hidden; }

  .sidebar { padding: 1rem; overflow-y: auto; z-index: 5; }

  .map-wrap { flex: 1; position: relative; }

  @media (max-width: 640px) {
    main { flex-direction: column-reverse; }
    .sidebar { padding: 0.75rem; display: flex; gap: 8px; overflow-x: auto; }
    .map-wrap { flex: 1; }
  }
</style>
