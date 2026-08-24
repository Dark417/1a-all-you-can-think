'use client';

import { useAuth } from '@/components/AuthProvider';
import { NotesPanel } from '@/components/NotesPanel';
import { SessionPanel } from '@/components/SessionPanel';
import { API_BASE } from '@/lib/api';

export default function Home() {
  const { status, user, error, signIn, signOut, config } = useAuth();

  return (
    <div className="page">
      <header>
        <div>
          <span className="badge next">Next.js App Router</span>
          <h1>Sign in with AWS Cognito</h1>
        </div>
        {status === 'authenticated' && user && (
          <div className="who">
            <span>{user.name ?? user.username}</span>
            <button className="ghost" onClick={signOut}>Sign out</button>
          </div>
        )}
      </header>

      {error && <p className="error">Login failed — {error}</p>}

      {status === 'loading' && <p className="muted">Checking your session…</p>}

      {status === 'anonymous' && (
        <section className="card centered">
          <h2>You are signed out</h2>
          <p className="muted">
            Clicking below sends the browser to{' '}
            <code>{config?.authMode === 'mock' ? 'the mock IdP' : 'the Cognito Hosted UI'}</code>. Your password is
            typed there, not here — this app never sees it, and never receives a token.
          </p>
          <button className="primary big" onClick={signIn}>Sign in</button>
          <p className="muted small">
            Mock users: <code>alice</code> (admin) or <code>bob</code> (viewer), password <code>Password1!</code>
          </p>
        </section>
      )}

      {status === 'authenticated' && (
        <div className="grid">
          <NotesPanel />
          <SessionPanel />
        </div>
      )}

      <footer className="muted small">
        All three sample UIs (React, Angular, Next.js) talk to the same backend at <code>{API_BASE}</code>.
      </footer>
    </div>
  );
}
