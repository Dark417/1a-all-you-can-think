import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

export const API = 'http://localhost:8000';

/** One SSE frame from the backend. Exactly one field is set. */
export interface ChatEvent {
  delta?: string;
  tool?: string;
  status?: string;
  error?: string;
}

export interface Health {
  status: string;
  framework: string;
  provider: string;
  model: string;
}

export interface Models {
  default: string;
  models: string[];
}

@Injectable({ providedIn: 'root' })
export class ChatService {
  health(): Promise<Health> {
    return fetch(`${API}/health`).then(r => r.json());
  }

  models(): Promise<Models> {
    return fetch(`${API}/models`).then(r => r.json());
  }

  reset(sessionId: string): Promise<void> {
    return fetch(`${API}/reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    }).then(() => undefined);
  }

  /** POST /chat and turn the SSE body into an Observable of parsed events.
   *  Uses fetch + ReadableStream because EventSource is GET-only.
   *  Unsubscribing aborts the request (and the graph run server-side). */
  send(sessionId: string, message: string, model: string): Observable<ChatEvent> {
    return new Observable<ChatEvent>(subscriber => {
      const ctrl = new AbortController();

      (async () => {
        try {
          const res = await fetch(`${API}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, message, model }),
            signal: ctrl.signal,
          });
          if (!res.ok || !res.body) {
            subscriber.next({ error: `HTTP ${res.status}` });
            subscriber.complete();
            return;
          }
          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buf = '';
          while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            const frames = buf.split('\n\n');
            buf = frames.pop() ?? '';                       // incomplete tail stays buffered
            for (const frame of frames) {
              const line = frame.split('\n').find(l => l.startsWith('data: '));
              if (!line) continue;
              const data = line.slice(6);
              if (data === '[DONE]') continue;
              subscriber.next(JSON.parse(data) as ChatEvent);
            }
          }
          subscriber.complete();
        } catch (e: unknown) {
          if ((e as Error).name !== 'AbortError') {
            subscriber.next({ error: String(e) });
          }
          subscriber.complete();
        }
      })();

      return () => ctrl.abort();
    });
  }
}
