from __future__ import annotations

import configparser
import json
import os
import re
import subprocess
import sys
import tomllib
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("code-reviewer")

_REPO_ROOT_OVERRIDE: Path | None = None
_LAST_REPO_CONTEXT: dict | None = None
_DOC_SOURCES: list[dict] = []

MAX_DIFF_CHARS = 120_000
MAX_FILE_BYTES = 60_000
MAX_DEPENDENCIES = 200

MODE_GUIDANCE: dict[str, str] = {
    "boyscout": (
        "Boyscout review mode (small, local improvements only).\n"
        "Focus on touched files and quick wins that improve clarity, safety, or maintainability.\n"
        "Do not request large refactors or broad redesigns.\n"
        "Call out small cleanup opportunities, naming clarity, minor edge cases, and missing small tests.\n"
        "Keep the review concise and actionable."
    ),
    "deep": (
        "Deep review mode (high confidence review of the change set).\n"
        "Focus on correctness, regressions, side effects, and best practices.\n"
        "Trace changes into referenced files if needed to confirm behavior.\n"
        "Assess whether the project remains consistent and whether breaking changes are introduced.\n"
        "Be explicit about what is good, what is risky, and what is uncertain."
    ),
}

REVIEW_TEMPLATE = (
    "Return the review with these sections:\n"
    "- Summary\n"
    "- Findings (ordered by severity)\n"
    "- Questions / Unknowns\n"
    "- Test Suggestions\n"
    "If there are no findings, state that explicitly."
)


class CommandError(RuntimeError):
    pass


def _run(cmd: list[str], cwd: Path | None = None, allow_codes: set[int] | None = None) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if allow_codes is None:
        allow_codes = {0}
    if result.returncode not in allow_codes:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        raise CommandError(
            "Command failed: "
            + " ".join(cmd)
            + (f"\nstdout: {stdout}" if stdout else "")
            + (f"\nstderr: {stderr}" if stderr else "")
        )
    return result.stdout


