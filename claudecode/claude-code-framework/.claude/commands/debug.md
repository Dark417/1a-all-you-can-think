---
description: Diagnose and fix a bug or error
---

Debug the following issue: $ARGUMENTS

## Instructions
1. Gather evidence:
   - Get the exact error message / stack trace
   - Check recent git changes (`git log --oneline -10`)
   - Check relevant logs
2. Reproduce the issue if possible
3. Systematically isolate the root cause:
   - Use `grep` to find relevant code paths
   - Use `git blame` to understand history
   - Check configuration and environment
4. Write diagnosis to `docs/bugs/<date>-<issue>.md`
5. Propose the MINIMAL fix that addresses the root cause
6. Suggest a test that would catch this bug in the future
7. Verify the fix doesn't break existing tests

Be systematic. Diagnose first, fix second. Never guess at fixes.
