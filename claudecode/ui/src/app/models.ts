export const API_BASE = 'http://localhost:8100';

export interface HarnessEvent {
  seq: number;
  ts: number;
  type: string;
  agent_id: string | null;
  data: Record<string, any>;
}

export interface ContextSnapshot {
  max_tokens: number;
  used_tokens: number;
  utilization: number;
  turns: number;
  compactions: number;
}

/** Live per-agent view, reconstructed purely from the event stream. */
export interface AgentView {
  id: string;
  role: string;
  parent: string | null;
  depth: number;
  task: string;
  status: 'running' | 'completed' | 'failed';
  turns: number;
  context: ContextSnapshot | null;
  summary: string;
  compactions: number;
}

export interface Todo {
  task: string;
  status: 'pending' | 'in_progress' | 'completed';
}

export interface SessionState {
  id: string;
  status: string;
  task: string | null;
  provider: string | null;
  created: number;
  finished: number | null;
  result: string | null;
  agents: any[];
}
