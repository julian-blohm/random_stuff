from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("code-reviewer")

_REPO_ROOT_OVERRIDE: Path | None = None
_LAST_REPO_CONTEXT: dict | None = None

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
        "@angular/core": "Angular",
        "express": "Express",
        "fastify": "Fastify",
        "@nestjs/core": "NestJS",
        "koa": "Koa",
        "@remix-run/react": "Remix",
        "astro": "Astro",
        "gatsby": "Gatsby",
        "solid-js": "SolidJS",
        "electron": "Electron",
        "django": "Django",
        "flask": "Flask",
        "fastapi": "FastAPI",
        "starlette": "Starlette",
        "tornado": "Tornado",
        "pyramid": "Pyramid",
        "rails": "Ruby on Rails",
        "laravel/framework": "Laravel",
        "spring-boot": "Spring Boot",
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
            "If you make recommendations tied to a framework/tool, reference the official documentation name "
            "in your reasoning (no hard-coded rules; derive from context)."
        ),
        "review_template": REVIEW_TEMPLATE,
        "repo_context": _LAST_REPO_CONTEXT,
        "repo_context_note": context_note,
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
        "package_managers": [],
        "runtime_versions": {},
        "ci_cd": [],
        "dependencies": {},
        "lockfiles": [],
        "build_systems": [],
        "container": {},
    }

    root_files = [
        "package.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "package-lock.json",
        "pnpm-workspace.yaml",
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
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
    context["package_managers"] = sorted(package_managers)
    context["lockfiles"] = sorted(lockfiles)
    context["build_systems"] = sorted(build_systems)
    context["runtime_versions"] = runtime_versions
    context["dependencies"] = dependencies

    payload = {
        "repo_root": str(root),
        "detected_files": detected_files,
        "truncated_files": truncated_files,
        "parse_errors": parse_errors,
        "context": context,
        "notes": "Use this context to tailor the review; call read_file for deeper inspection.",
    }
    _LAST_REPO_CONTEXT = payload
    return payload


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
