<script lang="ts">
	import favicon from '$lib/assets/favicon.svg';
	import { onMount } from 'svelte';
	import { api } from '$lib/api/client';
	import { authStore } from '$lib/stores/auth';

	let { children } = $props();

	// Profil hier statt auf einzelnen Seiten laden, damit auch ein Neuladen von /account oder /moderation klappt
	onMount(() => authStore.init(() => api.get('/auth/me')));
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<meta property="og:title" content="SpritzMap" />
	<meta property="og:description" content="Spritz-Index für Berlin – Aperol, Limoncello & Co." />
	<meta property="og:image" content="/og-image.png" />
	<meta property="og:image:width" content="1200" />
	<meta property="og:image:height" content="630" />
	<meta property="og:type" content="website" />
	<meta name="twitter:card" content="summary_large_image" />
	<meta name="twitter:image" content="/og-image.png" />
</svelte:head>

{@render children()}
