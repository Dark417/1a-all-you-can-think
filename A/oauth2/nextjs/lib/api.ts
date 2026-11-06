/**
 * Identical in spirit to the React and Angular clients: send the cookie, echo
 * the CSRF token, never touch a JWT.
 *
 * Worth calling out for Next specifically: this app *has* a server, so it could
 * have hosted the BFF itself in a route handler under app/api/. It does not,
 * on purpose - the point of this repo is three different frontends sharing one
 * backend. In a Next-only product, moving the /auth routes into this app is a
 * perfectly good (and one-fewer-service) choice; the flow would be identical.
 */
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8080';
const APP = 'nextjs';
const CSRF_COOKIE = 'csrf_token';

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
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

/** A full page navigation, not a fetch - the browser must leave for the IdP. */
export function startLogin() {
  const returnTo = `${window.location.origin}${window.location.pathname}`;
  window.location.href = `${API_BASE}/auth/login?app=${APP}&returnTo=${encodeURIComponent(returnTo)}`;
}

export function startLogout() {
  window.location.href = `${API_BASE}/auth/logout?app=${APP}`;
}
