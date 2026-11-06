export interface User {
  sub: string;
  username: string;
  email: string | null;
  name: string | null;
  groups: string[];
}

export interface SessionResponse {
  authenticated: true;
  via: 'session' | 'bearer';
  user: User;
  token: {
    expiresAt: string | null;
    expiresInSeconds: number | null;
    issuer: string;
    scope: string | null;
    refreshedAt: string | null;
  };
}

export interface Note {
  id: string;
  ownerSub: string;
  ownerName: string;
  title: string;
  body: string;
  createdAt: string;
  updatedAt?: string;
}

export interface NotesResponse {
  notes: Note[];
  permissions: { canDeleteAny: boolean };
}

export interface AuthConfig {
  authMode: 'mock' | 'cognito';
  issuer: string;
  clientId: string;
  scopes: string[];
  redirectUri: string;
}
