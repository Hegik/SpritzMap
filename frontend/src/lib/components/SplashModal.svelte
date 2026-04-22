<script lang="ts">
  import { untrack } from 'svelte';
  import { t } from '$lib/i18n';

  let {
    open = $bindable(false),
  }: {
    open: boolean;
  } = $props();

  let slides: { title: string; body: string }[] = $state([]);
  let currentIndex = $state(0);
  let neverAgain = $state(false);
  let loaded = $state(false);

  let touchStartX = 0;

  $effect(() => {
    if (!loaded) loadContent();
  });

  $effect(() => {
    const isOpen = open;
    if (isOpen) {
      untrack(() => {
        if (slides.length > 0) {
          const last = parseInt(localStorage.getItem('spritzmap_splash_index') ?? '-1');
          currentIndex = (last + 1) % slides.length;
          localStorage.setItem('spritzmap_splash_index', String(currentIndex));
        }
      });
    }
  });

  async function loadContent() {
    try {
      const { marked } = await import('marked');
      const res = await fetch('/splash.md');
      const text = await res.text();

      const sections = text.split(/^# /m).filter((s) => s.trim());
      slides = await Promise.all(
        sections.map(async (section) => {
          const newlineIdx = section.indexOf('\n');
          const title = newlineIdx >= 0 ? section.slice(0, newlineIdx).trim() : section.trim();
          const bodyText = newlineIdx >= 0 ? section.slice(newlineIdx + 1) : '';
          const body = await marked.parse(bodyText);
          return { title, body };
        }),
      );
      loaded = true;
    } catch {
      slides = [{ title: $t.splash.error, body: '' }];
      loaded = true;
    }
  }

  function close() {
    if (neverAgain) localStorage.setItem('spritzmap_splash_seen', '1');
    open = false;
  }

  function prev() {
    if (currentIndex > 0) currentIndex--;
  }

  function next() {
    if (currentIndex < slides.length - 1) currentIndex++;
  }

  function onTouchStart(e: TouchEvent) {
    touchStartX = e.touches[0].clientX;
  }

  function onTouchEnd(e: TouchEvent) {
    const dx = e.changedTouches[0].clientX - touchStartX;
    if (dx > 50) prev();
    else if (dx < -50) next();
  }
</script>

{#if open}
  <div
    class="overlay"
    onclick={close}
    onkeydown={(e) => e.key === 'Escape' && close()}
    role="dialog"
    aria-modal="true"
    tabindex="-1"
  >
    <div
      class="modal"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      ontouchstart={onTouchStart}
      ontouchend={onTouchEnd}
      role="presentation"
    >
      <button class="close-btn" aria-label={$t.splash.close_aria} onclick={close}>✕</button>

      {#if slides.length > 0}
        <h2 class="slide-title">{slides[currentIndex].title}</h2>

        <div class="slide-body">
          {@html slides[currentIndex].body}
        </div>

        {#if slides.length > 1}
          <button
            class="arrow arrow-left"
            aria-label="Vorheriger Slide"
            onclick={prev}
            disabled={currentIndex === 0}
          >‹</button>
          <button
            class="arrow arrow-right"
            aria-label="Nächster Slide"
            onclick={next}
            disabled={currentIndex === slides.length - 1}
          >›</button>

          <div class="dots">
            {#each slides as _, i}
              <button
                class="dot"
                class:active={i === currentIndex}
                aria-label={`Slide ${i + 1}`}
                onclick={() => (currentIndex = i)}
              ></button>
            {/each}
          </div>
        {/if}
      {/if}

      <div class="bottom-bar">
        <label class="not-again">
          <input type="checkbox" bind:checked={neverAgain} />
          {$t.splash.not_again}
        </label>
        <button class="btn-close" onclick={close}>{$t.splash.btn_close}</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1001;
    padding: 1rem;
  }

  .modal {
    position: relative;
    background: #e8500a;
    color: white;
    width: 100%;
    max-width: 460px;
    border-radius: 16px;
    padding: 1.75rem 1.75rem 1.25rem;
    box-shadow: 0 8px 40px rgba(0, 0, 0, 0.35);
    user-select: none;
  }

  .close-btn {
    position: absolute;
    top: 1rem;
    right: 1rem;
    width: 30px;
    height: 30px;
    border: none;
    background: rgba(255, 255, 255, 0.2);
    color: white;
    border-radius: 50%;
    font-size: 0.9rem;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .close-btn:hover {
    background: rgba(255, 255, 255, 0.35);
  }

  .slide-title {
    font-size: 1.3rem;
    font-weight: 700;
    margin: 0 2rem 1rem 0;
    color: white;
  }

  .slide-body {
    min-height: 80px;
    margin-bottom: 1.25rem;
  }

  .slide-body :global(p) {
    margin: 0 0 0.6rem;
    line-height: 1.6;
    color: rgba(255, 255, 255, 0.92);
  }

  .slide-body :global(strong) {
    font-weight: 600;
    color: white;
  }

  .slide-body :global(ul),
  .slide-body :global(ol) {
    margin: 0 0 0.6rem 1.25rem;
    line-height: 1.6;
    color: rgba(255, 255, 255, 0.92);
  }

  /* Desktop arrows */
  .arrow {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    width: 36px;
    height: 36px;
    border: none;
    background: rgba(255, 255, 255, 0.15);
    color: white;
    border-radius: 50%;
    font-size: 1.4rem;
    cursor: pointer;
    display: none;
    align-items: center;
    justify-content: center;
    transition: background 0.15s;
    line-height: 1;
  }

  .arrow:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.3);
  }

  .arrow:disabled {
    opacity: 0.25;
    cursor: default;
  }

  .arrow-left { left: -48px; }
  .arrow-right { right: -48px; }

  @media (min-width: 641px) {
    .arrow { display: flex; }
  }

  /* Mobile dots */
  .dots {
    display: flex;
    justify-content: center;
    gap: 8px;
    margin-bottom: 1rem;
  }

  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    border: none;
    background: rgba(255, 255, 255, 0.35);
    cursor: pointer;
    padding: 0;
    transition: background 0.15s, transform 0.15s;
  }

  .dot.active {
    background: white;
    transform: scale(1.2);
  }

  @media (min-width: 641px) {
    .dots { display: none; }
  }

  .bottom-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    border-top: 1px solid rgba(255, 255, 255, 0.25);
    padding-top: 1rem;
    margin-top: 0.25rem;
  }

  .not-again {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.82rem;
    color: rgba(255, 255, 255, 0.85);
    cursor: pointer;
    flex-shrink: 0;
  }

  .not-again input {
    accent-color: white;
    cursor: pointer;
  }

  .btn-close {
    padding: 6px 16px;
    background: rgba(255, 255, 255, 0.2);
    color: white;
    border: 1px solid rgba(255, 255, 255, 0.4);
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
    transition: background 0.15s;
  }

  .btn-close:hover {
    background: rgba(255, 255, 255, 0.35);
  }
</style>
