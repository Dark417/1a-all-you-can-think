import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../environment';
import type { AuthConfig, SessionResponse } from './models';

type Status = 'loading' | 'anonymous' | 'authenticated';

/**
 * Auth state for the whole app. Notice what is missing: no token storage, no
 * expiry timers, no silent-refresh iframe. The session is a cookie this code
 * cannot even read, and the backend renews the underlying access token behind
 * our back. All we do is ask "who am I?" once on boot.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);

  readonly status = signal<Status>('loading');
  readonly session = signal<SessionResponse | null>(null);
  readonly config = signal<AuthConfig | null>(null);
  readonly error = signal<string | null>(null);

  readonly user = computed(() => this.session()?.user ?? null);
  readonly isAdmin = computed(() => (this.user()?.groups ?? []).includes('admin'));

  constructor() {
    this.readAuthErrorFromUrl();
    void this.reload();
    firstValueFrom(this.http.get<AuthConfig>(`${environment.apiBaseUrl}/auth/config`))
      .then((cfg) => this.config.set(cfg))
      .catch(() => undefined);
  }

  async reload(): Promise<void> {
    try {
      const session = await firstValueFrom(
        this.http.get<SessionResponse>(`${environment.apiBaseUrl}/auth/session`),
      );
      this.session.set(session);
      this.status.set('authenticated');
    } catch (err) {
      if (err instanceof HttpErrorResponse && err.status === 401) {
        this.session.set(null);
        this.status.set('anonymous');
      } else {
        this.error.set(err instanceof HttpErrorResponse ? err.message : String(err));
        this.status.set('anonymous');
      }
    }
  }

  async forceRefresh(): Promise<void> {
    await firstValueFrom(this.http.post(`${environment.apiBaseUrl}/auth/refresh`, {}));
    await this.reload();
  }

  /**
   * A full page navigation, NOT an XHR. The browser has to leave this origin so
   * the identity provider can render its own login page - which is exactly what
   * keeps this application out of the credential path.
   */
  signIn(): void {
    const returnTo = `${location.origin}${location.pathname}`;
    location.href =
      `${environment.apiBaseUrl}/auth/login?app=${environment.appName}` +
      `&returnTo=${encodeURIComponent(returnTo)}`;
  }

  signOut(): void {
    location.href = `${environment.apiBaseUrl}/auth/logout?app=${environment.appName}`;
  }

  /** The backend redirects failed logins back with ?auth_error=... */
  private readAuthErrorFromUrl(): void {
    const params = new URLSearchParams(location.search);
    const err = params.get('auth_error');
    if (!err) return;
    const description = params.get('auth_error_description');
    this.error.set(description ? `${err}: ${description}` : err);
    history.replaceState(null, '', location.pathname);
  }
}
