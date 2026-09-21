<script lang="ts">
  import { onMount } from 'svelte';

  // Rechtstexte liegen als Markdown in static/, damit sie ohne Code-Änderung anpassbar bleiben
  let { src, title }: { src: string; title: string } = $props();
  let html = $state('');

  onMount(async () => {
    try {
      const { marked } = await import('marked');
      const res = await fetch(src);
      if (!res.ok) throw new Error(String(res.status));
      html = await marked.parse(await res.text());
    } catch {
      html = `<p>${title} konnte nicht geladen werden.</p>`;
    }
  });
</script>

<svelte:head>
  <title>{title} – SpritzMap</title>
</svelte:head>

<main>
  <nav>
    <a href="/">← Zur Karte</a>
    <a href="/impressum">Impressum</a>
    <a href="/datenschutz">Datenschutz</a>
  </nav>
  <article>{@html html}</article>
</main>

<style>
  main {
    max-width: 760px;
    margin: 0 auto;
    padding: 1.5rem 16px 3rem;
    line-height: 1.55;
    color: #222;
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }
  nav { display: flex; gap: 1.25rem; flex-wrap: wrap; }
  nav a { color: #e8500a; text-decoration: none; font-weight: 600; }
  nav a:first-child { margin-right: auto; }
  article :global(h1) { font-size: 1.6rem; margin: 1rem 0; }
  article :global(h2) { font-size: 1.15rem; margin: 1.75rem 0 0.5rem; }
  article :global(blockquote) {
    margin: 1rem 0;
    padding: 0.5rem 1rem;
    border-left: 4px solid #e8500a;
    background: #fff4ee;
  }
  article :global(a) { color: #e8500a; overflow-wrap: anywhere; }
</style>
