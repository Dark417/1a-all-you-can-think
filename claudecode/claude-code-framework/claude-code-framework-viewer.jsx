import { useState } from "react";

const FILES = {
  "CLAUDE.md": {
    type: "config",
    icon: "📋",
    desc: "Root project configuration",
    content: `# Project Configuration

## Stack
<!-- CUSTOMIZE: Replace with your actual stack -->
- Language: [Your language/framework]
- Database: [Your database]
- Infrastructure: [Your cloud provider / IaC tool]
- CI/CD: [Your CI/CD pipeline]

## Workflow (ENFORCED)

All work MUST follow this sequence. Do NOT skip phases.

1. **Research** → Read relevant code deeply. Write findings to docs/research/<topic>.md. Do NOT implement.
2. **Plan** → Create docs/plans/<feature>.md with approach, code snippets, trade-offs. Do NOT implement.
3. **Implement** → Execute approved plan only. Mark tasks complete as you go.
4. **Verify** → Run tests, check types, lint. Confirm changes work end-to-end.

## Standards
- Follow existing patterns in the codebase
- All public APIs need documentation
- Write tests for new functionality
- Use meaningful commit messages

## Agent Guidelines
- Agents MUST read relevant skill files before starting work
- Prefer spawning sub-agents for independent research streams
- Use file-based handoffs between sequential tasks
- NEVER implement without an approved plan
- When uncertain, ask — do not guess

## Research Tools
- Use Context7 MCP for library/API documentation lookups
- Use Brave Search for web research before architectural decisions
- Use GitHub MCP for PR reviews and cross-repo code search`
  },
  ".claude/agents/researcher.md": {
    type: "agent",
    icon: "🔍",
    desc: "Deep research before implementation",
    model: "opus",
    color: "#06b6d4",
    content: `---
name: researcher
description: Deep research agent. Use PROACTIVELY before any architecture decisions.
tools: Read, Grep, Glob, WebFetch, WebSearch, Task
model: opus
color: cyan
maxTurns: 30
skills: deep-research, codebase-explorer
---

You are a thorough research agent. Your job is to investigate deeply and produce comprehensive written findings. You NEVER write implementation code.

## Process
1. Scope: Clarify the research question. Break it into sub-questions.
2. Broad Search: Search web, codebase, and documentation broadly.
3. Deep Dive: Go deep on the most promising leads.
4. Cross-Reference: Validate findings across multiple sources.
5. Synthesize: Write a structured report to docs/research/<topic-slug>.md.

## Rules
- NEVER implement code. Research only.
- ALWAYS write findings to a file — never just respond verbally.
- Flag uncertainties explicitly — don't paper over gaps.
- Prefer primary sources (official docs, source code) over blog posts.`
  },
  ".claude/agents/architect.md": {
    type: "agent",
    icon: "🏛️",
    desc: "System design and ADRs",
    model: "opus",
    color: "#d946ef",
    content: `---
name: architect
description: System design and architecture agent. Use for designing new features, evaluating trade-offs, creating ADRs.
tools: Read, Grep, Glob, WebFetch, WebSearch
model: opus
color: magenta
maxTurns: 25
skills: codebase-explorer, api-patterns
---

You are a senior software architect. You design systems, evaluate trade-offs, and produce architectural plans.

## Process
1. Read Research: Start by reading any relevant docs/research/*.md files.
2. Analyze Current State: Explore the codebase to understand existing patterns.
3. Design: Propose architecture with diagrams, trade-offs, and alternatives.
4. Document: Write ADR to docs/adr/NNNN-<title>.md or plan to docs/plans/<feature>.md.

## Rules
- NEVER write implementation code. Design only.
- ALWAYS check existing patterns before proposing new ones.
- Every design decision should have a "why".
- Flag security implications explicitly.`
  },
  ".claude/agents/developer.md": {
    type: "agent",
    icon: "⚡",
    desc: "Implementation from plans",
    model: "sonnet",
    color: "#22c55e",
    content: `---
name: developer
description: Implementation agent. Executes approved plans from docs/plans/.
tools: Read, Write, Edit, Grep, Glob, Bash
model: sonnet
color: green
maxTurns: 50
skills: codebase-explorer
---

You are a senior developer focused on clean implementation. You execute approved plans and write production-ready code.

## Process
1. Read Plan: Start by reading the approved plan from docs/plans/<feature>.md.
2. Understand Context: Explore relevant existing code to match patterns.
3. Implement: Write code following the plan, one task at a time.
4. Test: Write tests alongside implementation.
5. Mark Progress: Check off tasks in the plan file as you complete them.

## Rules
- NEVER implement without an approved plan in docs/plans/.
- NEVER deviate from the plan without flagging it first.
- Run tests after each logical change — don't batch.`
  },
  ".claude/agents/code-reviewer.md": {
    type: "agent",
    icon: "🔒",
    desc: "Quality, security, perf review",
    model: "sonnet",
    color: "#eab308",
    content: `---
name: code-reviewer
description: Code review agent. Reviews code changes for quality, security, performance.
tools: Read, Grep, Glob, Bash
model: sonnet
color: yellow
maxTurns: 20
skills: codebase-explorer, testing-patterns
---

## Review Categories
- 🔒 Security: Input validation, auth, secrets, dependencies
- ⚡ Performance: N+1 queries, memory, blocking ops
- 🏗️ Architecture: Separation of concerns, patterns
- 📐 Code Quality: Naming, complexity, DRY
- 🧪 Testing: Coverage, edge cases, assertions

## Rules
- Be specific — always reference file:line for issues.
- Distinguish severity: critical vs suggestion vs nit.
- Acknowledge good patterns too.`
  },
  ".claude/agents/test-engineer.md": {
    type: "agent",
    icon: "🧪",
    desc: "Test writing and coverage",
    model: "sonnet",
    color: "#3b82f6",
    content: `---
name: test-engineer
description: Test engineering agent. Writes comprehensive test suites, analyzes coverage gaps.
tools: Read, Write, Edit, Grep, Glob, Bash
model: sonnet
color: blue
maxTurns: 30
skills: testing-patterns, codebase-explorer
---

## Process
1. Analyze: Read the code under test and understand its behavior.
2. Identify Gaps: Check existing tests and find what's missing.
3. Plan Tests: Create a test plan covering happy path, edge cases, errors.
4. Implement: Write tests following project testing patterns.
5. Verify: Run the test suite and confirm everything passes.

## Rules
- Match existing test patterns and frameworks in the project.
- Tests must be deterministic — no flaky tests.
- Don't test implementation details — test behavior.`
  },
  ".claude/agents/debugger.md": {
    type: "agent",
    icon: "🐛",
    desc: "Bug diagnosis and fixes",
    model: "sonnet",
    color: "#ef4444",
    content: `---
name: debugger
description: Debugging agent. Systematic root cause analysis and targeted fixes.
tools: Read, Grep, Glob, Bash, WebSearch
model: sonnet
color: red
maxTurns: 25
---

## Process
1. Reproduce: Confirm the issue is reproducible.
2. Isolate: Narrow down where the problem occurs.
3. Trace: Follow the execution path to find the root cause.
4. Diagnose: Identify the actual root cause (not just symptoms).
5. Fix: Propose the minimal fix.
6. Verify: Confirm the fix resolves the issue without side effects.

## Rules
- NEVER guess at fixes — diagnose first, then fix.
- Propose the MINIMAL fix — don't refactor while debugging.
- Suggest a test that would catch this bug in the future.`
  },
  ".claude/agents/docs-writer.md": {
    type: "agent",
    icon: "📝",
    desc: "Documentation generation",
    model: "sonnet",
    color: "#f8fafc",
    content: `---
name: docs-writer
description: Documentation agent. Generates READMEs, API docs, architecture guides.
tools: Read, Write, Edit, Grep, Glob
model: sonnet
color: white
maxTurns: 20
skills: codebase-explorer, api-patterns
---

## Documentation Types
- README.md: Project overview, quick start, architecture
- API Documentation: Endpoints, examples, auth, errors
- Architecture Docs: System context, component diagrams, ADRs
- Onboarding Guide: Setup, walkthrough, debugging tips

## Rules
- Documentation must match actual code — verify before writing.
- Use concrete examples, not abstract descriptions.
- Use mermaid diagrams for architecture.
- Write for scanning — headers, code blocks, short paragraphs.`
  },
  ".claude/agents/api-designer.md": {
    type: "agent",
    icon: "🔗",
    desc: "REST/GraphQL API design",
    model: "sonnet",
    color: "#f97316",
    content: `---
name: api-designer
description: API design agent. Designs REST and GraphQL APIs following best practices.
tools: Read, Write, Grep, Glob, WebSearch
model: sonnet
color: orange
maxTurns: 20
skills: api-patterns, codebase-explorer
---

## REST Design Principles
- Use nouns, not verbs: /users not /getUsers
- Use plural: /users not /user
- Max 3 levels of nesting
- Version from day one: /api/v1/...

## Rules
- ALWAYS check existing API patterns in the codebase first.
- Design for the client, not the database schema.
- Include pagination for all list endpoints.
- Document error responses as thoroughly as success responses.`
  },
  ".claude/agents/devops.md": {
    type: "agent",
    icon: "🚀",
    desc: "CI/CD, Docker, deployment",
    model: "sonnet",
    color: "#a855f7",
    content: `---
name: devops
description: DevOps agent. CI/CD pipelines, Docker, deployment, monitoring.
tools: Read, Write, Edit, Grep, Glob, Bash, WebSearch
model: sonnet
color: purple
maxTurns: 30
---

## Capabilities
- CI/CD Pipelines: GitHub Actions, GitLab CI, Jenkins
- Containerization: Dockerfile best practices, Docker Compose
- Infrastructure as Code: Terraform, CloudFormation
- Monitoring: Health checks, structured logging, alerting

## Rules
- NEVER store secrets in code or configs.
- ALWAYS include rollback procedures.
- Use least-privilege for all service accounts.
- Pin dependency versions — no floating tags in production.`
  },
  ".claude/agents/refactorer.md": {
    type: "agent",
    icon: "♻️",
    desc: "Tech debt and code improvement",
    model: "sonnet",
    color: "#14b8a6",
    content: `---
name: refactorer
description: Refactoring agent. Improves code quality without changing behavior.
tools: Read, Write, Edit, Grep, Glob, Bash
model: sonnet
color: teal
maxTurns: 30
---

## Code Smells to Target (Priority Order)
- Duplication: Same logic in 3+ places → extract
- Long Functions: >50 lines → break into sub-functions
- Deep Nesting: >3 levels → early returns, extract methods
- God Classes: >300 lines → split by responsibility
- Dead Code: Unused functions → remove

## Rules
- NEVER change behavior while refactoring.
- ALWAYS ensure test coverage before starting.
- Make ONE change at a time, verify, then continue.
- Prefer existing patterns over introducing new ones.`
  },
  ".claude/skills/deep-research/SKILL.md": {
    type: "skill",
    icon: "📚",
    desc: "Multi-source research methodology",
    content: `# Deep Research Skill

## 4-Phase Methodology
1. Scope (5 min): Define questions, constraints, success criteria
2. Broad Survey (15-30 min): Official docs, GitHub repos, web search, Stack Overflow
3. Deep Dive (20-40 min): Source code, issue trackers, compatibility checks
4. Synthesis (10-15 min): Options matrix, recommendation, uncertainties

## Quality Checklist
- Multiple sources consulted
- Official docs checked for latest version
- Existing codebase patterns considered
- Security + performance implications noted
- Maintenance/support status checked`
  },
  ".claude/skills/codebase-explorer/SKILL.md": {
    type: "skill",
    icon: "🗺️",
    desc: "Systematic codebase exploration",
    content: `# Codebase Explorer Skill

## 5-Step Exploration
1. High-Level Structure: Directory layout, tech stack, docs
2. Entry Points: Main files, routes, controllers
3. Domain Models: Entities, schemas, types
4. Dependencies: External services, env vars
5. Testing Patterns: Test files, frameworks, config

## Pattern Recognition
Look for: Architecture style (layered, hexagonal, event-driven),
naming conventions, error handling approach, logging patterns,
auth/authz approach`
  },
  ".claude/skills/api-patterns/SKILL.md": {
    type: "skill",
    icon: "📡",
    desc: "REST API design reference",
    content: `# API Patterns Skill

Covers: URL design, HTTP methods, pagination (offset + cursor),
filtering/sorting, error responses, auth patterns (JWT, API key),
versioning strategies, rate limiting headers, idempotency keys.

Standard Error Codes:
- VALIDATION_ERROR (400)
- UNAUTHORIZED (401)
- FORBIDDEN (403)
- NOT_FOUND (404)
- CONFLICT (409)
- RATE_LIMITED (429)
- INTERNAL_ERROR (500)`
  },
  ".claude/skills/testing-patterns/SKILL.md": {
    type: "skill",
    icon: "✅",
    desc: "Testing best practices reference",
    content: `# Testing Patterns Skill

Covers: Arrange-Act-Assert, one concept per test, test naming,
test data builders, parameterized tests, DB cleanup patterns,
API integration tests, external service mocking.

Coverage Targets:
- New code: 80%+ line coverage
- Critical paths: 95%+
- Utilities: 90%+

Common Pitfalls: Flaky tests (shared state, time-dependent,
network calls), brittle tests (implementation details, over-mocking)`
  },
  ".claude/commands/research.md": {
    type: "command",
    icon: "🔎",
    desc: "/research <topic>",
    content: `Research the following topic: $ARGUMENTS

Instructions:
1. Read the deep-research skill
2. Follow the 4-phase research methodology
3. Search web, codebase, and documentation
4. Write structured findings to docs/research/<topic-slug>.md
5. Include options analysis with pros/cons/effort
6. Make a clear recommendation
7. Flag all uncertainties

Do NOT implement anything. Research only.`
  },
  ".claude/commands/plan.md": {
    type: "command",
    icon: "📐",
    desc: "/plan <feature>",
    content: `Create a detailed implementation plan for: $ARGUMENTS

Instructions:
1. Check for research docs in docs/research/
2. Explore relevant codebase patterns
3. Write plan to docs/plans/<feature-slug>.md with:
   - Architecture decisions (mermaid diagrams)
   - MVP phases (MVP0 → MVP1 → MVP2)
   - Specific tasks with file paths
   - Trade-offs and risks

Do NOT implement anything. Planning only.`
  },
  ".claude/commands/implement.md": {
    type: "command",
    icon: "🔨",
    desc: "/implement <plan>",
    content: `Implement the plan for: $ARGUMENTS

Instructions:
1. Find and read the plan from docs/plans/
2. If no plan exists, STOP — run /plan first
3. Execute phase by phase, one task at a time
4. Write tests alongside each task
5. Run tests after each logical change
6. Mark tasks complete: - [x] Task — ✅ done`
  },
  ".claude/commands/review.md": {
    type: "command",
    icon: "👁️",
    desc: "/review [files]",
    content: `Review the following code: $ARGUMENTS

Evaluate against:
🔒 Security | ⚡ Performance | 🏗️ Architecture
📐 Code Quality | 🧪 Testing

Write structured review to docs/reviews/<date>-<feature>.md
Categorize: Critical > Suggestion > Nit`
  },
  ".claude/commands/debug.md": {
    type: "command",
    icon: "🐞",
    desc: "/debug <issue>",
    content: `Debug the following issue: $ARGUMENTS

1. Gather evidence (errors, logs, recent changes)
2. Reproduce and isolate
3. Systematic root cause analysis
4. Write diagnosis to docs/bugs/<date>-<issue>.md
5. Propose MINIMAL fix
6. Suggest preventive test`
  },
  ".claude/commands/explore.md": {
    type: "command",
    icon: "🧭",
    desc: "/explore [area]",
    content: `Explore the codebase area: $ARGUMENTS

Follow the codebase-explorer skill's 5-step strategy.
Write context summary to docs/context/<area-slug>.md including:
- Structure and purposes
- Key patterns observed
- Entry points and flow
- Dependencies
- Gotchas`
  },
  ".claude/settings.json": {
    type: "config",
    icon: "⚙️",
    desc: "MCP servers + permissions",
    content: `{
  "permissions": {
    "allow": ["Read(*)", "Grep(*)", "Glob(*)", "WebFetch(*)", "WebSearch(*)"]
  },
  "env": {
    "CLAUDE_CODE_SUBAGENT_MODEL": "claude-sonnet-4-5-20250929"
  },
  "mcpServers": {
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@anthropic-ai/brave-search-mcp-server"],
      "env": { "BRAVE_API_KEY": "YOUR_KEY" }
    },
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp"]
    },
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp"
    },
    "sequential-thinking": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
    }
  }
}`
  }
};

