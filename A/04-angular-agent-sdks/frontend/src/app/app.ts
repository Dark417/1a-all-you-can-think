import { Component, computed, inject, signal } from '@angular/core';
import { Subscription } from 'rxjs';
import { BACKENDS, Backend } from './backends';
import { ChatService, Health } from './chat.service';

interface Message {
  kind: 'user' | 'bot' | 'sys' | 'err';
  text: string;
}

@Component({
  selector: 'app-root',
  template: `
    <header>
      <h1>Agent SDK chat</h1>

      <!-- the backend switch: every option is a different FastAPI server -->
      <select [value]="backend().id" (change)="switchBackend($event)">
        @for (b of backends; track b.id) {
          <option [value]="b.id">{{ b.label }}</option>
        }
      </select>

      <span class="meta">
        @if (health(); as h) { {{ h.framework }} · {{ h.provider }} · {{ h.model }} }
        @else { {{ backend().url }} — unreachable }
      </span>

      <button class="ghost" (click)="newChat()">New chat</button>
    </header>

    <div class="log">
      @for (m of messages(); track $index) {
        <div class="msg {{ m.kind }}">{{ m.text }}</div>
      }
      @if (messages().length === 0) {
        <div class="msg sys">talking to <b>{{ backend().label }}</b> — say hi</div>
      }
    </div>

    <form (submit)="send($event)">
      <input #box [disabled]="busy()" placeholder="Type a message…" autocomplete="off" autofocus>
      <button type="submit" [disabled]="busy()">{{ busy() ? '…' : 'Send' }}</button>
      @if (busy()) { <button type="button" class="ghost" (click)="stop()">Stop</button> }
    </form>
  `,
  styles: [`
    header { display:flex; gap:12px; align-items:center; padding:12px 16px; background:var(--panel); border-bottom:1px solid #2a2e38; }
    h1 { font-size:16px; margin:0; font-weight:600; }
    select { padding:6px 8px; border-radius:8px; background:#0f1115; color:var(--fg); border:1px solid #333845; }
    .meta { color:var(--muted); font-size:13px; }
    header button { margin-left:auto; }
    .log { max-width:820px; margin:0 auto; padding:16px; display:flex; flex-direction:column; gap:10px; min-height:calc(100vh - 130px); }
    .msg { padding:10px 14px; border-radius:12px; max-width:78%; white-space:pre-wrap; word-wrap:break-word; }
    .user { align-self:flex-end; background:var(--me); }
    .bot  { align-self:flex-start; background:var(--bot); }
    .sys  { align-self:center; color:var(--muted); font-size:12px; }
    .err  { align-self:flex-start; background:#4a1f1f; color:#ffb3b3; }
    form { position:sticky; bottom:0; display:flex; gap:8px; padding:12px 16px; background:var(--panel); border-top:1px solid #2a2e38; }
    input { flex:1; padding:10px 12px; border-radius:8px; border:1px solid #333845; background:#0f1115; color:var(--fg); font-size:15px; }
    button { padding:10px 14px; border-radius:8px; border:0; background:var(--me); color:#fff; font-weight:600; cursor:pointer; }
    button.ghost { background:transparent; border:1px solid #333845; color:var(--muted); }
    button:disabled { opacity:.5; cursor:default; }
  `],
})
export class App {
  private chat = inject(ChatService);

  readonly backends = BACKENDS;
  readonly backend = signal<Backend>(BACKENDS[0]);
  readonly health = signal<Health | null>(null);
  readonly busy = signal(false);

  // one transcript + one session id per backend, so switching keeps both conversations
  private transcripts = new Map<string, Message[]>();
  private sessions = new Map<string, string>();
  private inflight: Subscription | null = null;

  readonly messages = computed(() => this.transcripts.get(this.backend().id) ?? []);
  private tick = signal(0);   // bumped to re-run `messages` after mutating a transcript

  constructor() {
    this.refreshHealth();
  }

  switchBackend(ev: Event) {
    const id = (ev.target as HTMLSelectElement).value as Backend['id'];
    this.stop();
    this.backend.set(BACKENDS.find(b => b.id === id)!);
    this.refreshHealth();
  }

  async newChat() {
    const b = this.backend();
    this.stop();
    const sid = this.sessions.get(b.id);
    if (sid) await this.chat.reset(b, sid).catch(() => undefined);
    this.sessions.delete(b.id);
    this.transcripts.set(b.id, []);
    this.bump();
  }

  send(ev: Event) {
    ev.preventDefault();
    const box = (ev.target as HTMLFormElement).querySelector('input')!;
    const text = box.value.trim();
    if (!text || this.busy()) return;
    box.value = '';

    const b = this.backend();
    const sid = this.sessions.get(b.id) ?? crypto.randomUUID();
    this.sessions.set(b.id, sid);

    const log = this.transcripts.get(b.id) ?? [];
    this.transcripts.set(b.id, log);
    log.push({ kind: 'user', text });
    const bot: Message = { kind: 'bot', text: '' };
    log.push(bot);
    this.busy.set(true);
    this.bump();

    this.inflight = this.chat.send(b, sid, text).subscribe({
      next: e => {
        if (e.delta) bot.text += e.delta;
        else if (e.tool) log.splice(log.length - 1, 0, { kind: 'sys', text: `⚙ tool: ${e.tool}` });
        else if (e.status) log.splice(log.length - 1, 0, { kind: 'sys', text: e.status });
        else if (e.error) log.push({ kind: 'err', text: e.error });
        this.bump();
      },
      complete: () => {
        if (!bot.text) log.splice(log.indexOf(bot), 1);
        this.busy.set(false);
        this.inflight = null;
        this.bump();
        setTimeout(() => box.focus());
      },
    });
  }

  stop() {
    this.inflight?.unsubscribe();     // aborts the fetch → server sees the disconnect
    this.inflight = null;
    this.busy.set(false);
  }

  private refreshHealth() {
    this.health.set(null);
    this.chat.health(this.backend()).then(h => this.health.set(h)).catch(() => this.health.set(null));
  }

  /** Transcripts are mutated in place for streaming speed; the tick signal
   *  forces `messages()` (and the template) to re-read them. */
  private bump() {
    this.tick.update(n => n + 1);
    this.tick();
  }
}
