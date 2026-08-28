# Project Configuration

## Stack
<!-- CUSTOMIZE: Replace with your actual stack -->
- Language: [Your language/framework]
- Database: [Your database]
- Infrastructure: [Your cloud provider / IaC tool]
- CI/CD: [Your CI/CD pipeline]

## Workflow (ENFORCED)

All work MUST follow this sequence. Do NOT skip phases.

1. **Research** → Read relevant code deeply. Write findings to `docs/research/<topic>.md`. Do NOT implement.
2. **Plan** → Create `docs/plans/<feature>.md` with approach, code snippets, trade-offs. Do NOT implement.
3. **Implement** → Execute approved plan only. Mark tasks complete as you go.
4. **Verify** → Run tests, check types, lint. Confirm changes work end-to-end.

## Standards
<!-- CUSTOMIZE: Add your project's coding standards -->
- Follow existing patterns in the codebase
- All public APIs need documentation
- Write tests for new functionality
- Use meaningful commit messages

## Common Commands
<!-- CUSTOMIZE: Replace with your actual commands -->
```bash
# Development
npm run dev              # start dev server
npm run test             # run tests
npm run lint             # lint code

# Infrastructure
terraform plan           # preview infra changes
terraform apply          # apply infra changes
```

## Agent Guidelines
- Agents MUST read relevant skill files before starting work
- Prefer spawning sub-agents for independent research streams
- Use file-based handoffs between sequential tasks (write to docs/)
- NEVER implement without an approved plan
- When uncertain, ask — do not guess

## Research Tools
- Use Context7 MCP for library/API documentation lookups
- Use Brave Search for web research before architectural decisions
- Use GitHub MCP for PR reviews and cross-repo code search
- Spawn parallel sub-agents for independent research streams

## Project Docs (read when relevant)
<!-- CUSTOMIZE: Add links to your project documentation -->
- Architecture → see docs/architecture.md
- API conventions → see docs/api-conventions.md
- Deployment → see docs/deployment.md
