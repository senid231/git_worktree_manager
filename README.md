# Git Worktree Manager (GWT)

[![CI](https://github.com/senid231/git_worktree_manager/actions/workflows/ci.yml/badge.svg)](https://github.com/senid231/git_worktree_manager/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Python CLI that automates git worktree setup — syncing files, running hooks, and providing convenient navigation.

## Why

`git worktree` handles the git side of things, but real projects need more: copy `.env` files, symlink `node_modules`, run `bundle install`, etc. GWT automates all of that with a simple YAML config.

- **Sync files** into each worktree on creation (copy or symlink, with glob support)
- **Run hooks** on create and remove (`on_create`, `on_remove`)
- **Named commands** via `gwt run <name>` with worktree env vars pre-set
- **Shell navigation** with `gcd <branch>` alias and tab completion
- **Two config files**: `.gwt/config.yml` (shared, committed) and `.gwt/config.local.yml` (personal overrides, gitignored)

## Installation

### Via pipx (recommended)

```bash
pipx install git+https://github.com/senid231/git_worktree_manager.git
```

To update:

```bash
pipx reinstall gwt
```

To uninstall:

```bash
pipx uninstall gwt
```

### From a local clone (to test as a tool)

```bash
git clone https://github.com/senid231/git_worktree_manager.git
pipx install ./git_worktree_manager
```

### Local development install

```bash
git clone https://github.com/senid231/git_worktree_manager.git
cd git_worktree_manager
pip install -e ".[dev]"
```

### Shell integration

Add to your `~/.bashrc` or `~/.zshrc`:

```bash
eval "$(gwt shell-init bash)"   # or zsh
```

This defines the `gwt_cd` function (aliased as `gcd`) for directory switching, and enables tab completion.

## Quick Start

```bash
# In your project repo
gwt init              # pick which config files to create (--yes accepts the defaults)
# edit .gwt/config.yml to configure copy/link/hooks
git branch my-feature
gwt add my-feature    # creates worktree, syncs files, runs on_create hooks
gcd my-feature        # cd into the worktree
gwt list              # show all worktrees
gwt remove my-feature # run on_remove hooks, then remove
```

## Configuration

GWT reads two files from the `.gwt/` directory in the repo root:

| File | Purpose |
|------|---------|
| `.gwt/config.yml` | Shared config — commit this |
| `.gwt/config.local.yml` | Personal overrides — gitignored |

Lists are **concatenated** (local appended to shared). Scalars are **overridden** by local. `commands` map is **deep-merged**.

### Full config reference

```yaml
# Root directory for worktrees, relative to repo root (default: .worktrees)
worktrees_root: .worktrees

# Files/dirs to copy into each new worktree (supports globs)
copy:
  - .env
  - config/*.yml

# Patterns to exclude from copy
skip_copy:
  - config/production.yml

# Files/dirs to symlink into each new worktree (supports globs)
link:
  - node_modules
  - vendor/bundle

# Patterns to exclude from link
skip_link:
  - vendor/bundle/cache

# Shell commands run after creating a worktree
on_create:
  - bundle install
  - echo "Worktree ready at $GWT_WT_PATH"
  - createdb "myapp_${GWT_WT_SLUG}"   # per-branch database

# Shell commands run before removing a worktree
on_remove:
  - echo "Removing $GWT_BRANCH"
  - dropdb --if-exists "myapp_${GWT_WT_SLUG}"

# Named commands for gwt run
commands:
  setup: bundle install && yarn install
  console: bin/rails console
  test: bundle exec rspec
```

### `.worktreeinclude`

Optionally, place a `.worktreeinclude` file at the repo root to list **gitignored** files that should be copied
into each new worktree — handy for `.env`, editor settings, local certs, and other untracked-but-needed files.
It uses **gitignore syntax** and follows the convention shared by
[satococoa/git-worktreeinclude](https://github.com/satococoa/git-worktreeinclude) and
[Conductor](https://www.conductor.build/docs/reference/worktreeinclude):

```gitignore
# Copied into every new worktree (only if Git ignores them)
.env
.env.local
!.env.example          # negation excludes a match

.vscode/settings.json
certs/local/**
```

Only files that match a pattern **and** are ignored by Git are copied. Tracked files are already checked out by
`git worktree add`, so they are never copied; an untracked file that Git does **not** ignore is skipped with a
warning. Entries here are **added to** (not replaced by) the `copy` config list, and `skip_copy` still applies.

A personal **`.worktreeinclude.local`** (gitignored, added by `gwt init`) mirrors the shared file for patterns
you don't want to commit. It is read **after** `.worktreeinclude`, so it can add patterns of its own or negate
shared ones:

```gitignore
# .worktreeinclude.local — yours only
.envrc
!certs/local/**        # opt out of a shared entry
```

Either worktreeinclude file also makes `.gwt/config.yml` **optional**: with one present but `.gwt/config.yml`
missing, commands run silently against the default `worktrees_root` of `.worktrees`. If **neither** file is
present, commands warn that at least one of them should exist but still proceed with defaults.

### Environment variables

Available in all hooks and `gwt run` commands:

| Variable | Value |
|----------|-------|
| `GWT_BRANCH` | Branch name (e.g. `feature/auth`) |
| `GWT_WT_SLUG` | Branch name with `/` and `-` replaced by `_` (e.g. `feature_auth`) — safe for database names / identifiers |
| `GWT_WT_PATH` | Absolute path to the worktree |
| `GWT_WT_REL_PATH` | Worktree path relative to repo root (may start with `..` for worktrees outside the repo root) |
| `GWT_REPO_PATH` | Absolute path to the main repo root |

## Commands

| Command | Description |
|---------|-------------|
| `gwt init [--yes]` | Initialize GWT in the current repo (pick which files to create) |
| `gwt add <branch> [--force-sync]` | Create worktree, sync files, run `on_create` hooks |
| `gwt sync (--branch <branch> \| --worktree-dir <path>) [--force] [--run-hooks]` | Sync files into an existing worktree (created by any tool) |
| `gwt remove <branch> [--force]` | Run `on_remove` hooks and remove worktree |
| `gwt remove-hooks (--branch <branch> \| --worktree-dir <path>)` | Run `on_remove` hooks for an existing worktree without removing it |
| `gwt list` | List all worktrees (branch + path) |
| `gwt cd <branch>` | Print worktree path (used by the `gcd` shell alias) |
| `gwt run <command> [--branch <branch>]` | Run a named command in a worktree |
| `gwt shell-init <bash\|zsh>` | Output shell integration snippet |

### `gwt init`

Prompts with a checkbox list for the files to create, skipping any that already exist:

| File | Default | Purpose |
|------|---------|---------|
| `.gwt/config.yml` | selected | shared config, commit this |
| `.gwt/config.local.yml` | — | personal overrides, gitignored |
| `.worktreeinclude` | selected | gitignored files to copy, commit this |
| `.worktreeinclude.local` | — | personal files to copy, gitignored |

It then adds the two personal files and the worktrees directory to `.gitignore`. Pass `--yes` to skip the
prompt and create the default selection; without a terminal (CI, pipes) it does that automatically.

### `gwt add`

- Branch must already exist locally or as a remote tracking branch
- Directory name: slashes in branch names become `--` (e.g. `feature/auth` → `.worktrees/feature--auth`)
- Use `--force-sync` to overwrite files that already exist in the worktree

### `gwt sync`

Syncs `copy`/`link` files into a worktree that **already exists** — useful when another tool
(e.g. Superconductor) creates the worktree itself, possibly outside `worktrees_root`. The worktree
is located by one of:

- `--branch <branch>` — find the registered worktree for that branch
- `--worktree-dir <path>` — find by path; accepts absolute, `~`-prefixed, or relative (to the cwd) paths

The path must be a worktree git already knows about (`git worktree list`). By default existing files
are skipped; pass `--force` to overwrite. Pass `--run-hooks` to also run `on_create` hooks after syncing.

```bash
# from the repo root, for a worktree another tool created:
gwt sync --branch my-branch
gwt sync --worktree-dir ~/elsewhere/my-branch --force --run-hooks
```

### `gwt remove-hooks`

Runs the `on_remove` hooks for an existing worktree **without removing it** — for tools that delete
worktrees themselves but let you register a cleanup script. Locate the worktree exactly like `gwt sync`
(`--branch` or `--worktree-dir`). Run it while the worktree still exists, before the external tool
deletes it.

```bash
# in a cleanup script invoked by the external tool, before it deletes the worktree:
gwt remove-hooks --worktree-dir "$WORKTREE_PATH"
```

### `gwt remove`

- Prompts for confirmation if the worktree has uncommitted tracked-file changes
- Use `--force` to skip the prompt and force removal
- Untracked files (e.g. synced `.env` copies) do not count as dirty

### `gwt run`

- From repo root: `--branch <branch>` is required
- From inside a worktree: uses the current branch automatically (`--branch` is an error)
- Replaces the current process via `execvp` for full terminal control (interactive consoles, etc.)

### `gwt list` output format

```
main            /home/user/project
feature--auth   /home/user/project/.worktrees/feature--auth
```

## File Sync Behaviour

When `gwt add` creates a worktree:

1. Glob patterns in `copy` and `link` are expanded against the main repo root; `.worktreeinclude` patterns
   additionally select gitignored files to copy (see [`.worktreeinclude`](#worktreeinclude))
2. Paths matching `skip_copy` / `skip_link` are excluded
3. For each resolved path:
   - If target already exists in the worktree: print warning and skip (use `--force-sync` to overwrite)
   - Otherwise: create parent directories as needed, then copy or symlink
4. **Copy** uses `shutil.copytree` (directories) / `shutil.copy2` (files)
5. **Symlink** creates an absolute symlink pointing to the main repo

## Hook Behaviour

- Hooks run sequentially in the worktree directory
- If a hook fails, remaining hooks are skipped and an error is printed
- A failing `on_create` hook does **not** roll back the worktree — it stays, you fix and re-run
- A failing `on_remove` hook does **not** prevent worktree removal — removal proceeds with a warning

## Requirements

- Python 3.10+
- Linux or macOS (symlinks require no special setup)
- Git

## Development

```bash
git clone https://github.com/senid231/git_worktree_manager.git
cd git_worktree_manager
pip install -e ".[dev]"

pytest             # run tests
ruff check gwt/    # lint
mypy gwt/          # type check
ruff format gwt/   # format
```

## Versioning

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Changes are documented in [CHANGELOG.md](CHANGELOG.md) following the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

### Releasing a new version

1. **Update the version** in `pyproject.toml`:
   ```toml
   version = "X.Y.Z"
   ```

2. **Update `CHANGELOG.md`** — rename `[Unreleased]` to the new version with today's date, and add a fresh `[Unreleased]` section above it:
   ```markdown
   ## [Unreleased]

   ## [X.Y.Z] - YYYY-MM-DD
   ...existing entries...
   ```

3. **Commit and tag**:
   ```bash
   git add pyproject.toml CHANGELOG.md
   git commit -m "Release vX.Y.Z"
   git tag vX.Y.Z
   git push origin master --tags
   ```

## License

[MIT](LICENSE) © Denis Talakevich