def _repo_root() -> Path:
    if _REPO_ROOT_OVERRIDE is not None:
        return _REPO_ROOT_OVERRIDE

    env_root = os.environ.get("CODE_REVIEWER_REPO_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    for key in ("VSCODE_WORKSPACE_FOLDER", "WORKSPACE_FOLDER", "VSCODE_CWD"):
        value = os.environ.get(key)
        if value:
            return Path(value).expanduser().resolve()

    try:
        root = _run(["git", "rev-parse", "--show-toplevel"]).strip()
        if root:
            return Path(root).resolve()
    except CommandError:
        pass
    return Path.cwd().resolve()


def _safe_repo_path(path_str: str) -> Path:
    root = _repo_root()
    path = (root / path_str).resolve()
    if root not in path.parents and path != root:
        raise ValueError(f"Path is outside repo root: {path_str}")
    return path


def _gh(args: list[str]) -> str:
    cmd = ["gh"]
    cmd.extend(args)
    return _run(cmd, cwd=_repo_root())


def _ensure_git_repo() -> None:
    root = _repo_root()
    output = _run(
        ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"], allow_codes={0, 1}
    ).strip()
    if output != "true":
        raise CommandError(
            "Not inside a git repository. Run the MCP server from a repo or set CODE_REVIEWER_REPO_ROOT."
        )


def _tool_version(label: str, cmd: list[str]) -> tuple[str, str | None]:
    try:
        output = _run(cmd).strip()
        if output:
            return label, output.splitlines()[0]
    except CommandError as exc:
        return label, f"unavailable ({exc})"
    return label, "unavailable"


def _resolve_git_root(path: Path) -> Path:
    try:
        root = _run(["git", "-C", str(path), "rev-parse", "--show-toplevel"]).strip()
    except CommandError as exc:
        raise CommandError(f"Path is not a git repository: {path}") from exc
    if not root:
        raise CommandError(f"Unable to resolve git root for: {path}")
    return Path(root).resolve()


def _fetch_url_text(url: str, max_bytes: int) -> tuple[str, bool]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http/https URLs are supported for documentation fetches.")
    request = urllib.request.Request(url, headers={"User-Agent": "code-reviewer-mcp"})
    with urllib.request.urlopen(request, timeout=20) as response:
        data = response.read(max_bytes + 1)
    truncated = len(data) > max_bytes
    if truncated:
        data = data[:max_bytes]
    text = data.decode("utf-8", errors="replace")
    return text, truncated


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + "\n\n[diff truncated]\n", True


def _read_text(path: Path, max_bytes: int) -> tuple[str, bool]:
    data = path.read_bytes()
    truncated = False
    if len(data) > max_bytes:
        data = data[:max_bytes]
        truncated = True
    return data.decode("utf-8", errors="replace"), truncated


def _read_json(path: Path, max_bytes: int) -> tuple[dict | None, bool, str | None]:
    text, truncated = _read_text(path, max_bytes)
    try:
        return json.loads(text), truncated, None
    except json.JSONDecodeError as exc:
        return None, truncated, str(exc)


def _read_toml(path: Path, max_bytes: int) -> tuple[dict | None, bool, str | None]:
    text, truncated = _read_text(path, max_bytes)
    try:
        return tomllib.loads(text), truncated, None
    except tomllib.TOMLDecodeError as exc:
        return None, truncated, str(exc)


def _detect_items(names: set[str], mapping: dict[str, str]) -> list[dict]:
    detected: list[dict] = []
    for key, label in mapping.items():
        if key in names:
            detected.append({"name": label, "package": key})
    return detected


def _normalize_dep_names(deps: dict[str, str] | None) -> set[str]:
    if not deps:
        return set()
    return {name.lower() for name in deps.keys()}


def _extract_requirements(text: str) -> list[str]:
    deps: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-"):
            continue
        deps.append(line)
        if len(deps) >= MAX_DEPENDENCIES:
            break
    return deps


def _extract_tool_versions(text: str) -> dict[str, str]:
    versions: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            versions[parts[0]] = parts[1]
    return versions


def _scan_workflows(root: Path) -> list[str]:
    workflows_dir = root / ".github" / "workflows"
    if not workflows_dir.exists():
        return []
    workflows: list[str] = []
    for path in workflows_dir.iterdir():
        if path.suffix in {".yml", ".yaml"}:
            workflows.append(path.name)
        if len(workflows) >= 25:
            break
    return workflows


def _scan_root_files(root: Path, names: list[str]) -> list[str]:
    present: list[str] = []
    for name in names:
        if (root / name).exists():
            present.append(name)
    return present


def _summarize_dependencies(dep_map: dict[str, str]) -> dict:
    items = list(dep_map.items())
    truncated = False
    if len(items) > MAX_DEPENDENCIES:
        items = items[:MAX_DEPENDENCIES]
        truncated = True
    return {"dependencies": dict(items), "truncated": truncated}


def _summarize_list(values: list[str]) -> dict:
    truncated = False
    if len(values) > MAX_DEPENDENCIES:
        values = values[:MAX_DEPENDENCIES]
        truncated = True
    return {"items": values, "truncated": truncated}


def _detect_frameworks_and_tools(dep_names: set[str]) -> tuple[list[dict], list[str]]:
    framework_map = {
        "react": "React",
        "next": "Next.js",
        "vue": "Vue",
        "nuxt": "Nuxt",
        "svelte": "Svelte",
        "@sveltejs/kit": "SvelteKit",
        "@angular/cli": "Angular",
        "@angular/core": "Angular",
        "@angular/platform-browser": "Angular",
        "qwik": "Qwik",
        "solid-js": "SolidJS",
        "lit": "Lit",
        "ember-source": "Ember",
        "gatsby": "Gatsby",
        "express": "Express",
        "fastify": "Fastify",
        "@nestjs/core": "NestJS",
        "koa": "Koa",
        "@hapi/hapi": "Hapi",
        "adonisjs": "AdonisJS",
        "@adonisjs/core": "AdonisJS",
        "@loopback/core": "LoopBack",
        "sails": "Sails",
        "@remix-run/react": "Remix",
        "astro": "Astro",
        "electron": "Electron",
        "django": "Django",
        "flask": "Flask",
        "fastapi": "FastAPI",
        "starlette": "Starlette",
        "tornado": "Tornado",
        "pyramid": "Pyramid",
        "falcon": "Falcon",
        "sanic": "Sanic",
        "quart": "Quart",
        "django-rest-framework": "Django REST Framework",
        "rails": "Ruby on Rails",
        "laravel/framework": "Laravel",
        "symfony/framework-bundle": "Symfony",
        "yiisoft/yii2": "Yii",
        "slim/slim": "Slim",
        "cakephp/cakephp": "CakePHP",
        "laminas/laminas-mvc": "Laminas",
        "codeigniter4/framework": "CodeIgniter",
        "spring-boot": "Spring Boot",
        "gin": "Gin",
        "github.com/gin-gonic/gin": "Gin",
        "echo": "Echo",
        "github.com/labstack/echo/v4": "Echo",
        "fiber": "Fiber",
        "github.com/gofiber/fiber/v2": "Fiber",
        "chi": "Chi",
        "github.com/go-chi/chi/v5": "Chi",
        "beego": "Beego",
        "github.com/beego/beego/v2": "Beego",
        "revel": "Revel",
        "github.com/revel/revel": "Revel",
        "actix-web": "Actix Web",
        "rocket": "Rocket",
    }
    tool_map = {
        "eslint": "ESLint",
        "prettier": "Prettier",
        "stylelint": "Stylelint",
        "jest": "Jest",
        "vitest": "Vitest",
        "mocha": "Mocha",
        "pytest": "pytest",
        "ruff": "Ruff",
        "black": "Black",
        "mypy": "mypy",
        "pylint": "pylint",
        "flake8": "flake8",
        "isort": "isort",
        "cypress": "Cypress",
        "playwright": "Playwright",
        "storybook": "Storybook",
    }
    frameworks = _detect_items(dep_names, framework_map)
    tools = [label for key, label in tool_map.items() if key in dep_names]
    return frameworks, tools


def _extract_pom_info(text: str) -> dict:
    info: dict[str, str] = {}
    for key in ("groupId", "artifactId", "version"):
        match = re.search(rf"<{key}>([^<]+)</{key}>", text)
        if match:
            info[key] = match.group(1)
    return info


def _extract_gradle_plugins(text: str) -> list[str]:
    plugins: list[str] = []
    for match in re.finditer(r"""id\(["']([^"']+)["']\)""", text):
        plugins.append(match.group(1))
        if len(plugins) >= 25:
            break
    return plugins


def _extract_ruby_gems(text: str) -> list[str]:
    gems: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"""gem\s+["']([^"']+)["']""", line)
        if match:
            gems.append(match.group(1))
        if len(gems) >= MAX_DEPENDENCIES:
            break
    return gems


