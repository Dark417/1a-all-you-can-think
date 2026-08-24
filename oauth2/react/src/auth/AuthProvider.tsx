import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { ApiError, api, startLogin, startLogout } from '../api/client';
import type { AuthConfig, SessionResponse, User } from '../api/types';

type Status = 'loading' | 'anonymous' | 'authenticated';

interface AuthState {
  status: Status;
  user: User | null;
  session: SessionResponse | null;
  config: AuthConfig | null;
  error: string | null;
  reload: () => Promise<void>;
  signIn: () => void;
  signOut: () => void;
  forceRefresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>('loading');
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [error, setError] = useState<string | null>(readAuthErrorFromUrl());

  /**
   * "Am I logged in?" is a question only the backend can answer, because the
   * session lives in a cookie this code cannot read. So we ask, once, on load.
   */
  const reload = useCallback(async () => {
    try {
      const next = await api<SessionResponse>('/auth/session');
      setSession(next);
      setStatus('authenticated');
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setSession(null);
        setStatus('anonymous');
      } else {
        setError(err instanceof Error ? err.message : String(err));
        setStatus('anonymous');
      }
    }
  }, []);

  useEffect(() => {
    void reload();
    api<AuthConfig>('/auth/config').then(setConfig).catch(() => undefined);
  }, [reload]);

  const forceRefresh = useCallback(async () => {
    await api('/auth/refresh', { method: 'POST' });
    await reload();
  }, [reload]);

  const value = useMemo<AuthState>(
    () => ({
      status,
      user: session?.user ?? null,
      session,
      config,
      error,
      reload,
      signIn: startLogin,
      signOut: startLogout,
      forceRefresh,
    }),
    [status, session, config, error, reload, forceRefresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}

/** The backend redirects failures back here as ?auth_error=... */
function readAuthErrorFromUrl(): string | null {
  const params = new URLSearchParams(location.search);
  const err = params.get('auth_error');
  if (!err) return null;
  const description = params.get('auth_error_description');
  history.replaceState(null, '', location.pathname);
  return description ? `${err}: ${description}` : err;
}
