export const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

/** Absolute URL für vom Backend gelieferte Medienpfade (z. B. "/media/12/abc.webp"). */
export const mediaUrl = (path: string) => `${BASE_URL}${path}`;

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('token');
  const headers: Record<string, string> = {
    // Bei FormData setzt der Browser Content-Type inkl. Boundary selbst
    ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
    ...(options.headers as Record<string, string>),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(`${res.status}: ${err.detail ?? 'Request failed'}`);
  }
  const text = await res.text();
  return (text ? JSON.parse(text) : null) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  deleteWithBody: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'DELETE', body: JSON.stringify(body) }),
  upload: <T>(path: string, form: FormData) =>
    request<T>(path, { method: 'POST', body: form }),

  // OAuth2 form-encoded login
  async login(email: string, password: string): Promise<{ access_token: string }> {
    const body = new URLSearchParams({ username: email, password });
    const res = await fetch(`${BASE_URL}/auth/login`, {
      method: 'POST',
      body,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
    if (!res.ok) throw new Error('Invalid credentials');
    return res.json();
  },
};
