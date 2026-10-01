from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from git import GitCommandError, Repo

from gwt.config import GwtConfig
from gwt.sync import sync_files


@dataclass(frozen=True)
class WorktreeInfo:
    path: Path
    branch: str | None


def sanitize_branch_name(branch: str) -> str:
    """Convert branch name to a filesystem-safe directory name."""
    return branch.replace("/", "--")


def branch_slug(branch: str) -> str:
    """Convert a branch name to a slug safe for identifiers (e.g. database names).

    Replaces '/' and '-' with '_' so the result is usable as a SQL/shell identifier.
    """
    return branch.replace("/", "_").replace("-", "_")


def resolve_worktree_path(config: GwtConfig, repo_root: Path, branch: str) -> Path:
    """Resolve the worktree directory path for a branch."""
    return repo_root / config.worktrees_root / sanitize_branch_name(branch)


def list_worktrees(repo_root: Path) -> list[WorktreeInfo]:
    """List all worktrees for the repo."""
    repo = Repo(repo_root)
    result: list[WorktreeInfo] = []
    for wt in repo.git.worktree("list", "--porcelain").split("\n\n"):
        wt_path: Path | None = None
        branch: str | None = None
        for line in wt.strip().splitlines():
            if line.startswith("worktree "):
                wt_path = Path(line.split(" ", 1)[1]).resolve()
            elif line.startswith("branch "):
                ref = line.split(" ", 1)[1]
                branch = ref.removeprefix("refs/heads/")
        if wt_path is not None:
            result.append(WorktreeInfo(path=wt_path, branch=branch))
    return result


def find_worktree_by_branch(repo_root: Path, branch: str) -> WorktreeInfo | None:
    """Find a worktree by branch name. Returns None if not found."""
    for wt in list_worktrees(repo_root):
        if wt.branch == branch:
            return wt
    return None


def find_worktree_by_path(repo_root: Path, wt_dir: Path) -> WorktreeInfo | None:
    """Find a registered worktree by its directory path. Returns None if not found.

    Accepts absolute, ``~``-prefixed, or relative paths (resolved against the cwd).
    """
    target = Path(wt_dir).expanduser().resolve()
    for wt in list_worktrees(repo_root):
        if wt.path == target:
            return wt
    return None


def list_available_branches(repo_root: Path) -> list[str]:
    """List git branches (local and remote) that don't already have a worktree."""
    repo = Repo(repo_root)
    existing = {wt.branch for wt in list_worktrees(repo_root) if wt.branch}

    branches: set[str] = set()
    for ref in repo.branches:
        branches.add(ref.name)
    for remote in repo.remotes:
        for ref in remote.refs:
            branches.add(ref.remote_head)

    return sorted(branches - existing)


def _branch_exists(repo: Repo, branch: str) -> bool:
    """Check if a branch exists locally or as a remote tracking branch."""
    # Check local branches
    if branch in [ref.name for ref in repo.branches]:
        return True
    # Check remote tracking branches (origin/<branch>)
    for remote in repo.remotes:
        for ref in remote.refs:
            if ref.remote_head == branch:
                return True
    return False


def _git_error_message(e: GitCommandError) -> str:
    """Return git's own error lines, without GitPython's command dump."""
    stderr = str(e.stderr).strip().removeprefix("stderr: '").removesuffix("'")
    fatal = [line for line in stderr.splitlines() if line.startswith(("fatal:", "error:"))]
    return " ".join(fatal) or stderr or str(e)


def add_worktree(
    config: GwtConfig,
    repo_root: Path,
    branch: str,
    force_sync: bool,
) -> Path:
    """Create a worktree for the given branch, sync files, return the worktree path."""
    repo = Repo(repo_root)

    wt_path = resolve_worktree_path(config, repo_root, branch)
    if wt_path.exists():
        raise ValueError(f"Worktree directory already exists: {wt_path}")

    existing = find_worktree_by_branch(repo_root, branch)
    if existing is not None:
        raise ValueError(f"Branch '{branch}' is already checked out in worktree at {existing.path}")

    try:
        if _branch_exists(repo, branch):
            repo.git.worktree("add", str(wt_path), branch)
        else:
            repo.git.worktree("add", "-b", branch, str(wt_path))
    except GitCommandError as e:
        raise ValueError(f"git worktree add failed: {_git_error_message(e)}") from e
    sync_files(config, repo_root, wt_path, force=force_sync)

    return wt_path


def remove_worktree(repo_root: Path, branch: str, force: bool) -> Path:
    """Remove a worktree for the given branch. Returns the removed path."""
    wt_info = find_worktree_by_branch(repo_root, branch)
    if wt_info is None:
        raise ValueError(f"No worktree found for branch '{branch}'.")

    repo = Repo(repo_root)
    args = ["remove"]
    if force:
        args.append("--force")
    args.append(str(wt_info.path))
    repo.git.worktree(*args)
    return wt_info.path


def is_worktree_dirty(wt_path: Path) -> bool:
    """Check if a worktree has uncommitted changes to tracked files."""
    repo = Repo(wt_path)
    # Check for staged or unstaged changes to tracked files only
    return repo.is_dirty(untracked_files=False)


def build_env_vars(repo_root: Path, wt_path: Path, branch: str) -> dict[str, str]:
    """Build a full process environment with GWT variables overlaid."""
    env = os.environ.copy()
    env["GWT_BRANCH"] = branch
    env["GWT_WT_SLUG"] = branch_slug(branch)
    env["GWT_WT_PATH"] = str(wt_path)
    # Worktrees may live outside repo_root (e.g. created by external tools), so
    # use relpath rather than Path.relative_to, which would raise for such paths.
    env["GWT_WT_REL_PATH"] = os.path.relpath(wt_path, repo_root)
    env["GWT_REPO_PATH"] = str(repo_root)
    return env


def run_hooks(hooks: list[str], wt_path: Path, env: dict[str, str]) -> None:
    """Run hook commands sequentially. Raises RuntimeError on first failure."""
    for cmd in hooks:
        result = subprocess.run(cmd, shell=True, cwd=wt_path, env=env)
        if result.returncode != 0:
            raise RuntimeError(f"hook failed (exit {result.returncode}): {cmd}")
