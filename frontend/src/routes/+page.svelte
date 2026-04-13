<script lang="ts">
  import { onMount } from 'svelte';
  import SpritzMap from '$lib/components/SpritzMap.svelte';
  import FilterPanel from '$lib/components/FilterPanel.svelte';
  import AuthModal from '$lib/components/AuthModal.svelte';
  import { authStore, isLoggedIn, user } from '$lib/stores/auth';
  import { drinks, selectedDrinkId } from '$lib/stores/map';
  import { api } from '$lib/api/client';
  import { t } from '$lib/i18n';

  let authOpen = $state(false);
  let spritzMap: ReturnType<typeof SpritzMap>;

  onMount(async () => {
    const list = await api.get<typeof $drinks>('/drinks/');
    drinks.set(list);
    const aperol = list.find((d: { name: string }) => d.name.toLowerCase().includes('aperol'));
    if (aperol) selectedDrinkId.set(aperol.id);

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
        <span class="username">{$user?.username}</span>
        <button onclick={() => authStore.logout()}>{$t.nav.logout}</button>
      {:else}
        <button class="cta" onclick={() => (authOpen = true)}>{$t.nav.login}</button>
      {/if}
    </nav>
  </header>

  <main>
    <SpritzMap bind:this={spritzMap} />
    <FilterPanel />
  </main>
</div>

<AuthModal bind:open={authOpen} onloggedin={() => spritzMap?.reloadMarkers()} />

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

  main {
    flex: 1;
    position: relative;
    overflow: hidden;
  }
</style>
