/** The two FastAPI backends. Both speak the same /chat, /reset, /health contract,
 *  so the UI switches between them by changing a base URL — nothing else. */
export interface Backend {
  id: 'claude' | 'codex';
  label: string;
  url: string;
}

export const BACKENDS: Backend[] = [
  { id: 'claude', label: 'Claude Agent SDK', url: 'http://localhost:8001' },
  { id: 'codex',  label: 'OpenAI Codex',     url: 'http://localhost:8002' },
];
