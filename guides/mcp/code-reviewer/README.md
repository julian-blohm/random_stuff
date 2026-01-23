# Code Reviewer MCP Server

This MCP server prepares GitHub PR review context with two review modes:

- `boyscout`: small, local improvements only (no large refactors)
- `deep`: higher-confidence review focused on correctness, side effects, and best practices

## Requirements

- Python 3.13+
- `gh` (GitHub CLI) authenticated for the target repo
- `rg` (ripgrep) for repo search (optional, used by `search_repo`)

## Run

```bash
python main.py
```

## Configure in VS Code (Codex extension)

Codex CLI and the VS Code extension share the same config file: `~/.codex/config.toml`.
You only need to set this up once.

### Quick setup (recommended)

1) Ensure dependencies are available

- Python 3.13+
- `gh` authenticated in the repo you are reviewing
- `rg` (optional, for `search_repo`)

2) Add the MCP server using the CLI

```bash
codex mcp add code-reviewer --   /path-to-venv/bin/python /absolute/path/to/code-reviewer/main.py
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

4) Reload the VS Code window so this session connects to the MCP server

Use `Developer: Reload Window` from the Command Palette.

5) Verify tools are available in this window

In the chat, try `server_info()` or check the tool list. You should see:

- `init_repo_context`
- `review_pr`
- `server_info`
- `read_file`
- `read_file_at_ref`
- `search_repo`

### Common pitfalls

- Running `python main.py` manually does **not** attach to the VS Code/Codex session.
- Relative `main.py` paths can fail if the working directory differs; use absolute paths.
- MCP tools are **per VS Code window**. If a server is running in another window, this window will not see its tools.
## Typical usage flow

1) Call `init_repo_context()` to gather repo context.
2) Call `review_pr(pr_number=..., mode="boyscout"|"deep")` to fetch the PR diff and metadata.
3) Use `read_file` / `read_file_at_ref` / `search_repo` for deeper checks as needed.

## Tools

- `review_pr(pr_number, mode)`
  - `mode` is required (`boyscout` or `deep`) so the client will prompt if missing
  - Uses `gh pr view` and `gh pr diff`
  - Requires running inside a git repo (or `CODE_REVIEWER_REPO_ROOT` set)
- `init_repo_context(max_bytes=60000)`
  - Scans common repo manifests to infer languages, frameworks, tools, package managers, build systems, and runtime versions
  - Looks at root files such as `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `pom.xml`, `build.gradle`, `composer.json`, `Gemfile`, and CI configs
  - Returns lists of detected signals plus any parse errors or truncations
- `server_info()`
  - Returns the current working directory, resolved repo root, and tool versions (python/git/gh/rg)
  - Helpful for debugging missing tools or environment mismatches
- `read_file(path, max_bytes=60000)`
  - Reads a file from the current repo working tree
  - Useful for inspecting referenced code without leaving the review flow
- `read_file_at_ref(path, ref="HEAD", max_bytes=60000)`
  - Reads a file from a specific git ref (e.g., `HEAD`, `main`, or a commit SHA)
  - Handy for before/after comparisons
- `search_repo(pattern, max_results=50)`
  - Runs ripgrep over the current repo and returns file/line matches
  - Good for finding definitions, usages, or referenced configs

## Notes

- You can override the repo root with `CODE_REVIEWER_REPO_ROOT`.
- If the diff is large, it will be truncated with a marker.
