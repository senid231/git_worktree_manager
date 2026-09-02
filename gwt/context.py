from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from git import InvalidGitRepositoryError, Repo

from gwt.config import GWT_CONFIG_FILE, WORKTREEINCLUDE_FILE, WORKTREEINCLUDE_LOCAL_FILE


@dataclass(frozen=True)
class RepoContext:
    """Describes whether we're in a main repo root or a worktree branch."""

    repo_root: Path
    is_main_repo: bool
    is_worktree: bool
    has_config: bool
    has_worktreeinclude: bool
    worktree_path: Path | None = None
    branch: str | None = None

    def require_repo_root(self) -> None:
        """Raise if not running from the main repo root."""
        if not self.is_main_repo:
            raise ValueError("This command must be run from the repo root, not a worktree branch.")


def detect_context(cwd: Path) -> RepoContext:
    """Detect whether cwd is a main repo root or a worktree branch."""
    try:
        repo = Repo(cwd, search_parent_directories=True)
    except InvalidGitRepositoryError as err:
        raise ValueError(f"{cwd} is not a git repository.") from err

    common_dir = Path(repo.common_dir).resolve()
    git_dir = Path(repo.git_dir).resolve()
    working_dir = Path(repo.working_dir).resolve()

    # If common_dir and git_dir point to the same .git, this is the main repo
    is_main = common_dir == git_dir
    repo_root = common_dir.parent
    has_config = (repo_root / GWT_CONFIG_FILE).exists()
    has_worktreeinclude = (repo_root / WORKTREEINCLUDE_FILE).exists() or (
        repo_root / WORKTREEINCLUDE_LOCAL_FILE
    ).exists()

    if is_main:
        return RepoContext(
            repo_root=repo_root,
            is_main_repo=True,
            is_worktree=False,
            has_config=has_config,
            has_worktreeinclude=has_worktreeinclude,
        )

    # Worktree: extract branch from HEAD
    branch = repo.active_branch.name if not repo.head.is_detached else None

    return RepoContext(
        repo_root=repo_root,
        is_main_repo=False,
        is_worktree=True,
        has_config=has_config,
        has_worktreeinclude=has_worktreeinclude,
        worktree_path=working_dir,
        branch=branch,
    )
