# Git Hooks: Quick Guide

Git hooks are custom scripts that run automatically on certain Git events.  
They can enforce rules, automate workflows, or trigger integrations.  
Hooks live in the `.git/hooks/` directory of a repository.

---

## 1. Server-side Example: Tagging on Push (post-update)

**Use case:** Automatically tag a release whenever `master` is updated on the remote.

### Steps
1. On the server/bare repo (e.g., `/opt/project.git/hooks/`), create `post-update`:

```sh
#!/bin/sh
# Tag today's release if master was updated
for ref in "$@"; do
  [ "$ref" = "refs/heads/master" ] && git tag -f "release-$(date +%F)" "$ref"
done
```

2. Make it executable:
```bash
chmod +x /opt/project.git/hooks/post-update
```

3. On the client, push to master:
```bash
git push origin master
```

4. The server repo now has a tag like `release-2025-09-16`.

---

## 2. Client-side Example: Pre-commit Lint Check

**Use case:** Prevent commits that contain `.log` files.

### Steps
1. In your local repo, create `.git/hooks/pre-commit`:

```sh
#!/bin/sh
# Block commits containing .log files
if git diff --cached --name-only | grep -q '\.log$'; then
  echo "❌ Commit rejected: .log files are not allowed"
  exit 1
fi
```

2. Make it executable:
```bash
chmod +x .git/hooks/pre-commit
```

3. Now, any attempt to commit `.log` files will be blocked locally.