def _extract_ruby_version(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("ruby "):
            return line.split(" ", 1)[1].strip().strip('"').strip("'")
    return None


def _extract_docker_compose_services(text: str) -> list[str]:
    services: list[str] = []
    in_services = False
    for line in text.splitlines():
        raw = line.rstrip()
        if raw.startswith("services:"):
            in_services = True
            continue
        if in_services:
            if not raw or raw.startswith(" "):
                match = re.match(r"\s{2}([a-zA-Z0-9_-]+):", raw)
                if match:
                    services.append(match.group(1))
            else:
                break
        if len(services) >= 25:
            break
    return services


def _ensure_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [value]
    return []


def _extract_rule_keys(rules: object, limit: int = MAX_DEPENDENCIES) -> list[str]:
    if isinstance(rules, dict):
        keys = list(rules.keys())
        return keys[:limit]
    return []


def _extract_eslint_config(data: dict) -> dict:
    extracted: dict[str, object] = {}
    extends = _ensure_list(data.get("extends"))
    if extends:
        extracted["extends"] = extends
    plugins = _ensure_list(data.get("plugins"))
    if plugins:
        extracted["plugins"] = plugins
    parser = data.get("parser")
    if isinstance(parser, str):
        extracted["parser"] = parser
    rules = _extract_rule_keys(data.get("rules"))
    if rules:
        extracted["rules"] = _summarize_list(rules)
    return extracted


def _extract_stylelint_config(data: dict) -> dict:
    extracted: dict[str, object] = {}
    extends = _ensure_list(data.get("extends"))
    if extends:
        extracted["extends"] = extends
    plugins = _ensure_list(data.get("plugins"))
    if plugins:
        extracted["plugins"] = plugins
    rules = _extract_rule_keys(data.get("rules"))
    if rules:
        extracted["rules"] = _summarize_list(rules)
    return extracted


def _extract_prettier_config(data: dict) -> dict:
    extracted: dict[str, object] = {}
    for key in (
        "printWidth",
        "tabWidth",
        "useTabs",
        "semi",
        "singleQuote",
        "trailingComma",
        "bracketSpacing",
        "arrowParens",
    ):
        if key in data:
            extracted[key] = data.get(key)
    return extracted


def _extract_tsconfig(data: dict) -> dict:
    extracted: dict[str, object] = {}
    extends = data.get("extends")
    if isinstance(extends, str):
        extracted["extends"] = extends
    compiler = data.get("compilerOptions")
    if isinstance(compiler, dict):
        keys = [
            "strict",
            "noImplicitAny",
            "strictNullChecks",
            "noUncheckedIndexedAccess",
            "noImplicitReturns",
            "noFallthroughCasesInSwitch",
            "target",
            "module",
            "lib",
            "jsx",
        ]
        compiler_info: dict[str, object] = {}
        for key in keys:
            if key in compiler:
                compiler_info[key] = compiler.get(key)
        if compiler_info:
            extracted["compilerOptions"] = compiler_info
    include = data.get("include")
    if isinstance(include, list):
        extracted["include"] = include[:25]
    exclude = data.get("exclude")
    if isinstance(exclude, list):
        extracted["exclude"] = exclude[:25]
    return extracted


def _extract_angular_config(data: dict) -> dict:
    extracted: dict[str, object] = {}
    default_project = data.get("defaultProject")
    if isinstance(default_project, str):
        extracted["defaultProject"] = default_project
    projects = data.get("projects")
    if isinstance(projects, dict):
        extracted["projects"] = list(projects.keys())[:10]
    schematics = data.get("schematics")
    if isinstance(schematics, dict):
        extracted["schematics"] = list(schematics.keys())[:10]
    return extracted


def _extract_editorconfig(text: str) -> dict:
    extracted: dict[str, object] = {}
    current_section = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1].strip()
            continue
        if "=" in line and current_section in ("*", "*.*", "**"):
            key, value = [part.strip() for part in line.split("=", 1)]
            if key in ("indent_style", "indent_size", "end_of_line", "charset", "trim_trailing_whitespace"):
                extracted[key] = value
    return extracted


def _read_ini(path: Path) -> tuple[configparser.ConfigParser | None, str | None]:
    parser = configparser.ConfigParser(interpolation=None)
    try:
        with path.open(encoding="utf-8") as handle:
            parser.read_file(handle)
        return parser, None
    except Exception as exc:  # noqa: BLE001 - best-effort config parsing
        return None, str(exc)


def _extract_subset(data: dict, keys: list[str]) -> dict:
    extracted: dict[str, object] = {}
    for key in keys:
        if key in data:
            extracted[key] = data.get(key)
    return extracted


