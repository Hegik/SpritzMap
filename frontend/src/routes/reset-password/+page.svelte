<script lang="ts">
  import { page } from '$app/stores';

  const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

  let password = $state('');
  let password2 = $state('');
  let status = $state<'idle' | 'loading' | 'success' | 'error'>('idle');
  let error = $state('');

  async function submit() {
    if (password !== password2) { error = 'Passwörter stimmen nicht überein'; return; }
    if (password.length < 8) { error = 'Mindestens 8 Zeichen'; return; }

    error = '';
    status = 'loading';
    const token = $page.url.searchParams.get('token') ?? '';

    try {
      const res = await fetch(`${API_URL}/auth/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, password }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? 'Fehler');
      }
      status = 'success';
    } catch (e: unknown) {
      error = e instanceof Error ? e.message : 'Fehler';
      status = 'error';
    }
  }
</script>

<div class="wrap">
  {#if status === 'success'}
    <h1>Passwort geändert</h1>
    <p>Du kannst dich jetzt mit deinem neuen Passwort einloggen.</p>
    <a href="/">Zur Karte</a>
  {:else}
    <div class="card">
      <h1>Neues Passwort</h1>
      <form onsubmit={(e) => { e.preventDefault(); submit(); }}>
        <label>
          Neues Passwort
          <input type="password" bind:value={password} required minlength={8}
                 autocomplete="new-password" />
        </label>
        <label>
          Wiederholen
          <input type="password" bind:value={password2} required minlength={8}
                 autocomplete="new-password" />
        </label>
        {#if error}<p class="error">{error}</p>{/if}
        <button type="submit" disabled={status === 'loading'}>
          {status === 'loading' ? 'Wird gespeichert…' : 'Passwort ändern'}
        </button>
      </form>
    </div>
  {/if}
</div>

<style>
  .wrap {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100dvh;
    font-family: system-ui, sans-serif;
    gap: 1rem;
  }
  .card {
    background: white;
    border-radius: 12px;
    padding: 2rem;
    width: min(400px, 92vw);
    box-shadow: 0 4px 20px rgba(0,0,0,0.1);
  }
  h1 { font-size: 1.3rem; margin: 0 0 1.5rem; }
  form { display: flex; flex-direction: column; gap: 1rem; }
  label { display: flex; flex-direction: column; gap: 4px; font-size: 0.875rem; font-weight: 500; }
  input {
    padding: 8px 12px;
    border: 1.5px solid #ddd;
    border-radius: 6px;
    font-size: 1rem;
  }
  button {
    padding: 10px;
    background: #e8500a;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
  }
  button:disabled { opacity: 0.6; }
  .error { color: #c00; font-size: 0.875rem; margin: 0; }
  a {
    padding: 8px 20px;
    background: #e8500a;
    color: white;
    border-radius: 6px;
    text-decoration: none;
    font-weight: 600;
  }
</style>
