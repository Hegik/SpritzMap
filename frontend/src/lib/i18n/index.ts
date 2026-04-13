import { readable } from 'svelte/store';
import de from './de';
import type { Translations } from './de';

// To add a new language: import it here and add to the map
const languages: Record<string, Translations> = { de };

export const t = readable<Translations>(languages['de']);
