<script lang="ts">
  import logo from '$lib/assets/logo.svg?url';
  import { goto } from '$app/navigation';
  import { authStore, isLoggedIn, user } from '$lib/stores/auth';
  import { t } from '$lib/i18n';

  let {
    onlogintrigger = () => {},
  }: {
    onlogintrigger?: () => void;
  } = $props();

  let dropdownOpen = $state(false);

  function toggleDropdown() {
    dropdownOpen = !dropdownOpen;
  }

  function closeDropdown() {
    dropdownOpen = false;
  }

  function goToAccount() {
    closeDropdown();
    goto('/account');
  }

  function logout() {
    closeDropdown();
    authStore.logout();
  }
</script>

<!-- Close dropdown on outside click -->
{#if dropdownOpen}
  <div class="backdrop" onclick={closeDropdown} role="presentation"></div>
{/if}

<header>
  <div class="logo">
    <a href="/"><img src={logo} alt="SpritzMap" class="logo-img" /></a>
  </div>
  <nav>
    {#if $isLoggedIn}
      <div class="user-menu">
        <button class="username-btn" onclick={toggleDropdown}>
          {$user?.username}
          <span class="chevron" class:open={dropdownOpen}>▾</span>
        </button>
        {#if dropdownOpen}
          <div class="dropdown">
            <button onclick={goToAccount}>{$t.nav.account}</button>
            <button onclick={logout}>{$t.nav.logout}</button>
          </div>
        {/if}
      </div>
    {:else}
      <button class="cta" onclick={onlogintrigger}>{$t.nav.login}</button>
    {/if}
  </nav>
</header>

<style>
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 1.25rem;
    height: 48px;
    background: #e8500a;
    z-index: 20;
    position: relative;
  }

  .logo { display: flex; align-items: center; }
  .logo a { display: flex; align-items: center; }

  .logo-img {
    height: 48px;
    width: auto;
    display: block;
  }

  nav { display: flex; align-items: center; gap: 12px; }

  .user-menu {
    position: relative;
  }

  .username-btn {
    display: flex;
    align-items: center;
    gap: 5px;
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

  .chevron {
    font-size: 0.75rem;
    transition: transform 0.15s;
    display: inline-block;
  }
  .chevron.open { transform: rotate(180deg); }

  .dropdown {
    position: absolute;
    top: calc(100% + 6px);
    right: 0;
    background: white;
    border-radius: 8px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
    overflow: hidden;
    min-width: 140px;
    z-index: 100;
  }

  .dropdown button {
    display: block;
    width: 100%;
    padding: 10px 16px;
    border: none;
    background: transparent;
    color: #333;
    font-size: 0.9rem;
    text-align: left;
    cursor: pointer;
    border-radius: 0;
  }
  .dropdown button:hover { background: #f5f5f5; color: #e8500a; }

  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 19;
  }

  button.cta {
    padding: 6px 14px;
    border: 1.5px solid white;
    border-radius: 6px;
    background: white;
    color: #e8500a;
    cursor: pointer;
    font-size: 0.875rem;
    font-weight: 600;
  }
  button.cta:hover { background: rgba(255, 255, 255, 0.9); }
</style>
