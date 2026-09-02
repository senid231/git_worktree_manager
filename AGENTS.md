## Project

GWT (Git Worktree Manager) — a Python CLI tool that automates git worktree management with file syncing, hooks, named commands, and shell navigation. Entry point: `gwt = "gwt.cli:app"` (Typer CLI).

## Commands

```bash
# Install for development
pip install -e ".[dev]"

# Run all tests
pytest

# Run a single test file
pytest tests/test_config.py

# Run a single test class/method
pytest tests/test_config.py::TestValidateConfig::test_valid_minimal

# Lint
ruff check gwt/

# Format
ruff format gwt/

# Type check
mypy gwt/
```

## Architecture

Six modules under `gwt/`, each with a single responsibility:

- **cli.py** — All Typer commands (`init`, `add`, `sync`, `remove`, `remove-hooks`, `list`, `cd`, `run`, `shell-init`) plus tab-completion functions. Entry point for the app. `init` prompts with a `questionary` checkbox (`_INIT_FILES`) for which of the four config files to create, skipping ones that exist; `--yes` or a non-TTY (`_is_interactive`) falls back to the `default=True` subset. `sync` / `remove-hooks` locate a worktree by `--branch` or `--worktree-dir` (shared `_locate_worktree` helper) and operate on worktrees created by any tool, including ones outside `worktrees_root`.
- **config.py** — Loads/validates/merges dual config files (`.gwt/config.yml` shared + `.gwt/config.local.yml` personal). Merge strategy: lists concatenate, scalars override, commands deep-merge. `gwt init` seeds new files from the packaged `gwt/*.example` templates (read via `importlib.resources`).
- **context.py** — Detects repo state (`RepoContext` dataclass) using GitPython's `common_dir` vs `git_dir` to distinguish main repo from worktree.
- **worktree.py** — Git worktree CRUD, lookup by branch (`find_worktree_by_branch`) or path (`find_worktree_by_path`), branch listing, dirty checks, hook execution, and `GWT_*` environment variable building. Branch names sanitized for dir names (slashes → `--`) and slugified for `GWT_WT_SLUG` (`/` and `-` → `_`). `GWT_WT_REL_PATH` uses `os.path.relpath` so worktrees outside the repo root don't crash.
- **sync.py** — File synchronization via glob patterns with skip filters. Supports both copy (`shutil.copy2`/`copytree`) and symlink modes. Also honors repo-root `.worktreeinclude` and `.worktreeinclude.local` files (gitignore syntax): files matching their patterns *and* ignored by Git (resolved via `git ls-files --others --ignored` with one `--exclude-from` per file, plus `git check-ignore`) are copied on top of the `copy` list. The local file is passed last so its `!` negations override the shared one. Tracked files are skipped automatically; matched-but-not-ignored files are skipped with a warning.
- **shell.py** — Generates shell integration snippets (`gwt_cd` function + `gcd` alias + completions) for bash/zsh.

## Key Design Decisions

- `gwt run` uses `os.execvpe()` to replace the process (full terminal control for interactive commands).
- Hooks run sequentially and stop on first failure but don't roll back prior steps.
- `is_worktree_dirty()` ignores untracked files — only uncommitted tracked-file changes count.
- Config validation rejects `worktrees_root` with `..` segments (path traversal prevention).
- A missing `.gwt/config.yml` warns only when no worktreeinclude file is present either — a worktreeinclude-only setup is deliberate, so it falls back to defaults silently.

## Testing

Tests use pytest with Typer's `CliRunner` for CLI tests and `monkeypatch` for cwd isolation. Each module has a corresponding `tests/test_<module>.py` file. Test fixtures in `tests/conftest.py` create temporary git repos.
