<script lang="ts">
  import { onMount } from 'svelte';
  import logo from '$lib/assets/logo.svg?url';
  import SpritzMap from '$lib/components/SpritzMap.svelte';
  import FilterPanel from '$lib/components/FilterPanel.svelte';
  import AuthModal from '$lib/components/AuthModal.svelte';
  import { goto } from '$app/navigation';
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
  <title>SpritzMap</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
</svelte:head>

<div class="app">
  <header>
    <div class="logo">
      <img src={logo} alt="SpritzMap" class="logo-img" />
    </div>
    <nav>
      {#if $isLoggedIn}
        <button class="username-btn" onclick={() => goto('/account')}>{$user?.username}</button>
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
    padding: 0 1.25rem;
    height: 48px;
    background: #e8500a;
    z-index: 10;
  }

  .logo { display: flex; align-items: center; }

  .logo-img {
    height: 48px;
    width: auto;
    display: block;
  }

  nav { display: flex; align-items: center; gap: 12px; }

  .username-btn {
    padding: 4px 10px;
    border: 1.5px solid rgba(255, 255, 255, 0.4);
    border-radius: 6px;
    background: transparent;
    color: rgba(255, 255, 255, 0.9);
    cursor: pointer;
    font-size: 0.875rem;
    font-weight: 500;
  }
  .username-btn:hover { background: rgba(255, 255, 255, 0.15); color: white; }

  button {
    padding: 6px 14px;
    border: 1.5px solid rgba(255, 255, 255, 0.5);
    border-radius: 6px;
    background: transparent;
    color: white;
    cursor: pointer;
    font-size: 0.875rem;
  }

  button:hover { background: rgba(255, 255, 255, 0.15); }

  button.cta {
    background: white;
    color: #e8500a;
    border-color: white;
    font-weight: 600;
  }

  button.cta:hover { background: rgba(255, 255, 255, 0.9); }

  main {
    flex: 1;
    position: relative;
    overflow: hidden;
  }
</style>
