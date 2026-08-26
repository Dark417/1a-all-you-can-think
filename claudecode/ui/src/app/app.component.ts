import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { EventLinePipe } from './event-line.pipe';
import { WatchService } from './watch.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [FormsModule, DatePipe, DecimalPipe, EventLinePipe],
  template: `
    <div class="page">
      <header>
        <div>
          <span class="badge">cc-1 watchtower</span>
          <h1>Watch a scratch Claude&nbsp;Code harness think</h1>
        </div>
        <div class="stats">
          <span>{{ watch.counts().spawns }} agents</span>
          <span>{{ watch.counts().tools }} tool calls</span>
          <span>{{ watch.counts().mcp }} MCP calls</span>
          <span [class.hot]="watch.counts().compactions > 0">{{ watch.counts().compactions }} compactions</span>
        </div>
      </header>

      <div class="layout">
        <!-- ================= left rail ================= -->
        <aside>
          <section class="card">
            <h2>New run</h2>
            <form (ngSubmit)="start()">
              <textarea [(ngModel)]="task" name="task" rows="4"
                placeholder="e.g. Work the open tickets: add stdev() to stats.py and fix the median() crash."></textarea>
              <label class="field">Provider
                <select [(ngModel)]="provider" name="provider">
                  <option value="mock">mock (offline, deterministic)</option>
                  <option value="anthropic">anthropic (needs ANTHROPIC_API_KEY)</option>
                  <option value="bedrock">bedrock (needs AWS credentials)</option>
                </select>
              </label>
              <label class="field">Resume from
                <select [(ngModel)]="resumeFrom" name="resumeFrom">
                  <option [ngValue]="null">— fresh session —</option>
                  @for (s of watch.sessions(); track s.id) {
                    <option [ngValue]="s.id">{{ s.id }}</option>
                  }
                </select>
              </label>
              <button class="primary" type="submit" [disabled]="watch.starting() || !task.trim()">
                {{ watch.starting() ? 'Starting…' : 'Run task' }}
              </button>
            </form>
            @if (watch.error(); as err) { <p class="error">{{ err }}</p> }
          </section>

          <section class="card">
            <h2>Sessions</h2>
            <ul class="sessions">
              @for (s of watch.sessions(); track s.id) {
                <li [class.active]="s.id === watch.currentId()" (click)="watch.open(s.id)">
                  <span class="dot" [attr.data-status]="s.status"></span>
                  <div>
                    <strong>{{ s.id }}</strong>
                    <span class="muted small">{{ s.status }} · {{ s.created * 1000 | date: 'HH:mm:ss' }}</span>
                  </div>
                </li>
              } @empty {
                <li class="muted">No sessions yet — run a task.</li>
              }
            </ul>
          </section>

          @if (watch.todos().length) {
            <section class="card">
              <h2>Plan</h2>
              <ul class="todos">
                @for (t of watch.todos(); track t.task) {
                  <li [attr.data-status]="t.status">{{ t.task }}</li>
                }
              </ul>
            </section>
          }
        </aside>

        <!-- ================= main ================= -->
        <main>
          @if (!watch.currentId()) {
            <section class="card centered">
              <h2>Nothing selected</h2>
              <p class="muted">Run a task or pick a session. You'll see the agent tree grow,
                per-agent context windows fill, compaction fire, and both MCP servers get called.</p>
            </section>
          } @else {
            <section class="card">
              <div class="card-head">
                <h2>Agent tree {{ watch.running() ? '· live' : '' }}</h2>
                <span class="muted small">{{ watch.currentId() }}</span>
              </div>
              @for (a of watch.agentTree(); track a.id) {
                <div class="agent" [style.margin-left.px]="a.depth * 26" [attr.data-status]="a.status">
                  <div class="agent-head">
                    <span class="dot" [attr.data-status]="a.status"></span>
                    <strong>{{ a.id }}</strong>
                    <span class="chip">{{ a.role }}</span>
                    @if (a.compactions > 0) { <span class="chip hot">{{ a.compactions }}× compacted</span> }
                    <span class="muted small">{{ a.turns }} turns</span>
                  </div>
                  @if (a.context; as ctx) {
                    <div class="gauge" [title]="ctx.used_tokens + ' / ' + ctx.max_tokens + ' tokens'">
                      <div class="gauge-fill" [style.width.%]="ctx.utilization * 100"
                           [class.warn]="ctx.utilization > 0.6" [class.crit]="ctx.utilization > 0.75"></div>
                    </div>
                    <span class="muted small">context {{ ctx.used_tokens | number }} / {{ ctx.max_tokens | number }} tokens
                      ({{ ctx.utilization * 100 | number: '1.0-0' }}%)</span>
                  }
                  <p class="task muted">{{ a.task }}</p>
                  @if (a.summary) { <p class="summary">{{ a.summary }}</p> }
                </div>
              }
            </section>

            @if (watch.result(); as result) {
              <section class="card result">
                <h2>Result</h2>
                <p>{{ result }}</p>
              </section>
            }

            <section class="card">
              <div class="card-head">
                <h2>Event stream ({{ watch.events().length }})</h2>
                <label class="small muted follow"><input type="checkbox" [(ngModel)]="onlyInteresting" name="f" />
                  hide turn chatter</label>
              </div>
              <div class="feed">
                @for (e of filteredEvents(); track e.seq) {
                  <div class="event" [attr.data-type]="e.type">
                    <span class="etype">{{ e.type }}</span>
                    <span class="eagent">{{ e.agent_id ?? '—' }}</span>
                    <span class="eline">{{ e | eventLine }}</span>
                  </div>
                }
              </div>
            </section>
          }
        </main>
      </div>

      <footer class="muted small">
        Backend: <code>python3 server.py</code> on :8100 · same events as the CLI, folded into a UI.
      </footer>
    </div>
  `,
})
export class AppComponent implements OnInit {
  readonly watch = inject(WatchService);
  task = 'Work the open tickets: add stdev() to stats.py and fix the median() empty-input crash. Verify with tests and open a PR.';
  provider = 'mock';
  resumeFrom: string | null = null;
  onlyInteresting = false;

  ngOnInit(): void {
    void this.watch.refreshSessions();
  }

  start(): void {
    void this.watch.start(this.task, this.provider, this.resumeFrom);
  }

  filteredEvents() {
    const events = this.watch.events();
    if (!this.onlyInteresting) return events;
    return events.filter((e) => e.type !== 'agent.turn' && e.type !== 'tool.call');
  }
}
