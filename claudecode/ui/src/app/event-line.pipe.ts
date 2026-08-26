import { Pipe, PipeTransform } from '@angular/core';
import { HarnessEvent } from './models';

/** One-line human rendering of a harness event, mirroring the CLI's. */
@Pipe({ name: 'eventLine', standalone: true })
export class EventLinePipe implements PipeTransform {
  transform(event: HarnessEvent): string {
    const d = event.data;
    switch (event.type) {
      case 'session.started': return `task started (provider: ${d['provider']})`;
      case 'mcp.connected': return `MCP server '${d['server']}' up — tools: ${(d['tools'] ?? []).join(', ')}`;
      case 'agent.spawned': return `${d['role']} spawned${d['parent'] ? ` by ${d['parent']}` : ''}`;
      case 'agent.turn': {
        const calls = (d['tool_calls'] ?? []).join(', ');
        return `turn ${d['turn']} · ctx ${Math.round((d['context']?.['utilization'] ?? 0) * 100)}% → ${calls || 'final answer'}`;
      }
      case 'tool.call':
        return `${d['tool']} ${d['ok'] ? '✓' : '✗'} ${d['duration_ms']}ms — ${String(d['output_preview'] ?? '').slice(0, 110)}`;
      case 'mcp.call': return `MCP ${d['server']}.${d['tool']} → ${String(d['result_preview'] ?? '').slice(0, 90)}`;
      case 'compaction':
        return `compacted ${d['turns_compacted']} turns: ${d['tokens_before']}t → ${d['tokens_after']}t`;
      case 'plan.updated': {
        const todos = d['todos'] ?? [];
        const done = todos.filter((t: any) => t.status === 'completed').length;
        return `plan updated: ${done}/${todos.length} complete`;
      }
      case 'agent.completed': return `finished after ${d['turns']} turns (${d['stop']})`;
      case 'agent.failed': return `failed: ${d['error']}`;
      case 'session.completed': return 'session completed';
      case 'session.failed': return `session failed: ${d['error']}`;
      default: return JSON.stringify(d).slice(0, 120);
    }
  }
}
