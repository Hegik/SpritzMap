import { writable } from 'svelte/store';

export interface Drink {
  id: number;
  name: string;
  color_hex: string;
}

export const drinks = writable<Drink[]>([]);
export const selectedDrinkId = writable<number | null>(null);
export const selectedPriceTier = writable<string | null>(null);
