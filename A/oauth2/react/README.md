# react — React 18 + Vite + TypeScript

```bash
npm install
npm run dev     # http://localhost:5173
```

Needs the backend running on `http://localhost:8080` (override with `VITE_API_BASE_URL`).

| File | Role |
| --- | --- |
| `src/api/client.ts` | `fetch` wrapper: `credentials: 'include'` + the CSRF header. The only file that knows about auth plumbing. |
| `src/auth/AuthProvider.tsx` | Context holding `status / user / session`. Asks the backend "who am I?" once on mount. |
| `src/components/SessionPanel.tsx` | Shows what the backend knows, with a live token countdown. |
| `src/components/NotesPanel.tsx` | The demo API calls. |

There is no token handling here, because the browser never receives a token. Sign-in is a
full page navigation (`location.href = …/auth/login`), never a `fetch` — the browser has to
leave this origin so AWS can render its own login page.
