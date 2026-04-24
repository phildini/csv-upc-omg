# Rules for opencode

CRITICAL RULES - never violate these:

1. NEVER force-push main without explicit authorization
   - Violated: 2025-04-24 (rewrote remote main to fix author info)
   - Impact: Rewrote 4 commits, force-push required by all collaborators

2. NEVER commit files with merge conflict markers
   - Always verify `git diff --check` before committing
   - Run `ruff check` and `ruff format --check` before committing

3. Always test the full CI pipeline locally before pushing to main
   - `uv run pytest -v`
   - `uv run ruff check .`
   - `uv run ruff format --check .`
   - For web code: `DJANGO_SETTINGS_MODULE=config.settings.dev uv run python web/manage.py check`

4. Use persistent SSH agent for all git operations
   - `export SSH_AUTH_SOCK=/home/exedev/.ssh/agent.sock`
   - This agent is configured in `.bashrc` and persists across sessions
