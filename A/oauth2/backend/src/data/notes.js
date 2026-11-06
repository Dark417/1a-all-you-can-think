import crypto from 'node:crypto';

/**
 * The demo domain: a tiny notes API. In-memory and seeded on boot, so you can
 * break it freely and restart. Swap for DynamoDB/RDS in a real app - nothing in
 * the auth layer above cares.
 */

const seed = [
  {
    id: 'n_1001',
    ownerSub: '11111111-1111-4111-8111-111111111111',
    ownerName: 'alice',
    title: 'Why the redirect URI points at the backend',
    body: 'So the authorization code is redeemed server side, where the PKCE verifier and the client secret live. The browser never sees a refresh token.',
    createdAt: '2026-01-04T09:12:00.000Z',
  },
  {
    id: 'n_1002',
    ownerSub: '22222222-2222-4222-8222-222222222222',
    ownerName: 'bob',
    title: 'Cookies vs localStorage',
    body: 'httpOnly + SameSite cookie: unreadable by injected JS. localStorage: readable by anything that manages to run on the page. Pick the first one.',
    createdAt: '2026-01-05T14:40:00.000Z',
  },
  {
    id: 'n_1003',
    ownerSub: '11111111-1111-4111-8111-111111111111',
    ownerName: 'alice',
    title: 'token_use matters',
    body: 'ID tokens and access tokens are signed by the same key. If you forget to check token_use your API will happily accept an ID token as authorization.',
    createdAt: '2026-01-06T08:02:00.000Z',
  },
];

let notes = structuredClone(seed);

export const listNotes = () => notes.slice().sort((a, b) => b.createdAt.localeCompare(a.createdAt));

export const getNote = (id) => notes.find((n) => n.id === id) ?? null;

export function createNote({ title, body, owner }) {
  const note = {
    id: `n_${crypto.randomBytes(5).toString('hex')}`,
    ownerSub: owner.sub,
    ownerName: owner.username,
    title,
    body,
    createdAt: new Date().toISOString(),
  };
  notes.unshift(note);
  return note;
}

export function updateNote(id, patch) {
  const note = getNote(id);
  if (!note) return null;
  Object.assign(note, patch, { updatedAt: new Date().toISOString() });
  return note;
}

export function deleteNote(id) {
  const before = notes.length;
  notes = notes.filter((n) => n.id !== id);
  return notes.length < before;
}

export function resetNotes() {
  notes = structuredClone(seed);
  return notes.length;
}
