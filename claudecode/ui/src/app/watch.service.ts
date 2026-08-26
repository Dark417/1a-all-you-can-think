import { HttpClient } from '@angular/common/http';
import { Injectable, NgZone, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { API_BASE, AgentView, HarnessEvent, SessionState, Todo } from './models';

/**
 * The watchtower's brain: opens the SSE stream for one session and folds the
 * raw harness events into UI state — the agent tree, per-agent context
 * gauges, the live plan, and the event feed. The UI never asks the harness
 * "what is your state"; it derives everything from the same transcript the
 * CLI prints and the JSONL file stores.
 */
@Injectable({ providedIn: 'root' })
export class WatchService {
  private readonly http = inject(HttpClient);
  private readonly zone = inject(NgZone);
  private source: EventSource | null = null;

  readonly sessions = signal<SessionState[]>([]);
  readonly currentId = signal<string | null>(null);
  readonly events = signal<HarnessEvent[]>([]);
  readonly agents = signal<AgentView[]>([]);
  readonly todos = signal<Todo[]>([]);
  readonly result = signal<string | null>(null);
  readonly running = signal(false);
  readonly starting = signal(false);
  readonly error = signal<string | null>(null);

  readonly agentTree = computed<AgentView[]>(() => {
    // depth-first flatten so children render under their parent
    const agents = this.agents();
    const byParent = new Map<string | null, AgentView[]>();
    for (const agent of agents) {
      const list = byParent.get(agent.parent) ?? [];
      list.push(agent);
      byParent.set(agent.parent, list);
    }
    const out: AgentView[] = [];
    const walk = (parent: string | null, depth: number) => {
      for (const agent of byParent.get(parent) ?? []) {
        agent.depth = depth;
        out.push(agent);
        walk(agent.id, depth + 1);
      }
    };
    walk(null, 0);
    return out;
  });

  readonly counts = computed(() => {
    const counts = { tools: 0, mcp: 0, compactions: 0, spawns: 0 };
    for (const event of this.events()) {
      if (event.type === 'tool.call') counts.tools++;
      else if (event.type === 'mcp.call') counts.mcp++;
      else if (event.type === 'compaction') counts.compactions++;
      else if (event.type === 'agent.spawned') counts.spawns++;
    }
    return counts;
  });

  async refreshSessions(): Promise<void> {
    this.sessions.set(await firstValueFrom(this.http.get<SessionState[]>(`${API_BASE}/api/sessions`)));
  }

  async start(task: string, provider: string, resumeFrom: string | null): Promise<void> {
    this.starting.set(true);
    this.error.set(null);
    try {
      const res = await firstValueFrom(
        this.http.post<{ id: string }>(`${API_BASE}/api/sessions`, {
          task, provider, resume_from: resumeFrom,
        }),
      );
      this.open(res.id);
    } catch (err: any) {
      this.error.set(err?.error?.detail ?? err?.message ?? String(err));
    } finally {
      this.starting.set(false);
    }
  }

  open(sessionId: string): void {
    this.close();
    this.currentId.set(sessionId);
    this.events.set([]);
    this.agents.set([]);
    this.todos.set([]);
    this.result.set(null);
    this.running.set(true);

    const source = new EventSource(`${API_BASE}/api/sessions/${sessionId}/events`);
    this.source = source;
    source.onmessage = (msg) => this.zone.run(() => this.ingest(JSON.parse(msg.data)));
    source.onerror = () => this.zone.run(() => {
      this.running.set(false);
      source.close();
    });
  }

  close(): void {
    this.source?.close();
    this.source = null;
    this.running.set(false);
  }

  // ---- event folding -----------------------------------------------------

  private ingest(event: HarnessEvent): void {
    if (event.type === 'stream.end') {
      this.running.set(false);
      this.close();
      void this.refreshSessions();
      return;
    }
    this.events.update((list) => [...list, event]);

    const agents = [...this.agents()];
    const find = (id: string | null) => agents.find((a) => a.id === id);

    switch (event.type) {
      case 'agent.spawned':
        agents.push({
          id: event.agent_id!, role: event.data['role'], parent: event.data['parent'],
          depth: 0, task: event.data['task'], status: 'running', turns: 0,
          context: null, summary: '', compactions: 0,
        });
        break;
      case 'agent.turn': {
        const agent = find(event.agent_id);
        if (agent) {
          agent.turns = event.data['turn'];
          agent.context = event.data['context'];
        }
        break;
      }
      case 'compaction': {
        const agent = find(event.agent_id);
        if (agent) agent.compactions += 1;
        break;
      }
      case 'agent.completed': {
        const agent = find(event.agent_id);
        if (agent) {
          agent.status = event.data['stop'] === 'completed' ? 'completed' : 'failed';
          agent.summary = event.data['summary'];
          agent.context = event.data['context'];
        }
        break;
      }
      case 'agent.failed': {
        const agent = find(event.agent_id);
        if (agent) { agent.status = 'failed'; agent.summary = event.data['error']; }
        break;
      }
      case 'plan.updated':
        this.todos.set(event.data['todos']);
        break;
      case 'session.completed':
        this.result.set(event.data['result']);
        break;
      case 'session.failed':
        this.result.set(`FAILED: ${event.data['error']}`);
        break;
    }
    this.agents.set(agents);
  }
}
