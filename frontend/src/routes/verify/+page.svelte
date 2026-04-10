<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';

  const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

  let status = $state<'loading' | 'success' | 'error'>('loading');

  onMount(async () => {
    const token = $page.url.searchParams.get('token');
    if (!token) { status = 'error'; return; }

    try {
      const res = await fetch(`${API_URL}/auth/verify?token=${token}`);
      status = res.ok ? 'success' : 'error';
    } catch {
      status = 'error';
    }
  });
</script>

<div class="wrap">
  {#if status === 'loading'}
    <p>Wird überprüft…</p>
  {:else if status === 'success'}
    <h1>✓ E-Mail bestätigt</h1>
    <p>Dein Konto ist jetzt aktiv. Du kannst dich einloggen.</p>
    <a href="/">Zur Karte</a>
  {:else}
    <h1>Ungültiger Link</h1>
    <p>Der Link ist abgelaufen oder wurde bereits verwendet.</p>
    <a href="/">Zur Karte</a>
  {/if}
</div>

<style>
  .wrap {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100dvh;
    gap: 1rem;
    font-family: system-ui, sans-serif;
  }
  h1 { font-size: 1.5rem; }
  a {
    padding: 8px 20px;
    background: #e8500a;
    color: white;
    border-radius: 6px;
    text-decoration: none;
    font-weight: 600;
  }
</style>