@mcp.tool()
def review_pr(
    pr_number: int,
    mode: Literal["boyscout", "deep"],
) -> dict:
    """
    Prepare a PR review package for the given PR number.

    The required `mode` parameter enforces a choice between `boyscout` and `deep`.
    If the user does not specify a mode, the client should ask for it.
    """
    _ensure_git_repo()
    pr_raw = _gh(
        [
            "pr",
            "view",
            str(pr_number),
            "--json",
            "number,title,author,url,baseRefName,headRefName,additions,deletions,files",
        ]
    )
    pr_data = json.loads(pr_raw)

    diff_raw = _gh(["pr", "diff", str(pr_number), "--color=never"])
    diff_text, diff_truncated = _truncate(diff_raw, MAX_DIFF_CHARS)

    files = pr_data.get("files") or []
    touched_files: list[str] = []
    for entry in files:
        if isinstance(entry, dict):
            path = entry.get("path") or entry.get("name") or entry.get("filename")
            if isinstance(path, str):
                touched_files.append(path)
        elif isinstance(entry, str):
            touched_files.append(entry)

    context_note = None
    if _LAST_REPO_CONTEXT is None:
        context_note = "No repo context set. Run init_repo_context() first to capture framework/tooling context."

    return {
        "mode": mode,
        "instructions": MODE_GUIDANCE[mode],
        "context_guidance": (
            "Use repo_context to apply framework- and language-specific best practices. "
            "Use config signals (lint/format/test/tooling configs and scripts) as evidence, "
            "but do not rely on linters alone. "
            "If you make recommendations tied to a framework/tool, reference the official documentation name "
            "in your reasoning (no hard-coded rules; derive from context). "
            "If you use doc_sources, cite the specific doc URL/section you relied on. "
            "Explain suggestions in clear, non-expert language."
        ),
        "review_template": REVIEW_TEMPLATE,
        "repo_context": _LAST_REPO_CONTEXT,
        "repo_context_note": context_note,
        "doc_sources": _DOC_SOURCES,
        "pr": {
            "number": pr_data.get("number"),
            "title": pr_data.get("title"),
            "author": (pr_data.get("author") or {}).get("login"),
            "url": pr_data.get("url"),
            "base_ref": pr_data.get("baseRefName"),
            "head_ref": pr_data.get("headRefName"),
            "additions": pr_data.get("additions"),
            "deletions": pr_data.get("deletions"),
        },
        "files": files,
        "touched_files": touched_files,
        "diff": diff_text,
        "diff_truncated": diff_truncated,
        "repo_root": str(_repo_root()),
        "notes": "Use init_repo_context to gather repo context and read_file/read_file_at_ref for deeper checks.",
    }


@mcp.tool()
def server_info() -> dict:
    """
    Return basic environment and tool version info for debugging.
    """
    versions = dict(
        [
            ("python", sys.version.splitlines()[0]),
            _tool_version("git", ["git", "--version"]),
            _tool_version("gh", ["gh", "--version"]),
            _tool_version("rg", ["rg", "--version"]),
        ]
    )
    return {
        "cwd": str(Path.cwd()),
        "repo_root": str(_repo_root()),
        "repo_root_override": str(_REPO_ROOT_OVERRIDE) if _REPO_ROOT_OVERRIDE else None,
        "doc_sources_count": len(_DOC_SOURCES),
        "versions": versions,
        "notes": "Useful for diagnosing missing tools or mismatched environments.",
    }


@mcp.tool()
def set_repo_root(path: str) -> dict:
    """
    Set the repo root for the current MCP server session.
    Use this when the server isn't started in the target repo.
    """
    global _REPO_ROOT_OVERRIDE
    resolved = _resolve_git_root(Path(path).expanduser())
    _REPO_ROOT_OVERRIDE = resolved
    return {
        "repo_root": str(_REPO_ROOT_OVERRIDE),
        "notes": "Repo root override set for this server session.",
    }


