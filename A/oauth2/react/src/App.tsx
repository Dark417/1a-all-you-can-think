import { useAuth } from './auth/AuthProvider';
import { NotesPanel } from './components/NotesPanel';
import { SessionPanel } from './components/SessionPanel';

export default function App() {
  const { status, user, error, signIn, signOut, config } = useAuth();

  return (
    <div className="page">
      <header>
        <div>
          <span className="badge react">React + Vite</span>
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
            Clicking below sends the browser to <code>{config?.authMode === 'mock' ? 'the mock IdP' : 'the Cognito Hosted UI'}</code>.
            Your password is typed there, not here — this app never sees it, and never receives a token.
          </p>
          <button className="primary big" onClick={signIn}>Sign in</button>
          <p className="muted small">Mock users: <code>alice</code> (admin) or <code>bob</code> (viewer), password <code>Password1!</code></p>
        </section>
      )}

      {status === 'authenticated' && (
        <div className="grid">
          <NotesPanel />
          <SessionPanel />
        </div>
      )}

      <footer className="muted small">
        All three sample UIs (React, Angular, Next.js) talk to the same backend at <code>{import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8080'}</code>.
      </footer>
    </div>
  );
}
