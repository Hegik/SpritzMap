<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { t } from '$lib/i18n';

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
    <p>{$t.verify.loading}</p>
  {:else if status === 'success'}
    <h1>{$t.verify.success_heading}</h1>
    <p>{$t.verify.success_body}</p>
    <a href="/">{$t.verify.to_map}</a>
  {:else}
    <h1>{$t.verify.error_heading}</h1>
    <p>{$t.verify.error_body}</p>
    <a href="/">{$t.verify.to_map}</a>
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
