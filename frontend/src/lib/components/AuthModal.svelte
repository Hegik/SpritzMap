<script lang="ts">
  import { authStore } from '$lib/stores/auth';
  import { api } from '$lib/api/client';

  let {
    open = $bindable(false),
    onloggedin = () => {},
  }: { open: boolean; onloggedin?: () => void } = $props();

  let mode = $state<'login' | 'register' | 'forgot'>('login');
  let email = $state('');
  let username = $state('');
  let password = $state('');
  let error = $state('');
  let info = $state('');
  let loading = $state(false);

  async function submit() {
    error = '';
    loading = true;
    try {
      if (mode === 'login') {
        const { access_token } = await api.login(email, password);
        authStore.setToken(access_token);
        const me = await api.get<{ id: number; email: string; username: string; role: 'user' | 'moderator' | 'admin' }>('/auth/me');
        authStore.setUser(me);
        open = false;
        onloggedin();
      } else if (mode === 'register') {
        await api.post('/auth/register', { email, username, password });
        mode = 'login';
        info = 'Registrierung erfolgreich — bitte bestätige deine E-Mail.';
      } else {
        await api.post('/auth/forgot-password', { email });
        info = 'Falls die E-Mail existiert, wurde ein Link gesendet.';
      }
    } catch (e: unknown) {
      error = e instanceof Error ? e.message : 'Fehler';
    } finally {
      loading = false;
    }
  }
</script>

{#if open}
  <div
    class="overlay"
    onclick={() => (open = false)}
    onkeydown={(e) => e.key === 'Escape' && (open = false)}
    role="dialog"
    aria-modal="true"
    tabindex="-1"
  >
    <div
      class="modal"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="presentation"
    >
      <h2>{mode === 'login' ? 'Einloggen' : mode === 'register' ? 'Registrieren' : 'Passwort vergessen'}</h2>

      <form onsubmit={(e) => { e.preventDefault(); submit(); }}>
        <label>
          E-Mail
          <input type="email" bind:value={email} required autocomplete="email" />
        </label>

        {#if mode === 'register'}
          <label>
            Nutzername
            <input type="text" bind:value={username} required minlength={3} maxlength={50} />
          </label>
        {/if}

        {#if mode !== 'forgot'}
          <label>
            Passwort
            <input
              type="password"
              bind:value={password}
              required
              minlength={8}
              autocomplete={mode === 'login' ? 'current-password' : 'new-password'}
            />
          </label>
        {/if}

        {#if info}
          <p class="info">{info}</p>
        {/if}
        {#if error}
          <p class="error">{error}</p>
        {/if}

        <button type="submit" disabled={loading}>
          {loading ? 'Lädt…' : mode === 'login' ? 'Einloggen' : mode === 'register' ? 'Registrieren' : 'Link senden'}
        </button>
      </form>

      <button class="switch" onclick={() => { mode = mode === 'login' ? 'register' : 'login'; error = ''; info = ''; }}>
        {mode === 'login' ? 'Noch kein Konto? Registrieren' : mode === 'register' ? 'Schon ein Konto? Einloggen' : 'Zurück zum Login'}
      </button>
      {#if mode === 'login'}
        <button class="switch" onclick={() => { mode = 'forgot'; error = ''; }}>
          Passwort vergessen?
        </button>
      {/if}
    </div>
  </div>
{/if}

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.45);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .modal {
    background: white;
    border-radius: 12px;
    padding: 2rem;
    width: min(400px, 92vw);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  }

  h2 { margin: 0 0 1.5rem; font-size: 1.25rem; }

  form { display: flex; flex-direction: column; gap: 1rem; }

  label { display: flex; flex-direction: column; gap: 4px; font-size: 0.875rem; font-weight: 500; }

  input {
    padding: 8px 12px;
    border: 1.5px solid #ddd;
    border-radius: 6px;
    font-size: 1rem;
  }

  input:focus { outline: none; border-color: #555; }

  button[type='submit'] {
    padding: 10px;
    background: #e8500a;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
  }

  button[type='submit']:disabled { opacity: 0.6; }

  .switch {
    margin-top: 1rem;
    background: none;
    border: none;
    color: #666;
    font-size: 0.875rem;
    cursor: pointer;
    text-decoration: underline;
    width: 100%;
  }

  .error { color: #c00; font-size: 0.875rem; margin: 0; }
  .info { color: green; font-size: 0.875rem; margin: 0; }
</style>
