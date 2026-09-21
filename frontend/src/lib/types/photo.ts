export type GlassType = 'wine' | 'tumbler' | 'other';

export interface Photo {
  id: number;
  location_id: number;
  price_entry_id: number | null;
  user_id: number | null;
  url: string;
  thumb_url: string;
  width: number;
  height: number;
  created_at: string | null;
}
