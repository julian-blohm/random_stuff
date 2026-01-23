# Code Reviewer MCP Server

This MCP server prepares GitHub PR review context with two review modes:

- `boyscout`: small, local improvements only (no large refactors)
- `deep`: higher-confidence review focused on correctness, side effects, and best practices

## Requirements

- Python 3.13+
- `gh` (GitHub CLI) authenticated for the target repo

## Configure in VS Code (Codex extension)

Codex CLI and the VS Code extension share the same config file: `~/.codex/config.toml`.
You only need to set this up once.

### Quick setup (recommended)

1) Ensure dependencies are available

- Python 3.13+
- `gh` authenticated in the repo you are reviewing

2) Add the MCP server using the CLI

```bash
codex mcp add code-reviewer -- /path-to-venv/bin/python /absolute/path/to/code-reviewer/main.py
```

Verify it’s configured:

```bash
codex mcp list
```

3) Or edit `~/.codex/config.toml` manually

```toml
[mcp_servers.code-reviewer]
command = "/path-to-venv/bin/python"
args = [
  "/absolute/path/to/code-reviewer/main.py",
]
```

Tip: In the Codex VS Code extension, open the gear menu and choose
`MCP settings > Open config.toml` to edit the shared config file.

Optional: If the extension supports workspace variables, you can set the repo
root dynamically with:

```toml
env = { CODE_REVIEWER_REPO_ROOT = "${workspaceFolder}" }
```

4) Reload the VS Code window so this session connects to the MCP server

Use `Developer: Reload Window` from the Command Palette.

5) Verify tools are available in this window

In the chat, check the tool list. You should see:

- `init_repo_context`
- `review_pr`
- `set_repo_root`
- `suggest_followups`

### Common pitfalls

- Running `python main.py` manually does **not** attach to the VS Code/Codex session.
- Relative `main.py` paths can fail if the working directory differs; use absolute paths.
- MCP tools are **per VS Code window**. If a server is running in another window, this window will not see its tools.

## Typical usage flow

1) (If needed) call `set_repo_root("/path/to/repo")` to point the server at your workspace.
2) Call `init_repo_context()` to gather repo context (stored for this server session).
3) Call `review_pr(pr_number=..., mode="boyscout"|"deep")` to fetch the PR diff and metadata.
4) Optionally call `suggest_followups()` to pick next steps.

Notes:
- `review_pr` will auto-run `init_repo_context()` if context is missing.
- In deep mode, it also auto-collects extra file context (up to 20 files).

## Tools

- `set_repo_root(path)`
  - Overrides the repo root for this server session (must be a git repo)
  - Useful when the server starts outside your workspace
- `init_repo_context(max_bytes=60000)`
  - Scans common repo manifests to infer languages, frameworks, tools, package managers, build systems, and runtime versions
  - Reads config files (linters, formatters, compiler settings) to build context signals
  - Returns lists of detected signals plus any parse errors or truncations
  - Covers popular frontend and backend frameworks (e.g., React, Angular, Vue, Next.js, Gin, Echo, Fiber, Django, FastAPI, Laravel, Symfony)
- `review_pr(pr_number, mode)`
  - `mode` is required (`boyscout` or `deep`) so the client will prompt if missing
  - Uses `gh pr view` and `gh pr diff`
  - Requires running inside a git repo (or `CODE_REVIEWER_REPO_ROOT` set)
  - Uses the most recent `init_repo_context()` output (auto-runs it if missing)
  - Review guidance uses config signals, but is not limited to linter rules
  - In deep mode, it also includes extra file context from touched files and key configs (up to 20 files)
  - Returns `context_sources` so you can see which files/configs informed the review
- `suggest_followups()`
  - Returns options for applying fixes or continuing the review after findings are delivered

## Notes

- You can override the repo root with `CODE_REVIEWER_REPO_ROOT` or `set_repo_root(...)`.
- If the diff is large, it will be truncated with a marker.
