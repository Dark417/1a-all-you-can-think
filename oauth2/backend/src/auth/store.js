import crypto from 'node:crypto';
import { config } from '../config.js';

/**
 * In-memory stores for (a) in-flight login transactions and (b) sessions.
 *
 * Swap both for Redis / DynamoDB / ElastiCache before you run more than one
 * instance - that is the only change needed, the interfaces below are tiny on
 * purpose. Tokens live here, server side, and never reach the browser.
 */

const now = () => Date.now();
export const randomId = (bytes = 32) => crypto.randomBytes(bytes).toString('base64url');

class TtlMap {
  #map = new Map();
  set(key, value, ttlMs) {
    this.#map.set(key, { value, expiresAt: now() + ttlMs });
    return key;
  }
  get(key) {
    const hit = this.#map.get(key);
    if (!hit) return null;
    if (hit.expiresAt < now()) {
      this.#map.delete(key);
      return null;
    }
    return hit.value;
  }
  delete(key) {
    this.#map.delete(key);
  }
  sweep() {
    for (const [k, v] of this.#map) if (v.expiresAt < now()) this.#map.delete(k);
  }
  get size() {
    return this.#map.size;
  }
  *entries() {
    yield* this.#map.entries();
  }
}

/** state -> { nonce, codeVerifier, returnTo, app }. Short lived: a login has 10 minutes to finish. */
const transactions = new TtlMap();
/** sid -> { profile, accessToken, idToken, refreshToken, accessTokenExpiresAt, csrfToken, ... } */
const sessions = new TtlMap();

setInterval(() => {
  transactions.sweep();
  sessions.sweep();
}, 60_000).unref();

export const txStore = {
  create(data) {
    const state = randomId(24);
    transactions.set(state, data, 10 * 60_000);
    return state;
  },
  take(state) {
    const value = transactions.get(state);
    transactions.delete(state); // one-shot: replaying a code is not allowed
    return value;
  },
};

export const sessionStore = {
  create(data) {
    const sid = randomId(32);
    sessions.set(sid, { ...data, createdAt: now() }, config.session.ttlSeconds * 1000);
    return sid;
  },
  get(sid) {
    return sid ? sessions.get(sid) : null;
  },
  update(sid, patch) {
    const current = sessions.get(sid);
    if (!current) return null;
    const next = { ...current, ...patch };
    // Keep the original absolute expiry; do not let refresh extend it forever.
    const remaining = config.session.ttlSeconds * 1000 - (now() - current.createdAt);
    sessions.set(sid, next, Math.max(remaining, 1000));
    return next;
  },
  destroy(sid) {
    if (sid) sessions.delete(sid);
  },
  stats() {
    return { sessions: sessions.size, pendingLogins: transactions.size };
  },
};
