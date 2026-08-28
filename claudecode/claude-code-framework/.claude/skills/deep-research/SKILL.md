# Deep Research Skill

Conduct thorough multi-source research on any technical topic. This skill guides structured investigation that produces actionable findings.

## When to Use
- Before making architectural decisions
- When evaluating new libraries, frameworks, or tools
- When investigating unfamiliar domains or patterns
- Before building features that interact with external systems

## Research Methodology

### Phase 1: Scope (5 minutes)
Define exactly what you're researching:
- What question(s) need answering?
- What would a good answer look like?
- What constraints exist (language, framework, budget, timeline)?

### Phase 2: Broad Survey (15-30 minutes)
Search widely to map the landscape:
- Official documentation for relevant technologies
- GitHub: search for reference implementations (sort by stars)
- Web search: "<topic> best practices 2025" / "<topic> vs alternatives"
- Stack Overflow: common pitfalls and solutions
- Check if the project already has similar patterns

### Phase 3: Deep Dive (20-40 minutes)
Go deep on the most promising approaches:
- Read source code of reference implementations
- Check issue trackers for known problems
- Verify claims with multiple sources
- Test compatibility with project's existing stack
- Check maintenance status (last commit, open issues, bus factor)

### Phase 4: Synthesis (10-15 minutes)
Produce structured findings:
- Summarize options with pros/cons/effort matrix
- Make a clear recommendation with justification
- Flag uncertainties and unknowns explicitly
- List sources for verification

## Research Output Template

Write findings to: `docs/research/<topic-slug>.md`

```markdown
# Research: <Topic>
Date: YYYY-MM-DD
Status: Complete | In Progress | Needs Review

## Question
<The specific question(s) being investigated>

## TL;DR
<2-3 sentence summary — the answer in brief>

## Findings

### Option A: <Name>
- **What**: <description>
- **Pros**: <list>
- **Cons**: <list>
- **Effort**: S/M/L
- **Reference**: <link to code/docs>

### Option B: <Name>
...

## Recommendation
<Recommended approach with clear reasoning>

## Uncertainties
<What couldn't be determined — needs human judgment or testing>

## Sources
- <URL> — <what it contributed>
- <URL> — <what it contributed>
```

## Quality Checklist
- [ ] Multiple sources consulted (not just one blog post)
- [ ] Official docs checked for latest version info
- [ ] Existing codebase patterns considered
- [ ] Compatibility with project stack verified
- [ ] Security implications noted
- [ ] Performance implications noted
- [ ] Maintenance/support status checked
