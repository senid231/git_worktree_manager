from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

import pytest
from git import Repo
from typer.testing import CliRunner

from gwt.cli import app
from tests.conftest import write_config

runner = CliRunner()


class TestVersion:
    def test_version_flag_outputs_version(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert f"gwt {version('gwt')}" in result.output


class TestInit:
    def test_init_creates_default_files(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert (tmp_git_repo / ".gwt" / "config.yml").exists()
        assert (tmp_git_repo / ".worktreeinclude").exists()
        # Personal files are opt-in, so the non-interactive defaults leave them out.
        assert not (tmp_git_repo / ".gwt" / "config.local.yml").exists()
        assert not (tmp_git_repo / ".worktreeinclude.local").exists()
        gitignore = (tmp_git_repo / ".gitignore").read_text()
        assert ".gwt/config.local.yml" in gitignore
        assert ".worktreeinclude.local" in gitignore
        assert ".worktrees" in gitignore

    def test_init_yes_flag_creates_default_files(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_git_repo)
        result = runner.invoke(app, ["init", "--yes"])
        assert result.exit_code == 0
        assert (tmp_git_repo / ".gwt" / "config.yml").exists()
        assert (tmp_git_repo / ".worktreeinclude").exists()

    def test_init_skips_existing_files(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees"})
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "already exists" in result.output.lower()
        # The pre-existing config is left untouched; the remaining files are still created.
        assert "worktrees_root: .worktrees" in (tmp_git_repo / ".gwt" / "config.yml").read_text()
        assert (tmp_git_repo / ".worktreeinclude").exists()

    def test_init_prompts_and_creates_selection(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_git_repo)
        monkeypatch.setattr("gwt.cli._is_interactive", lambda: True)
        asked: dict[str, object] = {}

        class _FakeQuestion:
            def ask(self) -> list[str]:
                return [".gwt/config.local.yml", ".worktreeinclude.local"]

        def fake_checkbox(message: str, choices: list[object]) -> _FakeQuestion:
            asked["message"] = message
            asked["choices"] = choices
            return _FakeQuestion()

        monkeypatch.setattr("gwt.cli.questionary.checkbox", fake_checkbox)
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert asked["message"] == "Which files should gwt create?"
        assert (tmp_git_repo / ".gwt" / "config.local.yml").exists()
        assert (tmp_git_repo / ".worktreeinclude.local").exists()
        assert not (tmp_git_repo / ".gwt" / "config.yml").exists()
        assert not (tmp_git_repo / ".worktreeinclude").exists()

    def test_init_prompt_with_empty_selection_creates_nothing(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_git_repo)
        monkeypatch.setattr("gwt.cli._is_interactive", lambda: True)

        class _FakeQuestion:
            def ask(self) -> list[str]:
                return []

        monkeypatch.setattr("gwt.cli.questionary.checkbox", lambda message, choices: _FakeQuestion())
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "nothing selected" in result.output.lower()
        assert not (tmp_git_repo / ".gwt").exists()

    def test_init_outside_git_repo(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        plain = tmp_path / "not_git"
        plain.mkdir()
        monkeypatch.chdir(plain)
        result = runner.invoke(app, ["init"])
        assert result.exit_code != 0
        assert "git repo" in result.output.lower() or "git repository" in result.output.lower()

    def test_init_already_initialized(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees"})
        (tmp_git_repo / ".gwt" / "config.local.yml").write_text("")
        (tmp_git_repo / ".worktreeinclude").write_text("")
        (tmp_git_repo / ".worktreeinclude.local").write_text("")
        result = runner.invoke(app, ["init"])
        assert result.exit_code != 0
        assert "already initialized" in result.output.lower()


class TestAdd:
    def test_add_creates_worktree(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees"})
        Repo(tmp_git_repo).create_head("test-branch")
        result = runner.invoke(app, ["add", "test-branch"])
        assert result.exit_code == 0
        assert (tmp_git_repo / ".worktrees" / "test-branch").exists()

    def test_add_from_worktree_errors(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees"})
        repo = Repo(tmp_git_repo)
        repo.create_head("test-branch")
        repo.create_head("other-branch")
        wt_path = tmp_git_repo / ".worktrees" / "test-branch"
        repo.git.worktree("add", str(wt_path), "test-branch")
        monkeypatch.chdir(wt_path)
        result = runner.invoke(app, ["add", "other-branch"])
        assert result.exit_code != 0
        assert "repo root" in result.output.lower()

    def test_add_without_config_warns_and_uses_default_root(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_git_repo)
        result = runner.invoke(app, ["add", "test-branch"])
        assert result.exit_code == 0
        assert "at least one of them should be present" in result.output.lower()
        assert (tmp_git_repo / ".worktrees" / "test-branch").exists()

    def test_add_with_worktreeinclude_no_config_is_silent(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_git_repo)
        (tmp_git_repo / ".worktreeinclude").write_text("*.env\n")
        result = runner.invoke(app, ["add", "test-branch"])
        assert result.exit_code == 0
        assert "warning" not in result.output.lower()
        assert (tmp_git_repo / ".worktrees" / "test-branch").exists()

    def test_add_with_worktreeinclude_local_only_is_silent(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_git_repo)
        (tmp_git_repo / ".worktreeinclude.local").write_text("*.env\n")
        result = runner.invoke(app, ["add", "test-branch"])
        assert result.exit_code == 0
        assert "warning" not in result.output.lower()
        assert (tmp_git_repo / ".worktrees" / "test-branch").exists()


class TestRemove:
    def test_remove_deletes_worktree(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees"})
        repo = Repo(tmp_git_repo)
        repo.create_head("test-branch")
        runner.invoke(app, ["add", "test-branch"])
        result = runner.invoke(app, ["remove", "test-branch", "--force"])
        assert result.exit_code == 0
        assert not (tmp_git_repo / ".worktrees" / "test-branch").exists()

    def test_remove_dirty_worktree_prompts(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees"})
        repo = Repo(tmp_git_repo)
        repo.create_head("test-branch")
        runner.invoke(app, ["add", "test-branch"])
        wt_path = tmp_git_repo / ".worktrees" / "test-branch"
        (wt_path / "README.md").write_text("dirty")
        # Deny the confirmation prompt
        runner.invoke(app, ["remove", "test-branch"], input="n\n")
        assert wt_path.exists()  # worktree should still exist


class TestSync:
    def _make_external_worktree(self, tmp_git_repo: Path, dest: Path, branch: str = "ext-branch") -> Path:
        repo = Repo(tmp_git_repo)
        repo.create_head(branch)
        repo.git.worktree("add", str(dest), branch)
        return dest

    def test_sync_by_branch_copies_file(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees", "copy": [".env"]})
        (tmp_git_repo / ".env").write_text("SECRET=1")
        wt = tmp_git_repo / ".worktrees" / "ext-branch"
        self._make_external_worktree(tmp_git_repo, wt)
        result = runner.invoke(app, ["sync", "--branch", "ext-branch"])
        assert result.exit_code == 0
        assert (wt / ".env").read_text() == "SECRET=1"

    def test_sync_by_worktree_dir_outside_root(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees", "copy": [".env"]})
        (tmp_git_repo / ".env").write_text("SECRET=1")
        # Worktree genuinely outside repo root (uniquely-named sibling), as an external tool might create.
        dest = tmp_git_repo.parent / f"{tmp_git_repo.name}-ext" / "ext-branch"
        external = self._make_external_worktree(tmp_git_repo, dest)
        result = runner.invoke(app, ["sync", "--worktree-dir", str(external)])
        assert result.exit_code == 0
        assert (external / ".env").read_text() == "SECRET=1"

    def test_sync_auto_detects_current_worktree(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees", "copy": [".env"]})
        (tmp_git_repo / ".env").write_text("SECRET=1")
        wt = self._make_external_worktree(tmp_git_repo, tmp_git_repo / ".worktrees" / "ext-branch")
        monkeypatch.chdir(wt)
        result = runner.invoke(app, ["sync"])
        assert result.exit_code == 0
        assert (wt / ".env").read_text() == "SECRET=1"

    def test_sync_requires_selector_from_main_repo(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees"})
        none = runner.invoke(app, ["sync"])
        assert none.exit_code != 0
        assert "exactly one" in none.output.lower()
        wt = self._make_external_worktree(tmp_git_repo, tmp_git_repo / ".worktrees" / "ext-branch")
        both = runner.invoke(app, ["sync", "--branch", "ext-branch", "--worktree-dir", str(wt)])
        assert both.exit_code != 0
        assert "exactly one" in both.output.lower()

    def test_sync_unknown_branch_errors(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees"})
        result = runner.invoke(app, ["sync", "--branch", "no-such-branch"])
        assert result.exit_code != 0
        assert "no worktree found" in result.output.lower()

    def test_sync_unregistered_path_errors(
        self, tmp_git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees"})
        result = runner.invoke(app, ["sync", "--worktree-dir", str(tmp_path / "not-a-worktree")])
        assert result.exit_code != 0
        assert "no worktree registered" in result.output.lower()

    def test_sync_skips_existing_without_force(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees", "copy": [".env"]})
        (tmp_git_repo / ".env").write_text("NEW=1")
        wt = self._make_external_worktree(tmp_git_repo, tmp_git_repo / ".worktrees" / "ext-branch")
        (wt / ".env").write_text("OLD=1")
        result = runner.invoke(app, ["sync", "--branch", "ext-branch"])
        assert result.exit_code == 0
        assert (wt / ".env").read_text() == "OLD=1"  # not overwritten

    def test_sync_force_overwrites(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees", "copy": [".env"]})
        (tmp_git_repo / ".env").write_text("NEW=1")
        wt = self._make_external_worktree(tmp_git_repo, tmp_git_repo / ".worktrees" / "ext-branch")
        (wt / ".env").write_text("OLD=1")
        result = runner.invoke(app, ["sync", "--branch", "ext-branch", "--force"])
        assert result.exit_code == 0
        assert (wt / ".env").read_text() == "NEW=1"

    def test_sync_run_hooks(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(
            tmp_git_repo,
            {"worktrees_root": ".worktrees", "on_create": ["touch hook_ran"]},
        )
        wt = self._make_external_worktree(tmp_git_repo, tmp_git_repo / ".worktrees" / "ext-branch")
        result = runner.invoke(app, ["sync", "--branch", "ext-branch", "--run-hooks"])
        assert result.exit_code == 0
        assert (wt / "hook_ran").exists()

    def test_sync_run_hooks_worktree_outside_root(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # The superconductor case end-to-end: external worktree dir + on_create hooks.
        # Exercises the GWT_WT_REL_PATH relpath handling for paths outside repo_root.
        monkeypatch.chdir(tmp_git_repo)
        write_config(
            tmp_git_repo,
            {"worktrees_root": ".worktrees", "on_create": ['echo "$GWT_WT_REL_PATH" > rel_path']},
        )
        dest = tmp_git_repo.parent / f"{tmp_git_repo.name}-ext" / "ext-branch"
        external = self._make_external_worktree(tmp_git_repo, dest)
        result = runner.invoke(app, ["sync", "--worktree-dir", str(external), "--run-hooks"])
        assert result.exit_code == 0
        assert (external / "rel_path").read_text().strip().startswith("..")

    def test_sync_without_run_hooks_does_not_run_them(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(
            tmp_git_repo,
            {"worktrees_root": ".worktrees", "on_create": ["touch hook_ran"]},
        )
        wt = self._make_external_worktree(tmp_git_repo, tmp_git_repo / ".worktrees" / "ext-branch")
        result = runner.invoke(app, ["sync", "--branch", "ext-branch"])
        assert result.exit_code == 0
        assert not (wt / "hook_ran").exists()

    def test_sync_only_hooks_runs_hooks_without_copying(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(
            tmp_git_repo,
            {"worktrees_root": ".worktrees", "copy": [".env"], "on_create": ["touch hook_ran"]},
        )
        (tmp_git_repo / ".env").write_text("SECRET=1")
        wt = self._make_external_worktree(tmp_git_repo, tmp_git_repo / ".worktrees" / "ext-branch")
        result = runner.invoke(app, ["sync", "--branch", "ext-branch", "--only-hooks"])
        assert result.exit_code == 0
        assert not (wt / ".env").exists()
        assert (wt / "hook_ran").exists()

    def test_sync_only_hooks_and_force_errors(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees"})
        self._make_external_worktree(tmp_git_repo, tmp_git_repo / ".worktrees" / "ext-branch")
        result = runner.invoke(app, ["sync", "--branch", "ext-branch", "--only-hooks", "--force"])
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower()

    def test_sync_without_config_warns_then_locates(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        result = runner.invoke(app, ["sync", "--branch", "ext-branch"])
        # Missing config no longer blocks; the command warns, then fails locating the worktree.
        assert "at least one of them should be present" in result.output.lower()
        assert result.exit_code != 0
        assert "no worktree found" in result.output.lower()

    def test_sync_with_worktreeinclude_no_config(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        (tmp_git_repo / ".worktreeinclude").write_text("ignored.txt\n")
        (tmp_git_repo / ".gitignore").write_text("ignored.txt\n")
        (tmp_git_repo / "ignored.txt").write_text("payload")
        self._make_external_worktree(tmp_git_repo, tmp_git_repo / "ext" / "ext-branch")
        result = runner.invoke(app, ["sync", "--branch", "ext-branch"])
        assert result.exit_code == 0
        assert "warning" not in result.output.lower()
        assert (tmp_git_repo / "ext" / "ext-branch" / "ignored.txt").exists()


class TestRemoveHooks:
    def _make_external_worktree(self, tmp_git_repo: Path, dest: Path, branch: str = "ext-branch") -> Path:
        repo = Repo(tmp_git_repo)
        repo.create_head(branch)
        repo.git.worktree("add", str(dest), branch)
        return dest

    def test_runs_on_remove_by_branch(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees", "on_remove": ["touch cleanup_ran"]})
        wt = self._make_external_worktree(tmp_git_repo, tmp_git_repo / ".worktrees" / "ext-branch")
        result = runner.invoke(app, ["remove-hooks", "--branch", "ext-branch"])
        assert result.exit_code == 0
        assert (wt / "cleanup_ran").exists()

    def test_runs_on_remove_by_worktree_dir(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(
            tmp_git_repo,
            {"worktrees_root": ".worktrees", "on_remove": ['echo "$GWT_WT_SLUG" > slug']},
        )
        wt = self._make_external_worktree(tmp_git_repo, tmp_git_repo / ".worktrees" / "ext-branch", branch="feat/x-y")
        result = runner.invoke(app, ["remove-hooks", "--worktree-dir", str(wt)])
        assert result.exit_code == 0
        assert (wt / "slug").read_text().strip() == "feat_x_y"

    def test_does_not_remove_the_worktree(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees", "on_remove": ["echo bye"]})
        wt = self._make_external_worktree(tmp_git_repo, tmp_git_repo / ".worktrees" / "ext-branch")
        runner.invoke(app, ["remove-hooks", "--branch", "ext-branch"])
        assert wt.exists()  # remove-hooks only runs hooks; it must not delete the worktree

    def test_no_hooks_configured_is_noop(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees"})
        self._make_external_worktree(tmp_git_repo, tmp_git_repo / ".worktrees" / "ext-branch")
        result = runner.invoke(app, ["remove-hooks", "--branch", "ext-branch"])
        assert result.exit_code == 0
        assert "no on_remove hooks" in result.output.lower()

    def test_auto_detects_current_worktree(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees", "on_remove": ["touch cleanup_ran"]})
        wt = self._make_external_worktree(tmp_git_repo, tmp_git_repo / ".worktrees" / "ext-branch")
        monkeypatch.chdir(wt)
        result = runner.invoke(app, ["remove-hooks"])
        assert result.exit_code == 0
        assert (wt / "cleanup_ran").exists()

    def test_requires_selector_from_main_repo(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees", "on_remove": ["echo bye"]})
        result = runner.invoke(app, ["remove-hooks"])
        assert result.exit_code != 0
        assert "exactly one" in result.output.lower()

    def test_unknown_branch_errors(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees", "on_remove": ["echo bye"]})
        result = runner.invoke(app, ["remove-hooks", "--branch", "no-such-branch"])
        assert result.exit_code != 0
        assert "no worktree found" in result.output.lower()


class TestList:
    def test_list_shows_worktrees(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees"})
        repo = Repo(tmp_git_repo)
        repo.create_head("test-branch")
        runner.invoke(app, ["add", "test-branch"])
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "test-branch" in result.output


class TestCd:
    def test_cd_prints_path(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees"})
        repo = Repo(tmp_git_repo)
        repo.create_head("test-branch")
        runner.invoke(app, ["add", "test-branch"])
        result = runner.invoke(app, ["cd", "test-branch"])
        assert result.exit_code == 0
        assert ".worktrees" in result.output
        assert "test-branch" in result.output


class TestRun:
    @pytest.fixture()
    def capture_execvpe(self, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[str], dict[str, str]]]:
        captured: list[tuple[str, list[str], dict[str, str]]] = []

        def fake_execvpe(file: str, args: list[str], env: dict[str, str]) -> None:
            captured.append((file, args, env))

        monkeypatch.setattr("os.execvpe", fake_execvpe)
        return captured

    def test_run_missing_branch_from_root_errors(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"commands": {"setup": "echo hi"}})
        result = runner.invoke(app, ["run", "setup"])
        assert result.exit_code != 0
        assert "branch" in result.output.lower()

    def test_run_unknown_command_errors(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees", "commands": {"setup": "echo hi"}})
        repo = Repo(tmp_git_repo)
        repo.create_head("test-branch")
        runner.invoke(app, ["add", "test-branch"])
        result = runner.invoke(app, ["run", "nonexistent", "--branch", "test-branch"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_run_forwards_extra_args(
        self,
        tmp_git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capture_execvpe: list[tuple[str, list[str], dict[str, str]]],
    ) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees", "commands": {"greet": "echo $1"}})
        repo = Repo(tmp_git_repo)
        repo.create_head("test-branch")
        runner.invoke(app, ["add", "test-branch"])

        runner.invoke(app, ["run", "greet", "--branch", "test-branch", "--", "hello", "world"])

        assert len(capture_execvpe) == 1
        file, args, _env = capture_execvpe[0]
        assert file == "bash"
        assert args == ["bash", "-c", "echo $1", "_", "hello", "world"]

    def test_run_no_extra_args_uses_bash(
        self,
        tmp_git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capture_execvpe: list[tuple[str, list[str], dict[str, str]]],
    ) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees", "commands": {"setup": "echo hi"}})
        repo = Repo(tmp_git_repo)
        repo.create_head("test-branch")
        runner.invoke(app, ["add", "test-branch"])

        runner.invoke(app, ["run", "setup", "--branch", "test-branch"])

        assert len(capture_execvpe) == 1
        file, args, _env = capture_execvpe[0]
        assert file == "bash"
        assert args == ["bash", "-c", "echo hi", "_"]

    def test_run_option_like_extra_args_not_intercepted(
        self,
        tmp_git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capture_execvpe: list[tuple[str, list[str], dict[str, str]]],
    ) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {"worktrees_root": ".worktrees", "commands": {"cmd": "echo $@"}})
        repo = Repo(tmp_git_repo)
        repo.create_head("test-branch")
        runner.invoke(app, ["add", "test-branch"])

        runner.invoke(app, ["run", "cmd", "--branch", "test-branch", "--", "--help", "--verbose"])

        assert len(capture_execvpe) == 1
        file, args, _env = capture_execvpe[0]
        assert file == "bash"
        assert args == ["bash", "-c", "echo $@", "_", "--help", "--verbose"]


class TestCompleteShell:
    def test_returns_matching_shells(self) -> None:
        from gwt.cli import _complete_shell

        assert _complete_shell("b") == ["bash"]
        assert _complete_shell("z") == ["zsh"]
        assert set(_complete_shell("")) == {"bash", "zsh"}

    def test_no_match_returns_empty(self) -> None:
        from gwt.cli import _complete_shell

        assert _complete_shell("fish") == []


class TestShellInit:
    def test_shell_init_bash(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {})
        result = runner.invoke(app, ["shell-init", "bash"])
        assert result.exit_code == 0
        assert "gwt_cd" in result.output

    def test_shell_init_unsupported(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_git_repo)
        write_config(tmp_git_repo, {})
        result = runner.invoke(app, ["shell-init", "fish"])
        assert result.exit_code != 0
