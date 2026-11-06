import { useCallback, useEffect, useState } from 'react';
import { ApiError, api } from '../api/client';
import type { Note, NotesResponse } from '../api/types';
import { useAuth } from '../auth/AuthProvider';

/** The actual "app". Every call below is authorized by the session cookie. */
export function NotesPanel() {
  const { user } = useAuth();
  const [notes, setNotes] = useState<Note[]>([]);
  const [canDeleteAny, setCanDeleteAny] = useState(false);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api<NotesResponse>('/api/notes');
      setNotes(data.notes);
      setCanDeleteAny(data.permissions.canDeleteAny);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const add = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!title.trim()) return;
    try {
      await api('/api/notes', { method: 'POST', body: JSON.stringify({ title, body }) });
      setTitle('');
      setBody('');
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  };

  const remove = async (id: string) => {
    try {
      await api(`/api/notes/${id}`, { method: 'DELETE' });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  };

  const mine = (note: Note) => note.ownerSub === user?.sub;

  return (
    <section className="card">
      <div className="card-head">
        <h2>Notes</h2>
        <button className="ghost" onClick={() => void load()}>Reload</button>
      </div>

      {error && <p className="error">{error}</p>}

      <form className="new-note" onSubmit={add}>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title" aria-label="Title" />
        <input value={body} onChange={(e) => setBody(e.target.value)} placeholder="Body" aria-label="Body" />
        <button type="submit" className="primary">Add</button>
      </form>

      {loading ? (
        <p className="muted">Loading…</p>
      ) : (
        <ul className="notes">
          {notes.map((note) => (
            <li key={note.id}>
              <div>
                <strong>{note.title}</strong>
                <p>{note.body}</p>
                <span className="muted">
                  {note.ownerName}
                  {mine(note) && ' (you)'} · {new Date(note.createdAt).toLocaleDateString()}
                </span>
              </div>
              <button
                className="danger"
                disabled={!mine(note) && !canDeleteAny}
                title={!mine(note) && !canDeleteAny ? 'Only the owner or an admin can delete this' : 'Delete'}
                onClick={() => void remove(note.id)}
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="muted small">
        Deleting someone else's note requires the <code>admin</code> group. Sign in as <code>bob</code> to see the
        button disabled — and note that the API rejects it too, the UI is only being polite.
      </p>
    </section>
  );
}
