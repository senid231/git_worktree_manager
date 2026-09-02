from __future__ import annotations

import os
from pathlib import Path

import pytest
from git import Repo

from gwt.config import GwtConfig
from gwt.worktree import (
    add_worktree,
    branch_slug,
    build_env_vars,
    find_worktree_by_branch,
    find_worktree_by_path,
    is_worktree_dirty,
    list_available_branches,
    list_worktrees,
    remove_worktree,
    resolve_worktree_path,
    run_hooks,
    sanitize_branch_name,
)


class TestSanitizeBranchName:
    def test_simple_name(self) -> None:
        assert sanitize_branch_name("feature") == "feature"

    def test_slashes_to_double_dashes(self) -> None:
        assert sanitize_branch_name("feature/auth") == "feature--auth"

    def test_multiple_slashes(self) -> None:
        assert sanitize_branch_name("feature/auth/login") == "feature--auth--login"


class TestBranchSlug:
    def test_simple_name(self) -> None:
        assert branch_slug("feature") == "feature"

    def test_slash_to_underscore(self) -> None:
        assert branch_slug("feature/auth") == "feature_auth"

    def test_dash_to_underscore(self) -> None:
        assert branch_slug("my-feature") == "my_feature"

    def test_slash_and_dash(self) -> None:
        assert branch_slug("feature/my-auth-login") == "feature_my_auth_login"


class TestResolveWorktreePath:
    def test_resolve(self, tmp_git_repo: Path) -> None:
        config = GwtConfig(worktrees_root=".worktrees")
        result = resolve_worktree_path(config, tmp_git_repo, "feature/auth")
        assert result == tmp_git_repo / ".worktrees" / "feature--auth"


class TestListWorktrees:
    def test_list_includes_main_and_branches(self, tmp_git_repo: Path) -> None:
        repo = Repo(tmp_git_repo)
        repo.create_head("test-branch")
        wt_path = tmp_git_repo / ".worktrees" / "test-branch"
        repo.git.worktree("add", str(wt_path), "test-branch")
        worktrees = list_worktrees(tmp_git_repo)
        branches = [wt.branch for wt in worktrees]
        assert "master" in branches or "main" in branches
        assert "test-branch" in branches

    def test_list_empty_repo(self, tmp_git_repo: Path) -> None:
        worktrees = list_worktrees(tmp_git_repo)
        assert len(worktrees) == 1  # just main


class TestListAvailableBranches:
    def test_excludes_main_worktree_branch(self, tmp_git_repo: Path) -> None:
        branches = list_available_branches(tmp_git_repo)
        assert "master" not in branches and "main" not in branches

    def test_includes_local_branch_without_worktree(self, tmp_git_repo: Path) -> None:
        Repo(tmp_git_repo).create_head("feature-x")
        branches = list_available_branches(tmp_git_repo)
        assert "feature-x" in branches

    def test_excludes_branch_with_existing_worktree(self, tmp_git_repo: Path) -> None:
        repo = Repo(tmp_git_repo)
        repo.create_head("feature-x")
        wt_path = tmp_git_repo / ".worktrees" / "feature-x"
        repo.git.worktree("add", str(wt_path), "feature-x")
        branches = list_available_branches(tmp_git_repo)
        assert "feature-x" not in branches

    def test_returns_sorted(self, tmp_git_repo: Path) -> None:
        repo = Repo(tmp_git_repo)
        repo.create_head("zebra")
        repo.create_head("alpha")
        branches = list_available_branches(tmp_git_repo)
        assert branches == sorted(branches)


class TestFindWorktreeByBranch:
    def test_find_existing(self, tmp_git_repo: Path) -> None:
        repo = Repo(tmp_git_repo)
        repo.create_head("test-branch")
        wt_path = tmp_git_repo / ".worktrees" / "test-branch"
        repo.git.worktree("add", str(wt_path), "test-branch")
        result = find_worktree_by_branch(tmp_git_repo, "test-branch")
        assert result is not None
        assert result.path == wt_path

    def test_find_nonexistent(self, tmp_git_repo: Path) -> None:
        result = find_worktree_by_branch(tmp_git_repo, "no-such-branch")
        assert result is None


