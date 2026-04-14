<script lang="ts">
  import { t } from '$lib/i18n';

  let {
    open = $bindable(false),
  }: {
    open: boolean;
  } = $props();

  let html = $state('');
  let loaded = $state(false);

  $effect(() => {
    if (open && !loaded) {
      loadContent();
    }
  });

  async function loadContent() {
    try {
      const { marked } = await import('marked');
      const res = await fetch('/Anleitung.md');
      const text = await res.text();
      html = await marked.parse(text);
      loaded = true;
    } catch {
      html = `<p>${$t.help.error}</p>`;
      loaded = true;
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
      <button class="close-btn" aria-label={$t.help.close_aria} onclick={() => (open = false)}>
        ✕
      </button>
      <div class="content">
        {@html html}
      </div>
    </div>
  </div>
{/if}

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.55);
    display: flex;
    align-items: stretch;
    justify-content: center;
    z-index: 1000;
  }

  .modal {
    position: relative;
    background: white;
    width: 100%;
    max-width: 680px;
    height: 100%;
    overflow-y: auto;
    padding: 2rem 2rem 3rem;
    box-shadow: 0 0 40px rgba(0, 0, 0, 0.3);
  }

  @media (min-width: 641px) {
    .overlay {
      align-items: center;
    }
    .modal {
      height: auto;
      max-height: 90dvh;
      border-radius: 12px;
      padding: 2.5rem 2.5rem 3rem;
    }
  }

  .close-btn {
    position: sticky;
    top: 0;
    float: right;
    margin: -0.5rem -0.5rem 0.5rem 1rem;
    width: 36px;
    height: 36px;
    border: none;
    background: #f0f0f0;
    border-radius: 50%;
    font-size: 1rem;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    z-index: 1;
  }

  .close-btn:hover {
    background: #ddd;
  }

  /* Markdown content styles */
  .content :global(h1) {
    font-size: 1.5rem;
    font-weight: 700;
    margin: 0 0 1rem;
    color: #e8500a;
  }

  .content :global(h2) {
    font-size: 1.1rem;
    font-weight: 600;
    margin: 1.75rem 0 0.5rem;
    color: #333;
  }

  .content :global(h3) {
    font-size: 1rem;
    font-weight: 600;
    margin: 1.25rem 0 0.4rem;
    color: #444;
  }

  .content :global(p) {
    margin: 0 0 0.75rem;
    line-height: 1.6;
    color: #444;
  }

  .content :global(ul),
  .content :global(ol) {
    margin: 0 0 0.75rem 1.25rem;
    line-height: 1.6;
    color: #444;
  }

  .content :global(li) {
    margin-bottom: 0.25rem;
  }

  .content :global(strong) {
    font-weight: 600;
    color: #222;
  }

  .content :global(img) {
    max-width: 100%;
    border-radius: 8px;
    margin: 0.75rem 0;
    display: block;
  }

  .content :global(hr) {
    border: none;
    border-top: 1px solid #eee;
    margin: 1.5rem 0;
  }

  .content :global(code) {
    background: #f5f5f5;
    padding: 2px 5px;
    border-radius: 4px;
    font-size: 0.875em;
  }
</style>
