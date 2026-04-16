import { writable } from 'svelte/store';

export interface Drink {
  id: number;
  name: string;
  color_hex: string;
}

export interface CityMeta {
  id: number;
  name: string;
  slug: string;
  center_lat: number;
  center_lon: number;
  default_zoom: number;
  wms_layer: string | null;
}

export const drinks = writable<Drink[]>([]);
export const selectedDrinkId = writable<number | null>(null);
export const selectedPriceTier = writable<string | null>(null);
export const cities = writable<CityMeta[]>([]);
export const selectedCity = writable<CityMeta | null>(null);