class TestFindWorktreeByPath:
    def test_find_absolute_path(self, tmp_git_repo: Path) -> None:
        repo = Repo(tmp_git_repo)
        repo.create_head("test-branch")
        wt_path = tmp_git_repo / ".worktrees" / "test-branch"
        repo.git.worktree("add", str(wt_path), "test-branch")
        result = find_worktree_by_path(tmp_git_repo, wt_path)
        assert result is not None
        assert result.branch == "test-branch"

    def test_find_outside_repo_root(self, tmp_git_repo: Path) -> None:
        repo = Repo(tmp_git_repo)
        repo.create_head("ext-branch")
        # Worktree created in a directory that is NOT under repo root (uniquely-named sibling)
        external = tmp_git_repo.parent / f"{tmp_git_repo.name}-ext" / "ext-branch"
        repo.git.worktree("add", str(external), "ext-branch")
        result = find_worktree_by_path(tmp_git_repo, external)
        assert result is not None
        assert result.path == external.resolve()
        assert result.branch == "ext-branch"

    def test_find_relative_path(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        repo = Repo(tmp_git_repo)
        repo.create_head("test-branch")
        wt_path = tmp_git_repo / ".worktrees" / "test-branch"
        repo.git.worktree("add", str(wt_path), "test-branch")
        monkeypatch.chdir(tmp_git_repo)
        result = find_worktree_by_path(tmp_git_repo, Path(".worktrees/test-branch"))
        assert result is not None
        assert result.branch == "test-branch"

    def test_find_nonexistent_path(self, tmp_git_repo: Path) -> None:
        result = find_worktree_by_path(tmp_git_repo, tmp_git_repo / "nope")
        assert result is None


class TestAddWorktree:
    def test_add_creates_worktree(self, tmp_git_repo: Path) -> None:
        repo = Repo(tmp_git_repo)
        repo.create_head("test-branch")
        config = GwtConfig(worktrees_root=".worktrees")
        wt_path = add_worktree(config, tmp_git_repo, "test-branch", force_sync=False)
        assert wt_path.exists()
        assert (wt_path / ".git").exists()

    def test_add_creates_new_branch_if_missing(self, tmp_git_repo: Path) -> None:
        config = GwtConfig(worktrees_root=".worktrees")
        wt_path = add_worktree(config, tmp_git_repo, "new-branch", force_sync=False)
        assert wt_path.exists()
        assert Repo(wt_path).active_branch.name == "new-branch"

    def test_add_branch_already_has_worktree_raises(self, tmp_git_repo: Path) -> None:
        repo = Repo(tmp_git_repo)
        repo.create_head("test-branch")
        config = GwtConfig(worktrees_root=".worktrees")
        add_worktree(config, tmp_git_repo, "test-branch", force_sync=False)
        with pytest.raises(ValueError):
            add_worktree(config, tmp_git_repo, "test-branch", force_sync=False)

    def test_add_with_slash_in_branch_name(self, tmp_git_repo: Path) -> None:
        repo = Repo(tmp_git_repo)
        repo.create_head("feature/auth")
        config = GwtConfig(worktrees_root=".worktrees")
        wt_path = add_worktree(config, tmp_git_repo, "feature/auth", force_sync=False)
        assert wt_path.name == "feature--auth"
        assert wt_path.exists()


class TestRemoveWorktree:
    def test_remove_deletes_worktree(self, tmp_git_repo: Path) -> None:
        repo = Repo(tmp_git_repo)
        repo.create_head("test-branch")
        config = GwtConfig(worktrees_root=".worktrees")
        wt_path = add_worktree(config, tmp_git_repo, "test-branch", force_sync=False)
        assert wt_path.exists()
        remove_worktree(tmp_git_repo, "test-branch", force=True)
        assert not wt_path.exists()

    def test_remove_nonexistent_branch_raises(self, tmp_git_repo: Path) -> None:
        with pytest.raises(ValueError):
            remove_worktree(tmp_git_repo, "no-such-branch", force=False)


class TestIsWorktreeDirty:
    def test_clean_worktree(self, tmp_git_repo: Path) -> None:
        repo = Repo(tmp_git_repo)
        repo.create_head("test-branch")
        wt_path = tmp_git_repo / ".worktrees" / "test-branch"
        repo.git.worktree("add", str(wt_path), "test-branch")
        assert is_worktree_dirty(wt_path) is False

    def test_dirty_worktree_with_modified_tracked_file(self, tmp_git_repo: Path) -> None:
        repo = Repo(tmp_git_repo)
        repo.create_head("test-branch")
        wt_path = tmp_git_repo / ".worktrees" / "test-branch"
        repo.git.worktree("add", str(wt_path), "test-branch")
        (wt_path / "README.md").write_text("modified")
        assert is_worktree_dirty(wt_path) is True

    def test_untracked_files_not_dirty(self, tmp_git_repo: Path) -> None:
        repo = Repo(tmp_git_repo)
        repo.create_head("test-branch")
        wt_path = tmp_git_repo / ".worktrees" / "test-branch"
        repo.git.worktree("add", str(wt_path), "test-branch")
        (wt_path / "newfile.txt").write_text("new")
        assert is_worktree_dirty(wt_path) is False


class TestBuildEnvVars:
    def test_env_vars(self, tmp_git_repo: Path) -> None:
        wt_path = tmp_git_repo / ".worktrees" / "feature--auth"
        env = build_env_vars(tmp_git_repo, wt_path, "feature/auth")
        assert env["GWT_BRANCH"] == "feature/auth"
        assert env["GWT_WT_SLUG"] == "feature_auth"
        assert env["GWT_WT_PATH"] == str(wt_path)
        assert env["GWT_REPO_PATH"] == str(tmp_git_repo)
        assert env["GWT_WT_REL_PATH"] == ".worktrees/feature--auth"

    def test_env_vars_worktree_outside_repo_root(self, tmp_git_repo: Path) -> None:
        # Worktrees created by external tools may live outside repo_root (sibling dir here).
        wt_path = tmp_git_repo.parent / "external" / "ext-branch"
        env = build_env_vars(tmp_git_repo, wt_path, "ext-branch")
        assert env["GWT_WT_PATH"] == str(wt_path)
        assert env["GWT_WT_REL_PATH"] == os.path.relpath(wt_path, tmp_git_repo)
        assert env["GWT_WT_REL_PATH"].startswith("..")


class TestRunHooks:
    def test_run_hooks_success(self, tmp_git_repo: Path) -> None:
        wt_path = tmp_git_repo / ".worktrees" / "test"
        wt_path.mkdir(parents=True)
        marker = wt_path / "hook_ran"
        hooks = [f"touch {marker}"]
        env = build_env_vars(tmp_git_repo, wt_path, "test")
        run_hooks(hooks, wt_path, env)
        assert marker.exists()

    def test_run_hooks_stops_on_failure(self, tmp_git_repo: Path) -> None:
        wt_path = tmp_git_repo / ".worktrees" / "test"
        wt_path.mkdir(parents=True)
        marker = wt_path / "should_not_exist"
        hooks = ["exit 1", f"touch {marker}"]
        env = build_env_vars(tmp_git_repo, wt_path, "test")
        with pytest.raises(RuntimeError, match="hook failed"):
            run_hooks(hooks, wt_path, env)
        assert not marker.exists()
