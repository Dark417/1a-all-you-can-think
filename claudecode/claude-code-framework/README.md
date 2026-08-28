# Claude Code Multi-Agent Framework

A production-ready multi-agent framework for Claude Code with 10 specialized agents, 4 skills, 6 slash commands, and MCP integrations for deep research.

## Quick Start

1. **Copy the `.claude/` directory** into your project root
2. **Copy `CLAUDE.md`** into your project root  
3. **Customize** `CLAUDE.md` with your stack, commands, and standards
4. **Add API keys** to `.claude/settings.json` (shared) or `.claude/settings.local.json` (personal)
5. **Add `.claude/settings.local.json`** to your `.gitignore`

## Architecture: Command → Agent → Skills

```
You (slash commands)
  │
  ├── /research <topic>     → Researcher Agent (Opus)
  ├── /plan <feature>       → Architect Agent (Opus)
  ├── /implement <plan>     → Developer Agent (Sonnet)
  ├── /review <files>       → Code Reviewer Agent (Sonnet)
  ├── /debug <issue>        → Debugger Agent (Sonnet)
  └── /explore <area>       → Codebase Explorer (Sonnet)
                                  │
                                  └── Skills (lazy-loaded)
                                      ├── deep-research
                                      ├── codebase-explorer
                                      ├── api-patterns
                                      └── testing-patterns
```

## Agents (10)

| Agent | Model | Purpose |
|-------|-------|---------|
| researcher | Opus | Deep research before decisions |
| architect | Opus | System design, ADRs, plans |
| developer | Sonnet | Implementation from plans |
| code-reviewer | Sonnet | Quality, security, perf review |
| test-engineer | Sonnet | Test writing and coverage |
| debugger | Sonnet | Bug diagnosis and fixes |
| docs-writer | Sonnet | Documentation generation |
| api-designer | Sonnet | REST/GraphQL API design |
| devops | Sonnet | CI/CD, Docker, deployment |
| refactorer | Sonnet | Tech debt and code improvement |

## Slash Commands (6)

| Command | Description |
|---------|-------------|
| `/research <topic>` | Deep research with written report |
| `/plan <feature>` | Implementation plan with MVPs |
| `/implement <plan>` | Execute approved plan |
| `/review [files]` | Code review with structured report |
| `/debug <issue>` | Systematic bug diagnosis |
| `/explore [area]` | Understand codebase area |

## Enforced Workflow

```
Research → Plan → Implement → Review
```

Agents enforce this sequence. The developer agent refuses to implement without a plan. The architect reads research before designing.

## MCP Servers

| Server | Purpose | Free Tier |
|--------|---------|-----------|
| Brave Search | Web research | 2,000/month |
| Context7 | Library docs | Unlimited |
| GitHub | PR review, code search | With PAT |
| Sequential Thinking | Complex reasoning | Unlimited |
| Tavily | Technical search | 1,000/month |
| Exa | Semantic search | No key needed |

## Directory Structure

```
.claude/
├── agents/          # 10 specialized agents
├── skills/          # 4 domain knowledge modules  
├── commands/        # 6 slash commands
├── settings.json    # Shared config + MCP servers
└── settings.local.json  # Personal API keys (gitignored)
```

## Customization

1. **CLAUDE.md**: Replace placeholder sections with your actual stack, commands, and standards
2. **Agents**: Modify tool restrictions, model assignments, or add new agents
3. **Skills**: Add domain-specific skills (e.g., `spring-patterns/SKILL.md`)
4. **MCP**: Add/remove MCP servers based on your needs

## Key Constraints

- **Sub-agents cannot nest**: Only the main session can spawn agents. Use file-based handoffs for sequential agent workflows.
- **Context isolation**: Sub-agents don't see the parent's conversation. Pass all needed context through the prompt.
- **Model routing**: Opus for research/architecture (expensive, deep reasoning). Sonnet for implementation (balanced). Haiku for read-only tasks (fast, cheap).

## References

- [Claude Code Docs: Skills](https://code.claude.com/docs/en/skills)
- [Claude Code Docs: Subagents](https://code.claude.com/docs/en/sub-agents)
- [Claude Code Docs: Agent Teams](https://code.claude.com/docs/en/agent-teams)
- [shanraisshan/claude-code-best-practice](https://github.com/shanraisshan/claude-code-best-practice)
- [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents)
- [giuseppe-trisciuoglio/developer-kit](https://github.com/giuseppe-trisciuoglio/developer-kit)
- [brilliantconsultingdev/claude-research-plan-implement](https://github.com/brilliantconsultingdev/claude-research-plan-implement)
- [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code)
