# Code Reviewer MCP Server

This MCP server prepares GitHub PR review context with two review modes:

- `boyscout`: small, local improvements only (no large refactors)
- `deep`: higher-confidence review focused on correctness, side effects, and best practices

## Requirements

- Python 3.13+
- `gh` (GitHub CLI) authenticated for the target repo

## Setup for Codex CLI

Codex CLI and the VS Code extension share the same config file: `~/.codex/config.toml`.
Configure it once and both clients will use it.

1) Add the MCP server via CLI

```bash
codex mcp add code-reviewer -- /path-to-venv/bin/python /absolute/path/to/code-reviewer/main.py
```

2) Verify it’s configured

```bash
codex mcp list
```

If you prefer to edit the config directly:

```toml
[mcp_servers.code-reviewer]
command = "/path-to-venv/bin/python"
args = [
  "/absolute/path/to/code-reviewer/main.py",
]
```

Optional: set the repo root via environment if the server starts outside your workspace.

```toml
env = { CODE_REVIEWER_REPO_ROOT = "/absolute/path/to/repo" }
```

## Setup for VS Code (Codex extension)

Open the gear menu and choose `MCP settings > Open config.toml` to edit the shared config.
After updating it, run `Developer: Reload Window` so the extension reconnects to the MCP server.

## Minimal usage flow

1) If needed, call `set_repo_root("/path/to/repo")`.
2) Call `init_repo_context()` to gather repo context for this session.
3) Call `review_pr(pr_number=..., mode="boyscout"|"deep")`.
4) Optionally call `suggest_followups()`.

Notes:
- `review_pr` does **not** auto-run `init_repo_context()` anymore. Call it manually when you want richer context.
- If the diff is large, it will be truncated with a marker.
