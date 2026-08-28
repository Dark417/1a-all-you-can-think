---
description: Create an implementation plan for a feature
---

Create a detailed implementation plan for: $ARGUMENTS

## Instructions
1. First, check if there's a research doc in `docs/research/` for this topic. If so, read it.
2. Explore the relevant parts of the codebase to understand existing patterns.
3. Write a plan to `docs/plans/<feature-slug>.md` with:
   - Overview of what we're building and why
   - Architecture decisions (with mermaid diagrams if helpful)
   - Implementation phases broken into MVPs:
     - Phase 1 (MVP0): Core skeleton / minimal viable feature
     - Phase 2 (MVP1): Enhanced functionality
     - Phase 3 (MVP2): Polish, edge cases, optimization
   - Specific tasks with file paths for each phase
   - API changes (if any)
   - Data model changes (if any)
   - Trade-offs and risks
4. Each task should be a checkbox: `- [ ] Task description — file(s) affected`

Do NOT implement anything. Planning only.
