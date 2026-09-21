import { writable, derived } from 'svelte/store';

interface User {
  id: number;
  email: string;
  username: string;
  role: 'user' | 'moderator' | 'admin';
  // Städte mit Bearbeitungsrechten; null = alle (Admin)
  moderated_city_ids?: number[] | null;
}

const token = writable<string | null>(
  typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null
);
export const user = writable<User | null>(null);

token.subscribe((val) => {
  if (typeof localStorage !== 'undefined') {
    if (val) localStorage.setItem('token', val);
    else localStorage.removeItem('token');
  }
});

export const isLoggedIn = derived(token, ($t) => !!$t);
export const isModerator = derived(user, ($u) => $u?.role === 'moderator' || $u?.role === 'admin');

// Moderatoren lesen überall, bearbeiten aber nur in zugewiesenen Städten
export const canModerate = derived(user, ($u) => (cityId: number | null | undefined): boolean => {
  if (!$u || cityId == null) return false;
  if ($u.role === 'admin') return true;
  return $u.role === 'moderator' && ($u.moderated_city_ids ?? []).includes(cityId);
});

export const authStore = {
  token,
  user,
  isLoggedIn,
  isModerator,
  setToken(t: string) {
    token.set(t);
  },
  setUser(u: User) {
    user.set(u);
  },
  logout() {
    token.set(null);
    user.set(null);
  },
};
