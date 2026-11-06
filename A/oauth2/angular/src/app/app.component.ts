import { Component, inject } from '@angular/core';
import { environment } from '../environment';
import { AuthService } from './auth.service';
import { NotesPanelComponent } from './notes-panel.component';
import { SessionPanelComponent } from './session-panel.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [NotesPanelComponent, SessionPanelComponent],
  template: `
    <div class="page">
      <header>
        <div>
          <span class="badge angular">Angular standalone</span>
          <h1>Sign in with AWS Cognito</h1>
        </div>
        @if (auth.status() === 'authenticated' && auth.user(); as user) {
          <div class="who">
            <span>{{ user.name ?? user.username }}</span>
            <button class="ghost" (click)="auth.signOut()">Sign out</button>
          </div>
        }
      </header>

      @if (auth.error(); as message) {
        <p class="error">Login failed — {{ message }}</p>
      }

      @switch (auth.status()) {
        @case ('loading') {
          <p class="muted">Checking your session…</p>
        }
        @case ('anonymous') {
          <section class="card centered">
            <h2>You are signed out</h2>
            <p class="muted">
              Clicking below sends the browser to
              <code>{{ auth.config()?.authMode === 'mock' ? 'the mock IdP' : 'the Cognito Hosted UI' }}</code>.
              Your password is typed there, not here — this app never sees it, and never receives a token.
            </p>
            <button class="primary big" (click)="auth.signIn()">Sign in</button>
            <p class="muted small">
              Mock users: <code>alice</code> (admin) or <code>bob</code> (viewer), password <code>Password1!</code>
            </p>
          </section>
        }
        @case ('authenticated') {
          <div class="grid">
            <app-notes-panel />
            <app-session-panel />
          </div>
        }
      }

      <footer class="muted small">
        All three sample UIs (React, Angular, Next.js) talk to the same backend at <code>{{ apiBaseUrl }}</code>.
      </footer>
    </div>
  `,
})
export class AppComponent {
  readonly auth = inject(AuthService);
  readonly apiBaseUrl = environment.apiBaseUrl;
}