@mcp.tool()
def init_repo_context(max_bytes: int = MAX_FILE_BYTES) -> dict:
    """
    Gather repo context before a review: frameworks, dependencies, tooling, and runtime hints.
    """
    global _LAST_REPO_CONTEXT
    root = _repo_root()
    detected_files: list[str] = []
    truncated_files: list[str] = []
    parse_errors: dict[str, str] = {}

    context: dict[str, object] = {
        "repo_root": str(root),
        "languages": [],
        "frameworks": [],
        "tools": [],
        "config": {},
        "package_managers": [],
        "runtime_versions": {},
        "ci_cd": [],
        "dependencies": {},
        "lockfiles": [],
        "build_systems": [],
        "container": {},
        "scripts": {},
        "doc_hints": [],
    }

    root_files = [
        "package.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "package-lock.json",
        "pnpm-workspace.yaml",
        "tsconfig.json",
        "tsconfig.base.json",
        "tsconfig.app.json",
        "tsconfig.spec.json",
        "angular.json",
        ".eslintrc",
        ".eslintrc.json",
        ".eslintrc.yaml",
        ".eslintrc.yml",
        ".eslintrc.js",
        ".eslintrc.cjs",
        ".eslintignore",
        ".prettierrc",
        ".prettierrc.json",
        ".prettierrc.yaml",
        ".prettierrc.yml",
        "prettier.config.js",
        "prettier.config.cjs",
        ".prettierignore",
        ".stylelintrc",
        ".stylelintrc.json",
        ".stylelintrc.yaml",
        ".stylelintrc.yml",
        ".stylelintignore",
        ".editorconfig",
        ".babelrc",
        "babel.config.json",
        ".swcrc",
        "jest.config.js",
        "vitest.config.ts",
        "vitest.config.js",
        "cypress.config.ts",
        "playwright.config.ts",
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
        "ruff.toml",
        "mypy.ini",
        ".pylintrc",
        "Pipfile",
        "Pipfile.lock",
        "poetry.lock",
        "uv.lock",
        "setup.cfg",
        "setup.py",
        "tox.ini",
        "pytest.ini",
        "go.mod",
        "go.sum",
        "Cargo.toml",
        "Cargo.lock",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        "settings.gradle.kts",
        "composer.json",
        "composer.lock",
        "Gemfile",
        "Gemfile.lock",
        ".nvmrc",
        ".node-version",
        ".python-version",
        ".ruby-version",
        ".tool-versions",
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "Makefile",
        ".gitlab-ci.yml",
        "azure-pipelines.yml",
        ".circleci/config.yml",
    ]
    detected_files.extend(_scan_root_files(root, root_files))

    languages: set[str] = set()
    frameworks: list[dict] = []
    tools: set[str] = set()
    package_managers: set[str] = set()
    lockfiles: set[str] = set()
    build_systems: set[str] = set()
    runtime_versions: dict[str, str] = {}
    dependencies: dict[str, object] = {}
    container: dict[str, object] = {}
    config_signals: dict[str, object] = {}
    scripts: dict[str, str] = {}

    if (root / "package.json").exists():
        data, truncated, error = _read_json(root / "package.json", max_bytes)
        if truncated:
            truncated_files.append("package.json")
        if error:
            parse_errors["package.json"] = error
        if isinstance(data, dict):
            languages.add("JavaScript/TypeScript")
            package_managers.add("npm")
            package_manager = data.get("packageManager")
            if isinstance(package_manager, str):
                context["package_manager"] = package_manager
            deps = data.get("dependencies") or {}
            dev_deps = data.get("devDependencies") or {}
            peer_deps = data.get("peerDependencies") or {}
            all_deps: dict[str, str] = {}
            for source in (deps, dev_deps, peer_deps):
                if isinstance(source, dict):
                    all_deps.update({k: str(v) for k, v in source.items()})
            dep_names = _normalize_dep_names(all_deps)
            found_frameworks, found_tools = _detect_frameworks_and_tools(dep_names)
            frameworks.extend(found_frameworks)
            tools.update(found_tools)
            dependencies["package.json"] = _summarize_dependencies(all_deps)
            engines = data.get("engines")
            if isinstance(engines, dict):
                for key, value in engines.items():
                    if isinstance(value, str):
                        runtime_versions[key] = value
            pkg_scripts = data.get("scripts")
            if isinstance(pkg_scripts, dict):
                script_items = list(pkg_scripts.items())
                if len(script_items) > 50:
                    script_items = script_items[:50]
                scripts.update({k: str(v) for k, v in script_items})
            eslint_config = data.get("eslintConfig")
            if isinstance(eslint_config, dict):
                config_signals["eslint"] = _extract_eslint_config(eslint_config)
            prettier_config = data.get("prettier")
            if isinstance(prettier_config, dict):
                config_signals["prettier"] = _extract_prettier_config(prettier_config)
            stylelint_config = data.get("stylelint")
            if isinstance(stylelint_config, dict):
                config_signals["stylelint"] = _extract_stylelint_config(stylelint_config)

    tsconfig_info: dict[str, object] = {}
    for ts_name in ("tsconfig.json", "tsconfig.base.json", "tsconfig.app.json", "tsconfig.spec.json"):
        path = root / ts_name
        if path.exists():
            data, truncated, error = _read_json(path, max_bytes)
            if truncated:
                truncated_files.append(ts_name)
            if error:
                parse_errors[ts_name] = error
            if isinstance(data, dict):
                extracted = _extract_tsconfig(data)
                if extracted:
                    tsconfig_info[ts_name] = extracted
    if tsconfig_info:
        config_signals["tsconfig"] = tsconfig_info

    if (root / "angular.json").exists():
        data, truncated, error = _read_json(root / "angular.json", max_bytes)
        if truncated:
            truncated_files.append("angular.json")
        if error:
            parse_errors["angular.json"] = error
        if isinstance(data, dict):
            angular_info = _extract_angular_config(data)
            if angular_info:
                config_signals["angular"] = angular_info

    for eslint_name in (".eslintrc", ".eslintrc.json"):
        path = root / eslint_name
        if path.exists():
            data, truncated, error = _read_json(path, max_bytes)
            if truncated:
                truncated_files.append(eslint_name)
            if error:
                parse_errors[eslint_name] = error
            if isinstance(data, dict):
                extracted = _extract_eslint_config(data)
                if extracted:
                    config_signals["eslint"] = extracted
            break

    for prettier_name in (".prettierrc", ".prettierrc.json"):
        path = root / prettier_name
        if path.exists():
            data, truncated, error = _read_json(path, max_bytes)
            if truncated:
                truncated_files.append(prettier_name)
            if error:
                parse_errors[prettier_name] = error
            if isinstance(data, dict):
                extracted = _extract_prettier_config(data)
                if extracted:
                    config_signals["prettier"] = extracted
            break

    for stylelint_name in (".stylelintrc", ".stylelintrc.json"):
        path = root / stylelint_name
        if path.exists():
            data, truncated, error = _read_json(path, max_bytes)
            if truncated:
                truncated_files.append(stylelint_name)
            if error:
                parse_errors[stylelint_name] = error
            if isinstance(data, dict):
                extracted = _extract_stylelint_config(data)
                if extracted:
                    config_signals["stylelint"] = extracted
            break

    for babel_name in (".babelrc", "babel.config.json"):
        path = root / babel_name
        if path.exists():
            data, truncated, error = _read_json(path, max_bytes)
            if truncated:
                truncated_files.append(babel_name)
            if error:
                parse_errors[babel_name] = error
            if isinstance(data, dict):
                config_signals["babel"] = _extract_subset(data, ["presets", "plugins"])
            break

    if (root / ".swcrc").exists():
        data, truncated, error = _read_json(root / ".swcrc", max_bytes)
        if truncated:
            truncated_files.append(".swcrc")
        if error:
            parse_errors[".swcrc"] = error
        if isinstance(data, dict):
            config_signals["swc"] = _extract_subset(
                data, ["jsc", "module", "sourceMaps", "minify", "env"]
            )

    if (root / ".editorconfig").exists():
        text, truncated = _read_text(root / ".editorconfig", max_bytes)
        if truncated:
            truncated_files.append(".editorconfig")
        editorconfig_info = _extract_editorconfig(text)
        if editorconfig_info:
            config_signals["editorconfig"] = editorconfig_info

    for test_config in (
        "jest.config.js",
        "vitest.config.ts",
        "vitest.config.js",
        "cypress.config.ts",
        "playwright.config.ts",
    ):
        if (root / test_config).exists():
            config_signals.setdefault("test_configs", [])
            if isinstance(config_signals["test_configs"], list):
                config_signals["test_configs"].append(test_config)

    if (root / "pnpm-lock.yaml").exists():
        package_managers.add("pnpm")
        lockfiles.add("pnpm-lock.yaml")
    if (root / "yarn.lock").exists():
        package_managers.add("yarn")
        lockfiles.add("yarn.lock")
    if (root / "package-lock.json").exists():
        package_managers.add("npm")
        lockfiles.add("package-lock.json")

    if (root / "pyproject.toml").exists():
        data, truncated, error = _read_toml(root / "pyproject.toml", max_bytes)
        if truncated:
            truncated_files.append("pyproject.toml")
        if error:
            parse_errors["pyproject.toml"] = error
        if isinstance(data, dict):
            languages.add("Python")
            project = data.get("project") or {}
            if isinstance(project, dict):
                deps = project.get("dependencies") or []
                if isinstance(deps, list):
                    dependencies["pyproject.toml"] = _summarize_list([str(d) for d in deps])
                optional = project.get("optional-dependencies") or {}
                if isinstance(optional, dict):
                    optional_deps: list[str] = []
                    for group in optional.values():
                        if isinstance(group, list):
                            optional_deps.extend([str(d) for d in group])
                    if optional_deps:
                        dependencies["pyproject.toml(optional)"] = _summarize_list(optional_deps)
            tool_section = data.get("tool") or {}
            if isinstance(tool_section, dict):
                poetry = tool_section.get("poetry") or {}
                if isinstance(poetry, dict):
                    package_managers.add("poetry")
                    deps = poetry.get("dependencies") or {}
                    dev = poetry.get("group") or {}
                    all_deps: dict[str, str] = {}
                    if isinstance(deps, dict):
                        all_deps.update({k: str(v) for k, v in deps.items()})
                    if isinstance(dev, dict):
                        for group in dev.values():
                            if isinstance(group, dict):
                                group_deps = group.get("dependencies") or {}
                                if isinstance(group_deps, dict):
                                    all_deps.update({k: str(v) for k, v in group_deps.items()})
                    dep_names = _normalize_dep_names(all_deps)
                    found_frameworks, found_tools = _detect_frameworks_and_tools(dep_names)
                    frameworks.extend(found_frameworks)
                    tools.update(found_tools)
                    if all_deps:
                        dependencies["pyproject.toml(poetry)"] = _summarize_dependencies(all_deps)
                ruff_cfg = tool_section.get("ruff")
                if isinstance(ruff_cfg, dict):
                    config_signals["ruff"] = _extract_subset(
                        ruff_cfg,
                        [
                            "select",
                            "ignore",
                            "extend-select",
                            "extend-ignore",
                            "line-length",
                            "target-version",
                        ],
                    )
                black_cfg = tool_section.get("black")
                if isinstance(black_cfg, dict):
                    config_signals["black"] = _extract_subset(
                        black_cfg,
                        ["line-length", "target-version", "skip-string-normalization"],
                    )
                mypy_cfg = tool_section.get("mypy")
                if isinstance(mypy_cfg, dict):
                    config_signals["mypy"] = _extract_subset(
                        mypy_cfg,
                        ["python_version", "strict", "ignore_missing_imports"],
                    )
                pytest_cfg = tool_section.get("pytest")
                if isinstance(pytest_cfg, dict):
                    ini_opts = pytest_cfg.get("ini_options")
                    if isinstance(ini_opts, dict):
                        config_signals["pytest"] = _extract_subset(
                            ini_opts, ["addopts", "testpaths", "pythonpath"]
                        )

    for req_name in ("requirements.txt", "requirements-dev.txt"):
        if (root / req_name).exists():
            text, truncated = _read_text(root / req_name, max_bytes)
            if truncated:
                truncated_files.append(req_name)
            reqs = _extract_requirements(text)
            dependencies[req_name] = _summarize_list(reqs)
            dep_names = {re.split(r"[=<>!~]", r, 1)[0].lower() for r in reqs if r}
            found_frameworks, found_tools = _detect_frameworks_and_tools(dep_names)
            frameworks.extend(found_frameworks)
            tools.update(found_tools)
            languages.add("Python")

    if (root / "Pipfile").exists():
        package_managers.add("pipenv")
        languages.add("Python")

    for ini_name in ("setup.cfg", "tox.ini", "pytest.ini", "mypy.ini"):
        path = root / ini_name
        if not path.exists():
            continue
        parser, error = _read_ini(path)
        if error:
            parse_errors[ini_name] = error
            continue
        if parser is None:
            continue
        if parser.has_section("flake8"):
            config_signals.setdefault("flake8", {})
            config_signals["flake8"] = _extract_subset(
                dict(parser.items("flake8")), ["max-line-length", "ignore", "extend-ignore"]
            )
        if parser.has_section("mypy"):
            config_signals.setdefault("mypy", {})
            config_signals["mypy"] = _extract_subset(
                dict(parser.items("mypy")), ["python_version", "strict", "ignore_missing_imports"]
            )
        if parser.has_section("tool:pytest"):
            config_signals.setdefault("pytest", {})
            config_signals["pytest"] = _extract_subset(
                dict(parser.items("tool:pytest")), ["addopts", "testpaths", "pythonpath"]
            )

    if (root / "ruff.toml").exists():
        data, truncated, error = _read_toml(root / "ruff.toml", max_bytes)
        if truncated:
            truncated_files.append("ruff.toml")
        if error:
            parse_errors["ruff.toml"] = error
        if isinstance(data, dict):
            lint_cfg = data.get("lint")
            if isinstance(lint_cfg, dict):
                config_signals["ruff"] = _extract_subset(
                    lint_cfg,
                    ["select", "ignore", "extend-select", "extend-ignore", "per-file-ignores"],
                )
            format_cfg = data.get("format")
            if isinstance(format_cfg, dict):
                config_signals.setdefault("ruff_format", {})
                config_signals["ruff_format"] = _extract_subset(
                    format_cfg, ["quote-style", "indent-style", "line-ending"]
                )

    if (root / "go.mod").exists():
        text, truncated = _read_text(root / "go.mod", max_bytes)
        if truncated:
            truncated_files.append("go.mod")
        languages.add("Go")
        build_systems.add("Go modules")
        module_match = re.search(r"^module\\s+(.+)$", text, re.MULTILINE)
        go_match = re.search(r"^go\\s+(.+)$", text, re.MULTILINE)
        go_info: dict[str, str] = {}
        if module_match:
            go_info["module"] = module_match.group(1).strip()
        if go_match:
            go_info["version"] = go_match.group(1).strip()
        if go_info:
            context["go"] = go_info

    if (root / "Cargo.toml").exists():
        data, truncated, error = _read_toml(root / "Cargo.toml", max_bytes)
        if truncated:
            truncated_files.append("Cargo.toml")
        if error:
            parse_errors["Cargo.toml"] = error
        if isinstance(data, dict):
            languages.add("Rust")
            build_systems.add("Cargo")
            package = data.get("package") or {}
            if isinstance(package, dict):
                context["cargo_package"] = {
                    "name": package.get("name"),
                    "version": package.get("version"),
                }
            deps = data.get("dependencies") or {}
            if isinstance(deps, dict):
                dependencies["Cargo.toml"] = _summarize_dependencies(
                    {k: str(v) for k, v in deps.items()}
                )
                dep_names = _normalize_dep_names(deps)
                found_frameworks, found_tools = _detect_frameworks_and_tools(dep_names)
                frameworks.extend(found_frameworks)
                tools.update(found_tools)

    if (root / "pom.xml").exists():
        text, truncated = _read_text(root / "pom.xml", max_bytes)
        if truncated:
            truncated_files.append("pom.xml")
        languages.add("Java")
        build_systems.add("Maven")
        pom_info = _extract_pom_info(text)
        if pom_info:
            context["maven"] = pom_info
        if "spring-boot" in text or "org.springframework.boot" in text:
            frameworks.append({"name": "Spring Boot", "package": "spring-boot"})

    for gradle_file in ("build.gradle", "build.gradle.kts"):
        path = root / gradle_file
        if path.exists():
            text, truncated = _read_text(path, max_bytes)
            if truncated:
                truncated_files.append(gradle_file)
            languages.add("Java/Kotlin")
            build_systems.add("Gradle")
            plugins = _extract_gradle_plugins(text)
            if plugins:
                context[f"{gradle_file}.plugins"] = plugins
            if "org.springframework.boot" in text or "spring-boot" in text:
                frameworks.append({"name": "Spring Boot", "package": "spring-boot"})

    if (root / "composer.json").exists():
        data, truncated, error = _read_json(root / "composer.json", max_bytes)
        if truncated:
            truncated_files.append("composer.json")
        if error:
            parse_errors["composer.json"] = error
        if isinstance(data, dict):
            languages.add("PHP")
            deps = data.get("require") or {}
            if isinstance(deps, dict):
                dependencies["composer.json"] = _summarize_dependencies(
                    {k: str(v) for k, v in deps.items()}
                )
                dep_names = _normalize_dep_names(deps)
                found_frameworks, found_tools = _detect_frameworks_and_tools(dep_names)
                frameworks.extend(found_frameworks)
                tools.update(found_tools)

    if (root / "Gemfile").exists():
        text, truncated = _read_text(root / "Gemfile", max_bytes)
        if truncated:
            truncated_files.append("Gemfile")
        languages.add("Ruby")
        gems = _extract_ruby_gems(text)
        if gems:
            dependencies["Gemfile"] = _summarize_list(gems)
            dep_names = {g.lower() for g in gems}
            found_frameworks, found_tools = _detect_frameworks_and_tools(dep_names)
            frameworks.extend(found_frameworks)
            tools.update(found_tools)
        ruby_version = _extract_ruby_version(text)
        if ruby_version:
            runtime_versions["ruby"] = ruby_version

    for filename, runtime_key in (
        (".nvmrc", "node"),
        (".node-version", "node"),
        (".python-version", "python"),
        (".ruby-version", "ruby"),
    ):
        path = root / filename
        if path.exists():
            text, truncated = _read_text(path, max_bytes)
            if truncated:
                truncated_files.append(filename)
            version = text.strip().splitlines()[0] if text.strip() else ""
            if version:
                runtime_versions[runtime_key] = version

    if (root / ".tool-versions").exists():
        text, truncated = _read_text(root / ".tool-versions", max_bytes)
        if truncated:
            truncated_files.append(".tool-versions")
        runtime_versions.update(_extract_tool_versions(text))

    workflows = _scan_workflows(root)
    if workflows:
        context["ci_cd"] = workflows
    elif any(name in detected_files for name in (".gitlab-ci.yml", "azure-pipelines.yml", ".circleci/config.yml")):
        context["ci_cd"] = [
            name for name in (".gitlab-ci.yml", "azure-pipelines.yml", ".circleci/config.yml") if name in detected_files
        ]

    if (root / "Dockerfile").exists():
        container["dockerfile"] = "Dockerfile"
    for compose_name in ("docker-compose.yml", "docker-compose.yaml"):
        path = root / compose_name
        if path.exists():
            text, truncated = _read_text(path, max_bytes)
            if truncated:
                truncated_files.append(compose_name)
            container["compose"] = compose_name
            services = _extract_docker_compose_services(text)
            if services:
                container["compose_services"] = services

    if container:
        context["container"] = container

    context["languages"] = sorted(languages)
    context["frameworks"] = frameworks
    context["tools"] = sorted(tools)
    context["config"] = config_signals
    context["package_managers"] = sorted(package_managers)
    context["lockfiles"] = sorted(lockfiles)
    context["build_systems"] = sorted(build_systems)
    context["runtime_versions"] = runtime_versions
    context["dependencies"] = dependencies
    context["scripts"] = scripts

    doc_hints: set[str] = set()
    doc_hints.update(context["languages"])
    doc_hints.update(context["tools"])
    for entry in frameworks:
        name = entry.get("name")
        if isinstance(name, str):
            doc_hints.add(name)
    context["doc_hints"] = sorted(doc_hints)

    payload = {
        "repo_root": str(root),
        "detected_files": detected_files,
        "truncated_files": truncated_files,
        "parse_errors": parse_errors,
        "context": context,
        "notes": (
            "Use this context (including config signals and doc_hints) to tailor the review; "
            "call read_file for deeper inspection."
        ),
    }
    _LAST_REPO_CONTEXT = payload
    return payload


