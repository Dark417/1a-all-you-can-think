/**
 * The only place this app knows anything about auth.
 *
 * There is no token handling here, because the browser never receives a token:
 * the backend keeps them and hands us an httpOnly session cookie instead. All
 * we have to do is send the cookie (`credentials: 'include'`) and echo the CSRF
 * cookie back in a header on writes.
 */
export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8080';
const APP = 'react';
const CSRF_COOKIE = 'csrf_token';

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
  }
}

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body && !headers.has('content-type')) headers.set('content-type', 'application/json');
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers.set('x-csrf-token', csrf);
  }

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers, credentials: 'include' });

  if (res.status === 204) return undefined as T;
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(payload.message ?? payload.error ?? res.statusText, res.status, payload.error);
  }
  return payload as T;
}

/**
 * Sign-in is a full page navigation, never a fetch. The browser has to *leave*
 * this app so that AWS can show its own page on its own origin - that is what
 * keeps our JavaScript out of the credential path.
 */
export const startLogin = () => {
  const returnTo = `${location.origin}${location.pathname}`;
  location.href = `${API_BASE}/auth/login?app=${APP}&returnTo=${encodeURIComponent(returnTo)}`;
};

export const startLogout = () => {
  location.href = `${API_BASE}/auth/logout?app=${APP}`;
};
