---
description: Execute an approved implementation plan
---

Implement the plan for: $ARGUMENTS

## Instructions
1. Find and read the plan from `docs/plans/`. If no plan exists, STOP and tell the user to run `/plan` first.
2. Read the codebase-explorer skill and understand the relevant code.
3. Execute the plan phase by phase:
   - Start with Phase 1 (MVP0) unless the user specifies otherwise
   - Implement one task at a time
   - Write tests alongside each task
   - Run tests after each logical change
   - Mark each task complete: `- [x] Task — ✅ done`
4. After completing a phase, summarize what was done and what's next.
5. If you encounter anything unexpected, STOP and document it before proceeding.

Follow existing codebase patterns. Write clean, tested, production-ready code.
