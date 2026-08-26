# AGENT.md

Standing instructions for any agent working in this project.

- Run tests with `python3 -m pytest -q`; a change is not done until the suite is green.
- Errors are raised as `ValueError` with actionable messages — never return None to signal failure.
- The docs MCP server holds the design notes; check it before guessing requirements.
- Keep functions pure and typed where practical.
