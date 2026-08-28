# Codebase Explorer Skill

Systematically explore and understand a codebase before making changes. This skill ensures agents have deep context before modifying code.

## When to Use
- First time working in a part of the codebase
- Before implementing any feature
- When debugging unfamiliar code
- When reviewing code you haven't written

## Exploration Strategy

### Step 1: High-Level Structure
```bash
# View top-level directory layout
find . -maxdepth 2 -type d -not -path '*/node_modules/*' -not -path '*/.git/*' | head -50

# Identify the tech stack
cat package.json 2>/dev/null || cat pom.xml 2>/dev/null || cat build.gradle 2>/dev/null || cat requirements.txt 2>/dev/null

# Check for documentation
ls -la docs/ README.md CLAUDE.md CONTRIBUTING.md 2>/dev/null
```

### Step 2: Entry Points
Find the main entry points and understand the application flow:
```bash
# Find main/entry files
grep -rl "main\|createApp\|express()\|SpringApplication" --include="*.{ts,js,java,py}" -l | head -10

# Find route/controller definitions
grep -rn "router\.\|@GetMapping\|@app.route\|@Controller" --include="*.{ts,js,java,py}" | head -20

# Find configuration files
find . -name "*.config.*" -o -name "*.yml" -o -name "*.yaml" -o -name "*.properties" | grep -v node_modules | head -15
```

### Step 3: Domain Models
Understand the data structures:
```bash
# Find model/entity definitions
find . -path "*/model*" -o -path "*/entity*" -o -path "*/schema*" -o -path "*/types*" | grep -v node_modules | head -20

# Find database migrations
find . -path "*/migration*" -o -path "*/migrate*" | grep -v node_modules | head -10
```

### Step 4: Dependencies & Integrations
```bash
# External service integrations
grep -rn "http\|fetch\|axios\|RestTemplate\|WebClient\|requests\." --include="*.{ts,js,java,py}" -l | head -10

# Environment variables used
grep -rn "process.env\|System.getenv\|os.environ\|@Value" --include="*.{ts,js,java,py}" | head -20
```

### Step 5: Testing Patterns
```bash
# Find test files and understand testing patterns
find . -name "*.test.*" -o -name "*.spec.*" -o -name "*Test.java" | grep -v node_modules | head -15

# Check test configuration
ls -la jest.config* vitest.config* pytest.ini .mocharc* 2>/dev/null
```

## Pattern Recognition

When exploring, look for and document:

### Architecture Patterns
- Layered (controller → service → repository)?
- Hexagonal (ports and adapters)?
- Event-driven (pub/sub, message queues)?
- Microservices or monolith?

### Coding Conventions
- Naming conventions (camelCase, snake_case, PascalCase)
- File organization patterns
- Error handling approach
- Logging patterns
- Authentication/authorization approach

### Documentation Patterns
- Inline comments style
- API documentation approach
- README structure
- ADR (Architecture Decision Records) presence

## Output
After exploring, write a brief summary to help future agents:
```markdown
# Codebase Context: <area explored>

## Structure
<Key directories and their purposes>

## Key Patterns
<Architectural and coding patterns observed>

## Entry Points
<Main files and request flow>

## Gotchas
<Non-obvious things that could trip up an agent>
```