const TYPE_LABELS = {
  agent: "Agent",
  skill: "Skill",
  command: "Command",
  config: "Config"
};

const TYPE_COLORS = {
  agent: { bg: "rgba(139,92,246,0.15)", border: "#8b5cf6", text: "#c4b5fd" },
  skill: { bg: "rgba(34,197,94,0.15)", border: "#22c55e", text: "#86efac" },
  command: { bg: "rgba(59,130,246,0.15)", border: "#3b82f6", text: "#93c5fd" },
  config: { bg: "rgba(251,191,36,0.15)", border: "#fbbf24", text: "#fde68a" }
};

const MODEL_BADGE = {
  opus: { bg: "#7c3aed", label: "Opus" },
  sonnet: { bg: "#2563eb", label: "Sonnet" }
};

export default function App() {
  const [selected, setSelected] = useState("CLAUDE.md");
  const [filter, setFilter] = useState("all");

  const entries = Object.entries(FILES).filter(
    ([, f]) => filter === "all" || f.type === filter
  );

  const file = FILES[selected];
  const tc = TYPE_COLORS[file?.type] || TYPE_COLORS.config;

  const counts = { all: Object.keys(FILES).length };
  Object.values(FILES).forEach(f => {
    counts[f.type] = (counts[f.type] || 0) + 1;
  });

  return (
    <div style={{
      display: "flex", flexDirection: "column", height: "100vh",
      background: "#0a0a0f", color: "#e2e8f0",
      fontFamily: "'JetBrains Mono', 'Fira Code', 'SF Mono', monospace"
    }}>
      {/* Header */}
      <div style={{
        padding: "16px 20px", borderBottom: "1px solid #1e293b",
        background: "linear-gradient(135deg, #0f0f1a 0%, #1a0a2e 100%)"
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
          <span style={{ fontSize: 22 }}>🤖</span>
          <h1 style={{
            margin: 0, fontSize: 17, fontWeight: 700,
            background: "linear-gradient(90deg, #c4b5fd, #93c5fd)",
            WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent"
          }}>Claude Code Multi-Agent Framework</h1>
          <span style={{
            marginLeft: "auto", fontSize: 11, padding: "3px 10px",
            background: "rgba(139,92,246,0.2)", borderRadius: 12,
            color: "#c4b5fd", border: "1px solid rgba(139,92,246,0.3)"
          }}>10 Agents · 4 Skills · 6 Commands</span>
        </div>
        {/* Filter tabs */}
        <div style={{ display: "flex", gap: 6 }}>
          {["all", "agent", "skill", "command", "config"].map(t => (
            <button key={t} onClick={() => setFilter(t)} style={{
              padding: "4px 12px", fontSize: 11, borderRadius: 6,
              border: filter === t ? "1px solid #8b5cf6" : "1px solid #1e293b",
              background: filter === t ? "rgba(139,92,246,0.2)" : "transparent",
              color: filter === t ? "#c4b5fd" : "#64748b",
              cursor: "pointer", fontFamily: "inherit", transition: "all 0.15s"
            }}>
              {t === "all" ? "All" : TYPE_LABELS[t]}
              <span style={{ marginLeft: 4, opacity: 0.6 }}>({counts[t] || 0})</span>
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Sidebar */}
        <div style={{
          width: 280, minWidth: 280, borderRight: "1px solid #1e293b",
          overflowY: "auto", background: "#0d0d14"
        }}>
          {entries.map(([path, f]) => {
            const active = path === selected;
            const c = TYPE_COLORS[f.type];
            return (
              <button key={path} onClick={() => setSelected(path)} style={{
                display: "flex", alignItems: "flex-start", gap: 10,
                width: "100%", padding: "10px 14px", border: "none",
                borderLeft: active ? `3px solid ${c.border}` : "3px solid transparent",
                background: active ? c.bg : "transparent",
                cursor: "pointer", textAlign: "left", fontFamily: "inherit",
                transition: "all 0.12s"
              }}>
                <span style={{ fontSize: 16, flexShrink: 0, marginTop: 1 }}>{f.icon}</span>
                <div style={{ minWidth: 0 }}>
                  <div style={{
                    fontSize: 12, fontWeight: 600,
                    color: active ? c.text : "#cbd5e1",
                    whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis"
                  }}>{path.split("/").pop()}</div>
                  <div style={{
                    fontSize: 10, color: "#64748b", marginTop: 2,
                    display: "flex", alignItems: "center", gap: 6
                  }}>
                    <span style={{
                      padding: "1px 5px", borderRadius: 3, fontSize: 9,
                      background: c.bg, color: c.text, border: `1px solid ${c.border}`,
                      textTransform: "uppercase", letterSpacing: "0.5px"
                    }}>{TYPE_LABELS[f.type]}</span>
                    {f.model && (
                      <span style={{
                        padding: "1px 5px", borderRadius: 3, fontSize: 9,
                        background: MODEL_BADGE[f.model].bg, color: "#fff"
                      }}>{MODEL_BADGE[f.model].label}</span>
                    )}
                  </div>
                  <div style={{
                    fontSize: 10, color: "#475569", marginTop: 3,
                    lineHeight: 1.3
                  }}>{f.desc}</div>
                </div>
              </button>
            );
          })}
        </div>

        {/* Content */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          {/* File header */}
          <div style={{
            padding: "12px 20px", borderBottom: "1px solid #1e293b",
            display: "flex", alignItems: "center", gap: 10,
            background: "rgba(15,15,26,0.8)"
          }}>
            <span style={{ fontSize: 18 }}>{file?.icon}</span>
            <span style={{ fontSize: 13, fontWeight: 600, color: tc.text }}>{selected}</span>
            <span style={{
              marginLeft: "auto", fontSize: 10, padding: "2px 8px",
              borderRadius: 4, background: tc.bg, color: tc.text,
              border: `1px solid ${tc.border}`
            }}>{TYPE_LABELS[file?.type]}</span>
            {file?.model && (
              <span style={{
                fontSize: 10, padding: "2px 8px", borderRadius: 4,
                background: MODEL_BADGE[file.model].bg, color: "#fff"
              }}>{MODEL_BADGE[file.model].label}</span>
            )}
          </div>

          {/* Code content */}
          <div style={{
            flex: 1, overflowY: "auto", padding: "16px 20px",
            background: "#080810"
          }}>
            <pre style={{
              margin: 0, fontSize: 12, lineHeight: 1.65, color: "#94a3b8",
              whiteSpace: "pre-wrap", wordBreak: "break-word",
              fontFamily: "'JetBrains Mono', 'Fira Code', monospace"
            }}>{file?.content}</pre>
          </div>
        </div>
      </div>

      {/* Footer - architecture diagram */}
      <div style={{
        padding: "10px 20px", borderTop: "1px solid #1e293b",
        background: "#0d0d14", fontSize: 11, color: "#475569",
        display: "flex", alignItems: "center", gap: 16
      }}>
        <span style={{ color: "#64748b" }}>Workflow:</span>
        <span style={{ color: "#06b6d4" }}>🔍 Research</span>
        <span>→</span>
        <span style={{ color: "#d946ef" }}>🏛️ Plan</span>
        <span>→</span>
        <span style={{ color: "#22c55e" }}>⚡ Implement</span>
        <span>→</span>
        <span style={{ color: "#eab308" }}>🔒 Review</span>
        <span style={{ marginLeft: "auto", color: "#334155" }}>
          Hub-and-spoke: main session orchestrates all agents
        </span>
      </div>
    </div>
  );
}
