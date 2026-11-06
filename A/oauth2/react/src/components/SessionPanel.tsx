import { useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthProvider';

/** Shows what the backend knows about the session. Purely educational. */
export function SessionPanel() {
  const { session, config, forceRefresh, reload } = useAuth();
  const [busy, setBusy] = useState(false);
  const [countdown, setCountdown] = useState(session?.token.expiresInSeconds ?? 0);

  useEffect(() => {
    setCountdown(session?.token.expiresInSeconds ?? 0);
    const id = setInterval(() => setCountdown((c) => Math.max(0, c - 1)), 1000);
    return () => clearInterval(id);
  }, [session]);

  if (!session) return null;

  return (
    <section className="card">
      <h2>Session</h2>
      <dl className="kv">
        <dt>Authenticated via</dt>
        <dd><code>{session.via}</code> cookie (no token in JavaScript)</dd>
        <dt>Identity provider</dt>
        <dd><code>{config?.authMode === 'mock' ? 'mock IdP' : 'AWS Cognito'}</code></dd>
        <dt>Issuer</dt>
        <dd className="mono-wrap">{session.token.issuer}</dd>
        <dt>Groups</dt>
        <dd>{session.user.groups.length ? session.user.groups.map((g) => <span key={g} className="chip">{g}</span>) : <em>none</em>}</dd>
        <dt>Access token expires</dt>
        <dd>
          in <strong>{countdown}s</strong>
          {countdown === 0 && <em> — the next API call renews it automatically</em>}
        </dd>
        {session.token.refreshedAt && (
          <>
            <dt>Last refreshed</dt>
            <dd>{new Date(session.token.refreshedAt).toLocaleTimeString()}</dd>
          </>
        )}
      </dl>
      <div className="row">
        <button
          className="ghost"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await forceRefresh();
            } finally {
              setBusy(false);
            }
          }}
        >
          Force token refresh
        </button>
        <button className="ghost" onClick={() => void reload()}>Re-check session</button>
      </div>
    </section>
  );
}
