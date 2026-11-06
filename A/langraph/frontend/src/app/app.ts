import { Component, inject, signal } from '@angular/core';
import { Subscription } from 'rxjs';
import { ChatService, Health, API } from './chat.service';

interface Message {
  kind: 'user' | 'bot' | 'sys' | 'err';
  text: string;
}

@Component({
  selector: 'app-root',
  template: `
    <header>
      <h1>LangGraph chat</h1>

      <!-- model picker: every id BazaarLink serves; changing it starts a fresh thread -->
      <select [value]="model()" (change)="switchModel($event)" [disabled]="busy()">
        @for (m of models(); track m) {
          <option [value]="m">{{ m }}</option>
        }
      </select>

      <span class="meta">
        @if (health(); as h) { {{ h.framework }} · {{ h.provider }} }
        @else { {{ api }} — unreachable }
      </span>

      <button class="ghost" (click)="newChat()">New chat</button>
    </header>

    <div class="log">
      @for (m of messages(); track $index) {
        <div class="msg {{ m.kind }}">{{ m.text }}</div>
      }
      @if (messages().length === 0) {
        <div class="msg sys">talking to <b>{{ model() }}</b> via LangGraph — try "what's 17**5 / 3?" or "what time is it?"</div>
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
    select { padding:6px 8px; border-radius:8px; background:#0f1115; color:var(--fg); border:1px solid #333845; max-width:260px; }
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

  readonly api = API;
  readonly health = signal<Health | null>(null);
  readonly models = signal<string[]>([]);
  readonly model = signal('');
  readonly messages = signal<Message[]>([]);
  readonly busy = signal(false);

  private sessionId: string | null = null;
  private inflight: Subscription | null = null;

  constructor() {
    this.chat.health().then(h => this.health.set(h)).catch(() => this.health.set(null));
    this.chat.models()
      .then(m => { this.models.set(m.models); this.model.set(m.default); })
      .catch(() => undefined);
  }

  switchModel(ev: Event) {
    this.model.set((ev.target as HTMLSelectElement).value);
    this.newChat();   // memory is per (model, thread) server-side, so start clean
  }

  async newChat() {
    this.stop();
    if (this.sessionId) await this.chat.reset(this.sessionId).catch(() => undefined);
    this.sessionId = null;
    this.messages.set([]);
  }

  send(ev: Event) {
    ev.preventDefault();
    const box = (ev.target as HTMLFormElement).querySelector('input')!;
    const text = box.value.trim();
    if (!text || this.busy()) return;
    box.value = '';

    const sid = this.sessionId ??= crypto.randomUUID();
    const log = [...this.messages(), { kind: 'user', text } as Message];
    const bot: Message = { kind: 'bot', text: '' };
    log.push(bot);
    this.messages.set(log);
    this.busy.set(true);

    const render = () => this.messages.set([...log]);   // new array → signal notifies

    this.inflight = this.chat.send(sid, text, this.model()).subscribe({
      next: e => {
        if (e.delta) bot.text += e.delta;
        else if (e.tool) log.splice(log.length - 1, 0, { kind: 'sys', text: `⚙ ${e.tool}` });
        else if (e.status) log.splice(log.length - 1, 0, { kind: 'sys', text: e.status });
        else if (e.error) log.push({ kind: 'err', text: e.error });
        render();
      },
      complete: () => {
        if (!bot.text) log.splice(log.indexOf(bot), 1);
        render();
        this.busy.set(false);
        this.inflight = null;
        setTimeout(() => box.focus());
      },
    });
  }

  stop() {
    this.inflight?.unsubscribe();     // aborts the fetch → server sees the disconnect
    this.inflight = null;
    this.busy.set(false);
  }
}
