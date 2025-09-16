# Git Cheat Sheet

## Setup & Identity
```bash
git config --global user.name "Your Name"          # set your name
git config --global user.email "you@example.com"   # set your email
git config --global init.defaultBranch main        # default branch = main
git config --global pull.rebase false              # pull merges by default (true = rebase)
git config --list                                  # show all current config
```

## Create / Clone / Inspect
```bash
git init                        # create a new repo
git clone <url-or-path>         # clone existing repo
git remote -v                   # list remotes
git remote add origin <url>     # add a new remote called origin
```

## Status, Add, Commit
```bash
git status                      # check what changed
git add <file>                  # stage file for commit
git commit -m "msg"             # commit staged changes
git commit --amend              # edit last commit (msg or content) if not pushed
```

## Branching (create/switch/delete)
```bash
git branch                      # list local branches
git branch -vv                  # list with tracking info
git switch -c feature/foo       # create + switch to new branch
git switch main                 # switch to main branch
git branch -d feature/foo       # delete branch (safe, merged)
git branch -D feature/foo       # force delete branch (not merged)
```

## Sync with Remote
```bash
git fetch --all --prune         # fetch updates + clean old refs
git pull                        # fetch + merge (or rebase if configured)
git push origin <branch>        # push branch to remote
git push -u origin <branch>     # push and set upstream tracking
```

## Merging & Rebasing (basic)
```bash
git merge feature/foo           # merge branch into current branch
git merge --no-ff feature/foo   # force merge commit (keeps branch node)
git rebase main                 # replay commits on top of main
git rebase --continue           # continue after conflict resolved
git rebase --abort              # cancel rebase
git rebase --skip               # skip a problematic commit
```
> Merge = keeps history as a graph.  
> Rebase = rewrites for linear history.  
> Don’t rebase public branches.

## Handling Merge Conflicts
```bash
git merge <branch>              # attempt merge, may create conflicts
# edit conflicted files, remove conflict markers <<<<< ===== >>>>>
git add <file>                  # mark file as resolved
git commit                      # finish the merge
```
Rebase conflicts:
```bash
git rebase <branch>             # attempt rebase
# fix files
git add <file>                  # mark resolved
git rebase --continue           # continue the rebase
```
Push conflicts:
```bash
git push                        # attempt push
git fetch origin                # Fetch remote changes
git status                      # see conflicted files
git pull origin main            # merge instead (optional: --rebase)
# edit conflicted files, remove conflict markers <<<<< ===== >>>>>
git add <file>                  # mark file as resolved
git commit                      # finish the merge (or git rebase --continue)
git push                        # push again
```

## Undo / Fix Mistakes
```bash
git restore <file>              # discard unstaged changes in file
git restore --staged <file>     # unstage a file
git reset --soft HEAD~1         # undo last commit, keep changes staged
git reset --mixed HEAD~1        # undo last commit, keep changes unstaged
git reset --hard HEAD~1         # undo commit + changes (DANGEROUS)
git revert -n <commit>          # prepare inverse of commit (e.g., HEAD), no commit
git commit -m "revert message"  # finalize the revert
git reflog                      # show history of HEAD moves
git reset --hard <reflog-id>    # recover to saved state from reflog
```

## Inspect History & Diff
```bash
git log --oneline --graph --decorate --all   # nice history graph
git log -p <path>                            # show commits + diffs for file
git show <commit>[:<path>]                   # show commit or file at commit
git diff                                     # unstaged changes
git diff --staged                            # staged changes vs HEAD
git blame <file>                             # show last author per line
```

## Stash (save work-in-progress)
```bash
git stash push -m "msg"        # save changes to stash
git stash list                 # list stashes
git stash show -p stash@{0}    # show diff of a stash
git stash apply stash@{0}      # apply stash but keep it
git stash pop                  # apply + drop stash
```

## Tags (versions/releases)
```bash
git tag v1.0.0                 # lightweight tag
git tag -a v1.0.1 -m "msg"     # annotated tag
git push origin --tags         # push tags to remote
git show v1.0.0                # show commit/tag details
```

## Cherry-pick
```bash
git cherry-pick <commit>       # apply commit onto current branch
git cherry-pick --continue     # after resolving conflict
git cherry-pick --abort        # cancel cherry-pick
```

## Clean Untracked
```bash
git clean -ndx                 # preview what will be removed
git clean -fd                  # delete untracked files/dirs
```

## Common PR Workflow (GitHub/GitLab)
```bash
git switch -c feature/foo      # create new branch
# ... commit changes ...
git push -u origin feature/foo # push + set tracking
# open PR/MR in platform UI
git switch main                # back to main
git pull --ff-only             # update main
git branch -d feature/foo      # delete local branch
git push origin --delete feature/foo   # delete remote branch
```
