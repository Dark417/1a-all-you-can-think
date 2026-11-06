import { HttpInterceptorFn } from '@angular/common/http';
import { environment } from '../environment';

/**
 * One interceptor, two jobs, and no token in sight:
 *
 *   1. withCredentials - so the httpOnly session cookie is sent cross-origin
 *      (the UI is on :4200, the API on :8080).
 *   2. the double-submit CSRF header on writes.
 *
 * Angular ships its own XSRF interceptor, but it deliberately skips absolute
 * URLs - it will not attach the header to a cross-origin API like ours. Hence
 * this one.
 */
export const credentialsInterceptor: HttpInterceptorFn = (req, next) => {
  if (!req.url.startsWith(environment.apiBaseUrl)) return next(req);

  const isWrite = !['GET', 'HEAD', 'OPTIONS'].includes(req.method.toUpperCase());
  const csrf = readCookie('csrf_token');

  return next(
    req.clone({
      withCredentials: true,
      setHeaders: isWrite && csrf ? { 'x-csrf-token': csrf } : {},
    }),
  );
};

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}
