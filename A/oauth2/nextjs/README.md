# nextjs — Next.js 15, App Router

```bash
npm install
npm run dev     # http://localhost:3000
```

Needs the backend running on `http://localhost:8080` (override with
`NEXT_PUBLIC_API_BASE_URL`).

| File | Role |
| --- | --- |
| `lib/api.ts` | `fetch` wrapper: `credentials: 'include'` + the CSRF header. |
| `components/AuthProvider.tsx` | Client-side auth context. Reads `window.location` in an effect, not during render — this component is prerendered on the server. |
| `components/SessionPanel.tsx` | Backend session state with a live countdown. |
| `components/NotesPanel.tsx` | The demo API calls. |

**Why not put the BFF in this app?** Next has a server, so `/auth/*` could live in
`app/api/` route handlers and this would be one service instead of two. It doesn't here
because the point of the repo is three different frontends sharing one backend. In a
Next-only product, hosting the BFF inside Next is a good choice and the flow is identical —
`app/api/auth/login/route.ts` doing what `backend/src/routes/auth.routes.js` does today.
