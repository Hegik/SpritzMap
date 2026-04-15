<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';

  onMount(() => {
    goto('/moderation/dashboard', { replaceState: true });
  });
</script>
