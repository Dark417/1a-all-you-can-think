import express from 'express';
import { requireAuth, requireCsrf, requireGroup } from '../auth/middleware.js';
import { createNote, deleteNote, getNote, listNotes, resetNotes, updateNote } from '../data/notes.js';
import { sessionStore } from '../auth/store.js';

/**
 * The business API. Deliberately boring - the interesting part is that every
 * route below is protected by exactly one line, and that line works the same
 * for a cookie-bearing browser and a Bearer-token service call.
 */
export function apiRouter() {
  const router = express.Router();

  /** Public - no auth. Useful for a "is the backend up?" check in the UIs. */
  router.get('/public/health', (_req, res) => {
    res.json({ status: 'ok', ...sessionStore.stats(), time: new Date().toISOString() });
  });

  router.get('/me', requireAuth, (req, res) => {
    res.json({ user: req.auth.profile, via: req.auth.via });
  });

  router.get('/notes', requireAuth, (req, res) => {
    const notes = listNotes();
    res.json({
      notes,
      // Let the UI grey out buttons the API would reject anyway.
      permissions: { canDeleteAny: (req.auth.profile.groups ?? []).includes('admin') },
    });
  });

  router.post('/notes', requireCsrf, requireAuth, (req, res) => {
    const title = String(req.body?.title ?? '').trim();
    const body = String(req.body?.body ?? '').trim();
    if (!title) return res.status(422).json({ error: 'validation_error', message: 'title is required' });
    res.status(201).json({ note: createNote({ title, body, owner: req.auth.profile }) });
  });

  router.patch('/notes/:id', requireCsrf, requireAuth, (req, res) => {
    const note = getNote(req.params.id);
    if (!note) return res.status(404).json({ error: 'not_found' });
    if (!canMutate(req.auth.profile, note)) {
      return res.status(403).json({ error: 'forbidden', message: 'You can only edit your own notes.' });
    }
    const patch = {};
    if (req.body?.title !== undefined) patch.title = String(req.body.title).trim();
    if (req.body?.body !== undefined) patch.body = String(req.body.body).trim();
    res.json({ note: updateNote(req.params.id, patch) });
  });

  router.delete('/notes/:id', requireCsrf, requireAuth, (req, res) => {
    const note = getNote(req.params.id);
    if (!note) return res.status(404).json({ error: 'not_found' });
    if (!canMutate(req.auth.profile, note)) {
      return res.status(403).json({ error: 'forbidden', message: 'You can only delete your own notes.' });
    }
    deleteNote(req.params.id);
    res.status(204).end();
  });

  /** Group-gated route, to show Cognito groups driving authorization. */
  router.post('/admin/reset', requireCsrf, requireAuth, requireGroup('admin'), (_req, res) => {
    res.json({ ok: true, count: resetNotes() });
  });

  return router;
}

/** Owner or admin. Cognito groups arrive as the `cognito:groups` claim. */
const canMutate = (profile, note) =>
  note.ownerSub === profile.sub || (profile.groups ?? []).includes('admin');
