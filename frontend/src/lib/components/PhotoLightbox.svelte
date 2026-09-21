<script lang="ts">
  import { api, mediaUrl } from '$lib/api/client';
  import { user, isModerator } from '$lib/stores/auth';
  import { t } from '$lib/i18n';
  import type { Photo } from '$lib/types/photo';

  let {
    open = $bindable(false),
    photos = $bindable<Photo[]>([]),
    index = $bindable(0),
    ondeleted = () => {},
  }: {
    open: boolean;
    photos: Photo[];
    index: number;
    ondeleted?: () => void;
  } = $props();

  let deleting = $state(false);
  let error = $state('');

  const current = $derived(photos[index]);
  const canDelete = $derived(!!current && ($isModerator || (current.user_id != null && current.user_id === $user?.id)));

  function prev() { index = (index - 1 + photos.length) % photos.length; }
  function next() { index = (index + 1) % photos.length; }

  function onKey(e: KeyboardEvent) {
    if (!open) return;
    if (e.key === 'Escape') open = false;
    else if (e.key === 'ArrowLeft' && photos.length > 1) prev();
    else if (e.key === 'ArrowRight' && photos.length > 1) next();
  }

  async function remove() {
    if (!current) return;
    deleting = true;
    error = '';
    try {
      await api.delete(`/photos/${current.id}`);
      photos = photos.filter((p) => p.id !== current.id);
      if (!photos.length) open = false;
      else index = Math.min(index, photos.length - 1);
      ondeleted();
    } catch (e: unknown) {
      error = e instanceof Error ? e.message : $t.photos.error_delete;
    } finally {
      deleting = false;
    }
  }

  function formatDate(iso: string | null) {
    return iso ? new Date(iso).toLocaleDateString('de-DE') : '';
  }
</script>

<svelte:window onkeydown={onKey} />

{#if open && current}
  <div
    class="overlay"
    onclick={() => (open = false)}
    onkeydown={() => {}}
    role="dialog"
    aria-modal="true"
    aria-label={$t.photos.lightbox_aria}
    tabindex="-1"
  >
    <div class="frame" onclick={(e) => e.stopPropagation()} onkeydown={() => {}} role="presentation">
      <img
        src={mediaUrl(current.url)}
        alt={$t.photos.photo_alt}
        width={current.width}
        height={current.height}
      />
      <div class="bar">
        <span>{formatDate(current.created_at)}{photos.length > 1 ? ` · ${index + 1}/${photos.length}` : ''}</span>
        {#if canDelete}
          <button class="delete" onclick={remove} disabled={deleting}>
            {deleting ? '…' : $t.photos.btn_delete}
          </button>
        {/if}
      </div>
      {#if error}<p class="error">{error}</p>{/if}
    </div>

    {#if photos.length > 1}
      <button class="nav left" aria-label={$t.photos.prev} onclick={(e) => { e.stopPropagation(); prev(); }}>‹</button>
      <button class="nav right" aria-label={$t.photos.next} onclick={(e) => { e.stopPropagation(); next(); }}>›</button>
    {/if}
    <button class="close" aria-label={$t.help.close_aria} onclick={() => (open = false)}>×</button>
  </div>
{/if}

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.85);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1100;
  }

  .frame {
    display: flex;
    flex-direction: column;
    max-width: min(92vw, 1000px);
    max-height: 90dvh;
  }

  img {
    max-width: 100%;
    max-height: calc(90dvh - 2.5rem);
    width: auto;
    height: auto;
    object-fit: contain;
    border-radius: 6px;
  }

  .bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 2px 0;
    color: #ddd;
    font-size: 0.8rem;
  }

  .delete {
    background: none;
    border: 1px solid #f44336;
    color: #ff8a80;
    border-radius: 5px;
    padding: 3px 10px;
    font-size: 0.8rem;
    cursor: pointer;
  }

  .error { color: #ff8a80; font-size: 0.8rem; margin: 4px 0 0; }

  .nav, .close {
    position: absolute;
    background: rgba(255, 255, 255, 0.15);
    color: white;
    border: none;
    border-radius: 50%;
    width: 40px;
    height: 40px;
    font-size: 1.6rem;
    line-height: 1;
    cursor: pointer;
  }

  .nav { top: 50%; transform: translateY(-50%); }
  .left { left: 12px; }
  .right { right: 12px; }
  .close { top: 12px; right: 12px; }
</style>
