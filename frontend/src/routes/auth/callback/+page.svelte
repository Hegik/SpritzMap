<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { api } from '$lib/api/client';
  import { authStore } from '$lib/stores/auth';
  import { oidcLoginUrl } from '$lib/stores/authConfig';
  import { t } from '$lib/i18n';

  let error = $state('');

  onMount(async () => {
    const params = page.url.searchParams;
    const err = params.get('error');
    const code = params.get('code');
    if (err || !code) {
      error = $t.auth.callback_errors[err as keyof typeof $t.auth.callback_errors] ?? $t.auth.callback_errors.default;
      return;
    }
    try {
      // Einmal-Code gegen das SpritzMap-Token tauschen (das Token steht so nie in einer URL)
      const res = await api.post<{ access_token: string; next: string }>('/auth/oidc/exchange', { code });
      authStore.setToken(res.access_token);
      authStore.setUser(await api.get('/auth/me'));
      goto(res.next?.startsWith('/') ? res.next : '/', { replaceState: true });
    } catch {
      error = $t.auth.callback_errors.expired;
    }
  });
</script>

<svelte:head><title>{$t.auth.callback_title} – SpritzMap</title></svelte:head>

<main class="callback">
  {#if error}
    <h1>{$t.auth.callback_failed}</h1>
    <p>{error}</p>
    <div class="actions">
      <a class="btn-primary" href={oidcLoginUrl(false, '/')}>{$t.auth.btn_try_again}</a>
      <a href="/">{$t.auth.back_to_map}</a>
    </div>
  {:else}
    <p class="loading">{$t.auth.callback_title}…</p>
  {/if}
</main>

<style>
  .callback { max-width: 420px; margin: 4rem auto; padding: 0 1rem; text-align: center; font-family: inherit; }
  h1 { font-size: 1.3rem; }
  .loading { color: #888; }
  .actions { display: flex; gap: 1rem; justify-content: center; align-items: center; margin-top: 1.5rem; }
  .btn-primary {
    padding: 0.55rem 1.2rem;
    background: #e8500a;
    color: white;
    border-radius: 8px;
    text-decoration: none;
    font-weight: 600;
  }
  a { color: #e8500a; }
</style>
