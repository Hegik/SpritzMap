<script lang="ts">
  import { onMount } from 'svelte';
  import SpritzMap from '$lib/components/SpritzMap.svelte';
  import FilterPanel from '$lib/components/FilterPanel.svelte';
  import AuthModal from '$lib/components/AuthModal.svelte';
  import AppHeader from '$lib/components/AppHeader.svelte';
  import { drinks, selectedDrinkId } from '$lib/stores/map';
  import { api } from '$lib/api/client';

  let authOpen = $state(false);
  let spritzMap: ReturnType<typeof SpritzMap>;

  onMount(async () => {
    const list = await api.get<typeof $drinks>('/drinks/');
    drinks.set(list);
    const aperol = list.find((d: { name: string }) => d.name.toLowerCase().includes('aperol'));
    if (aperol) selectedDrinkId.set(aperol.id);
  });
</script>

<svelte:head>
  <title>SpritzMap</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
</svelte:head>

<div class="app">
  <AppHeader onlogintrigger={() => (authOpen = true)} />

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

  main {
    flex: 1;
    position: relative;
    overflow: hidden;
  }
</style>
