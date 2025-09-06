# Git Cheatsheet: Repository Creation

## 1. Create a Normal (Non-Bare) Repository
A normal repository has a working directory with actual project files.

```bash
# Create a project folder and init a repo
mkdir myproject && cd myproject
git init
```

- Contains your project files + a hidden `.git/` folder  
- Used by developers to work on code locally  

---

## 2. Create a Bare Repository
A bare repository has **no working directory**, only the contents of `.git/`.

```bash
# Commonly used as a central remote repo
git init --bare /opt/myrepo.git
```

- No working files, only Git history  
- Cannot directly edit files or commit  
- Convention: ends with `.git`  
- Used as a **shared hub** for push/pull  

---

## 3. Quick Comparison

| Repo Type   | Has Working Directory? | Use Case                         |
|-------------|-------------------------|----------------------------------|
| Non-Bare    | ✅ Yes                  | Local development work           |
| Bare        | ❌ No                   | Central repo for collaboration   |

---

## 4. Example Workflow

```bash
# Developer clones from bare repo
git clone user@server:/opt/myrepo.git

# Make changes, commit, then push back
git add .
git commit -m "Initial commit"
git push origin main
```

This way, the bare repo acts as the central hub, while developers use non-bare repos to write code.
