'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { ApiError, api, startLogin, startLogout } from '@/lib/api';
import type { AuthConfig, SessionResponse, User } from '@/lib/types';

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
  const [error, setError] = useState<string | null>(null);

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
    // Read in an effect, not during render: this component is prerendered on
    // the server, where there is no window.location to read.
    const params = new URLSearchParams(window.location.search);
    const authError = params.get('auth_error');
    if (authError) {
      const description = params.get('auth_error_description');
      setError(description ? `${authError}: ${description}` : authError);
      history.replaceState(null, '', window.location.pathname);
    }
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
