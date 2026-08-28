---
description: Review code changes for quality, security, and patterns
---

Review the following code: $ARGUMENTS

## Instructions
1. If a file path or glob is provided, review those specific files.
2. If "latest" or no argument, review the most recent git changes (`git diff HEAD~1`).
3. Evaluate against all review categories:
   - 🔒 Security (injection, auth, secrets, dependencies)
   - ⚡ Performance (N+1 queries, memory, blocking ops)
   - 🏗️ Architecture (separation of concerns, patterns)
   - 📐 Code Quality (naming, complexity, DRY)
   - 🧪 Testing (coverage, edge cases, assertions)
4. Write a structured review to `docs/reviews/<date>-<feature>.md`
5. Categorize issues by severity: Critical > Suggestion > Nit
6. Include specific file:line references for every issue
7. Also note what's done well — reviews aren't just about problems

Be thorough but fair. Explain "why" for every finding.
