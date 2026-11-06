# angular — Angular 19, standalone components + signals

```bash
npm install
npm run dev     # http://localhost:4200
```

Needs the backend running on `http://localhost:8080` (set in `src/environment.ts`).

| File | Role |
| --- | --- |
| `src/app/credentials.interceptor.ts` | Adds `withCredentials` and the CSRF header to API calls. |
| `src/app/auth.service.ts` | Signal-based auth state; `signIn()` / `signOut()` navigate the browser. |
| `src/app/notes.service.ts` | Typed `HttpClient` calls against the demo API. |
| `src/app/app.component.ts` | Shell, using `@if` / `@switch` control flow. |

**Why a custom interceptor?** Angular ships `withXsrfConfiguration`, but its interceptor
deliberately skips absolute URLs — it will not attach the header to a cross-origin API like
this one on `:8080`. If you deploy the UI and API on the same origin you can drop
`credentials.interceptor.ts` and use Angular's built-in support instead.
