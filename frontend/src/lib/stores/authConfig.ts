import { writable, get } from 'svelte/store';
import { api, BASE_URL } from '$lib/api/client';

export interface AuthConfig {
  // legacy: eigene Konten · both: Übergang (Authentik + alter Login) · authentik: nur Authentik
  mode: 'legacy' | 'both' | 'authentik';
  account_url: string | null;
  unenrollment_url: string | null;
}

export const authConfig = writable<AuthConfig>({ mode: 'legacy', account_url: null, unenrollment_url: null });
let loaded: Promise<AuthConfig> | null = null;

export function loadAuthConfig(): Promise<AuthConfig> {
  loaded ??= api
    .get<AuthConfig>('/auth/config')
    .then((c) => { authConfig.set(c); return c; })
    .catch(() => get(authConfig));
  return loaded;
}

/** Start des Authentik-Logins; `signup` springt direkt in die Registrierung. */
export function oidcLoginUrl(signup = false, next?: string): string {
  const params = new URLSearchParams({ next: next ?? `${location.pathname}${location.search}` });
  if (signup) params.set('signup', '1');
  return `${BASE_URL}/auth/oidc/login?${params}`;
}
