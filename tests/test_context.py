from __future__ import annotations

from pathlib import Path

import pytest
from git import Repo

from gwt.context import detect_context
from tests.conftest import write_config


class TestDetectContext:
    def test_main_repo_root(self, tmp_git_repo: Path) -> None:
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees"})
        ctx = detect_context(tmp_git_repo)
        assert ctx.is_main_repo is True
        assert ctx.is_worktree is False
        assert ctx.repo_root == tmp_git_repo
        assert ctx.has_config is True

    def test_main_repo_without_config(self, tmp_git_repo: Path) -> None:
        ctx = detect_context(tmp_git_repo)
        assert ctx.is_main_repo is True
        assert ctx.has_config is False
        assert ctx.has_worktreeinclude is False

    def test_detects_worktreeinclude(self, tmp_git_repo: Path) -> None:
        (tmp_git_repo / ".worktreeinclude").write_text("*.env\n")
        ctx = detect_context(tmp_git_repo)
        assert ctx.has_config is False
        assert ctx.has_worktreeinclude is True

    def test_detects_worktreeinclude_local(self, tmp_git_repo: Path) -> None:
        (tmp_git_repo / ".worktreeinclude.local").write_text("*.env\n")
        ctx = detect_context(tmp_git_repo)
        assert ctx.has_config is False
        assert ctx.has_worktreeinclude is True

    def test_worktree_branch(self, tmp_git_repo: Path) -> None:
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees"})
        repo = Repo(tmp_git_repo)
        repo.create_head("test-branch")
        wt_path = tmp_git_repo / ".worktrees" / "test-branch"
        repo.git.worktree("add", str(wt_path), "test-branch")
        ctx = detect_context(wt_path)
        assert ctx.is_main_repo is False
        assert ctx.is_worktree is True
        assert ctx.repo_root == tmp_git_repo
        assert ctx.worktree_path == wt_path
        assert ctx.branch == "test-branch"
        assert ctx.has_config is True

    def test_not_a_git_repo(self, tmp_path: Path) -> None:
        plain_dir = tmp_path / "not_a_repo"
        plain_dir.mkdir()
        with pytest.raises(ValueError, match="not a git repository"):
            detect_context(plain_dir)

    def test_require_repo_root_from_worktree(self, tmp_git_repo: Path) -> None:
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees"})
        repo = Repo(tmp_git_repo)
        repo.create_head("test-branch")
        wt_path = tmp_git_repo / ".worktrees" / "test-branch"
        repo.git.worktree("add", str(wt_path), "test-branch")
        ctx = detect_context(wt_path)
        with pytest.raises(ValueError, match="repo root"):
            ctx.require_repo_root()
