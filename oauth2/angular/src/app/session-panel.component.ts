import { DatePipe } from '@angular/common';
import { Component, DestroyRef, effect, inject, signal } from '@angular/core';
import { AuthService } from './auth.service';

@Component({
  selector: 'app-session-panel',
  standalone: true,
  template: `
    @if (auth.session(); as session) {
      <section class="card">
        <h2>Session</h2>
        <dl class="kv">
          <dt>Authenticated via</dt>
          <dd><code>{{ session.via }}</code> cookie (no token in JavaScript)</dd>
          <dt>Identity provider</dt>
          <dd><code>{{ auth.config()?.authMode === 'mock' ? 'mock IdP' : 'AWS Cognito' }}</code></dd>
          <dt>Issuer</dt>
          <dd class="mono-wrap">{{ session.token.issuer }}</dd>
          <dt>Groups</dt>
          <dd>
            @for (group of session.user.groups; track group) {
              <span class="chip">{{ group }}</span>
            } @empty {
              <em>none</em>
            }
          </dd>
          <dt>Access token expires</dt>
          <dd>
            in <strong>{{ countdown() }}s</strong>
            @if (countdown() === 0) {
              <em> — the next API call renews it automatically</em>
            }
          </dd>
          @if (session.token.refreshedAt) {
            <dt>Last refreshed</dt>
            <dd>{{ session.token.refreshedAt | date: 'mediumTime' }}</dd>
          }
        </dl>
        <div class="row">
          <button class="ghost" [disabled]="busy()" (click)="refresh()">Force token refresh</button>
          <button class="ghost" (click)="auth.reload()">Re-check session</button>
        </div>
      </section>
    }
  `,
  imports: [DatePipe],
})
export class SessionPanelComponent {
  readonly auth = inject(AuthService);
  readonly busy = signal(false);
  readonly countdown = signal(0);

  constructor() {
    effect(() => this.countdown.set(this.auth.session()?.token.expiresInSeconds ?? 0));
    const ticker = setInterval(() => this.countdown.update((c) => Math.max(0, c - 1)), 1000);
    inject(DestroyRef).onDestroy(() => clearInterval(ticker));
  }

  async refresh(): Promise<void> {
    this.busy.set(true);
    try {
      await this.auth.forceRefresh();
    } finally {
      this.busy.set(false);
    }
  }
}