@mcp.tool()
def fetch_docs(url: str, max_bytes: int = MAX_FILE_BYTES) -> dict:
    """
    Fetch documentation content from a URL and store it for review context.
    """
    text, truncated = _fetch_url_text(url, max_bytes)
    entry = {"url": url, "content": text, "truncated": truncated}
    _DOC_SOURCES.append(entry)
    return entry


@mcp.tool()
def read_file(path: str, max_bytes: int = MAX_FILE_BYTES) -> dict:
    """
    Read a file from the current repo working tree.
    Returns content and whether it was truncated.
    """
    file_path = _safe_repo_path(path)
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    data = file_path.read_bytes()
    truncated = False
    if len(data) > max_bytes:
        data = data[:max_bytes]
        truncated = True

    text = data.decode("utf-8", errors="replace")
    return {"path": str(file_path), "content": text, "truncated": truncated}


@mcp.tool()
def read_file_at_ref(path: str, ref: str = "HEAD", max_bytes: int = MAX_FILE_BYTES) -> dict:
    """
    Read a file at a specific git ref (default: HEAD).
    Useful for comparing pre- and post-change behavior.
    """
    _safe_repo_path(path)
    content = _run(["git", "show", f"{ref}:{path}"])
    truncated = False
    if len(content) > max_bytes:
        content = content[:max_bytes]
        truncated = True
    return {"path": path, "ref": ref, "content": content, "truncated": truncated}


@mcp.tool()
def search_repo(pattern: str, max_results: int = 50) -> list[dict]:
    """
    Search the repo with ripgrep. Returns file, line, and text matches.
    """
    root = _repo_root()
    cmd = [
        "rg",
        "-n",
        "--no-heading",
        "--max-count",
        str(max_results),
        pattern,
        str(root),
    ]
    output = _run(cmd, allow_codes={0, 1})
    results: list[dict] = []
    for line in output.splitlines():
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        path, line_no, text = parts
        results.append({"path": path, "line": int(line_no), "text": text})
    return results


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
