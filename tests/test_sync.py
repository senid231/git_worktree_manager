from __future__ import annotations

from pathlib import Path

import pytest
from git import Repo

from gwt.config import GwtConfig
from gwt.sync import sync_files


class TestSyncCopy:
    def test_copy_file(self, tmp_git_repo: Path) -> None:
        (tmp_git_repo / ".env").write_text("SECRET=123")
        wt_path = tmp_git_repo / ".worktrees" / "test"
        wt_path.mkdir(parents=True)
        config = GwtConfig(copy=[".env"])
        result = sync_files(config, tmp_git_repo, wt_path, force=False)
        assert (wt_path / ".env").read_text() == "SECRET=123"
        assert result.copied == 1

    def test_copy_directory(self, tmp_git_repo: Path) -> None:
        config_dir = tmp_git_repo / "config"
        config_dir.mkdir()
        (config_dir / "app.yml").write_text("key: val")
        wt_path = tmp_git_repo / ".worktrees" / "test"
        wt_path.mkdir(parents=True)
        config = GwtConfig(copy=["config"])
        result = sync_files(config, tmp_git_repo, wt_path, force=False)
        assert (wt_path / "config" / "app.yml").read_text() == "key: val"
        assert result.copied == 1

    def test_copy_glob(self, tmp_git_repo: Path) -> None:
        config_dir = tmp_git_repo / "config"
        config_dir.mkdir()
        (config_dir / "app.yml").write_text("a")
        (config_dir / "db.yml").write_text("b")
        (config_dir / "readme.txt").write_text("c")
        wt_path = tmp_git_repo / ".worktrees" / "test"
        wt_path.mkdir(parents=True)
        config = GwtConfig(copy=["config/*.yml"])
        result = sync_files(config, tmp_git_repo, wt_path, force=False)
        assert (wt_path / "config" / "app.yml").exists()
        assert (wt_path / "config" / "db.yml").exists()
        assert not (wt_path / "config" / "readme.txt").exists()
        assert result.copied == 2

    def test_skip_copy(self, tmp_git_repo: Path) -> None:
        tmp_dir = tmp_git_repo / "tmp"
        tmp_dir.mkdir()
        (tmp_dir / "keep.txt").write_text("keep")
        (tmp_dir / "ignore.txt").write_text("ignore")
        wt_path = tmp_git_repo / ".worktrees" / "test"
        wt_path.mkdir(parents=True)
        config = GwtConfig(copy=["tmp/*"], skip_copy=["tmp/ignore.txt"])
        sync_files(config, tmp_git_repo, wt_path, force=False)
        assert (wt_path / "tmp" / "keep.txt").exists()
        assert not (wt_path / "tmp" / "ignore.txt").exists()

    def test_copy_skips_existing_without_force(self, tmp_git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        (tmp_git_repo / ".env").write_text("original")
        wt_path = tmp_git_repo / ".worktrees" / "test"
        wt_path.mkdir(parents=True)
        (wt_path / ".env").write_text("existing")
        config = GwtConfig(copy=[".env"])
        sync_files(config, tmp_git_repo, wt_path, force=False)
        assert (wt_path / ".env").read_text() == "existing"
        captured = capsys.readouterr()
        assert "warning" in captured.err.lower() or "skip" in captured.err.lower()

    def test_copy_overwrites_with_force(self, tmp_git_repo: Path) -> None:
        (tmp_git_repo / ".env").write_text("original")
        wt_path = tmp_git_repo / ".worktrees" / "test"
        wt_path.mkdir(parents=True)
        (wt_path / ".env").write_text("existing")
        config = GwtConfig(copy=[".env"])
        sync_files(config, tmp_git_repo, wt_path, force=True)
        assert (wt_path / ".env").read_text() == "original"


class TestSyncLink:
    def test_symlink_file(self, tmp_git_repo: Path) -> None:
        (tmp_git_repo / ".env").write_text("SECRET=123")
        wt_path = tmp_git_repo / ".worktrees" / "test"
        wt_path.mkdir(parents=True)
        config = GwtConfig(link=[".env"])
        result = sync_files(config, tmp_git_repo, wt_path, force=False)
        link = wt_path / ".env"
        assert link.is_symlink()
        assert link.resolve() == (tmp_git_repo / ".env").resolve()
        assert result.linked == 1

    def test_symlink_directory(self, tmp_git_repo: Path) -> None:
        nm = tmp_git_repo / "node_modules"
        nm.mkdir()
        (nm / "pkg.json").write_text("{}")
        wt_path = tmp_git_repo / ".worktrees" / "test"
        wt_path.mkdir(parents=True)
        config = GwtConfig(link=["node_modules"])
        sync_files(config, tmp_git_repo, wt_path, force=False)
        link = wt_path / "node_modules"
        assert link.is_symlink()
        assert (link / "pkg.json").read_text() == "{}"

    def test_skip_link(self, tmp_git_repo: Path) -> None:
        vendor = tmp_git_repo / "vendor" / "bundle"
        vendor.mkdir(parents=True)
        cache = vendor / "cache"
        cache.mkdir()
        wt_path = tmp_git_repo / ".worktrees" / "test"
        wt_path.mkdir(parents=True)
        config = GwtConfig(link=["vendor/bundle", "vendor/bundle/cache"], skip_link=["vendor/bundle/cache"])
        sync_files(config, tmp_git_repo, wt_path, force=False)
        assert (wt_path / "vendor" / "bundle").is_symlink()
        assert not (wt_path / "vendor" / "bundle" / "cache").is_symlink()


class TestSyncEdgeCases:
    def test_glob_matches_nothing_warns(self, tmp_git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        wt_path = tmp_git_repo / ".worktrees" / "test"
        wt_path.mkdir(parents=True)
        config = GwtConfig(copy=["nonexistent/*.xyz"])
        sync_files(config, tmp_git_repo, wt_path, force=False)
        captured = capsys.readouterr()
        assert "warning" in captured.err.lower() or "no matches" in captured.err.lower()

    def test_creates_parent_directories(self, tmp_git_repo: Path) -> None:
        nested = tmp_git_repo / "deep" / "nested"
        nested.mkdir(parents=True)
        (nested / "file.txt").write_text("hello")
        wt_path = tmp_git_repo / ".worktrees" / "test"
        wt_path.mkdir(parents=True)
        config = GwtConfig(copy=["deep/nested/file.txt"])
        sync_files(config, tmp_git_repo, wt_path, force=False)
        assert (wt_path / "deep" / "nested" / "file.txt").read_text() == "hello"


class TestWorktreeInclude:
    """`.worktreeinclude`: copy the intersection of (matched patterns) and (git-ignored)."""

    @staticmethod
    def _wt(repo: Path) -> Path:
        wt_path = repo / ".worktrees" / "test"
        wt_path.mkdir(parents=True)
        return wt_path

    def test_copies_ignored_file_matching_pattern(self, tmp_git_repo: Path) -> None:
        (tmp_git_repo / ".gitignore").write_text(".env\n")
        (tmp_git_repo / ".env").write_text("SECRET=1")
        (tmp_git_repo / ".worktreeinclude").write_text(".env\n")
        wt_path = self._wt(tmp_git_repo)
        result = sync_files(GwtConfig(), tmp_git_repo, wt_path, force=False)
        assert (wt_path / ".env").read_text() == "SECRET=1"
        assert result.copied == 1

    def test_skips_tracked_file_even_if_listed(self, tmp_git_repo: Path) -> None:
        (tmp_git_repo / "tracked.txt").write_text("x")
        repo = Repo(tmp_git_repo)
        repo.index.add(["tracked.txt"])
        repo.index.commit("add tracked")
        (tmp_git_repo / ".worktreeinclude").write_text("tracked.txt\n")
        wt_path = self._wt(tmp_git_repo)
        result = sync_files(GwtConfig(), tmp_git_repo, wt_path, force=False)
        assert not (wt_path / "tracked.txt").exists()
        assert result.copied == 0

    def test_skips_untracked_non_ignored_file_with_warning(
        self, tmp_git_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_git_repo / "stray.txt").write_text("x")  # neither tracked nor ignored
        (tmp_git_repo / ".worktreeinclude").write_text("stray.txt\n")
        wt_path = self._wt(tmp_git_repo)
        result = sync_files(GwtConfig(), tmp_git_repo, wt_path, force=False)
        assert not (wt_path / "stray.txt").exists()
        assert result.copied == 0
        assert result.warnings >= 1
        assert "does not ignore" in capsys.readouterr().err.lower()

    def test_negation_excludes_match(self, tmp_git_repo: Path) -> None:
        (tmp_git_repo / ".gitignore").write_text("*.local\n")
        (tmp_git_repo / "a.local").write_text("a")
        (tmp_git_repo / "b.local").write_text("b")
        (tmp_git_repo / ".worktreeinclude").write_text("*.local\n!b.local\n")
        wt_path = self._wt(tmp_git_repo)
        sync_files(GwtConfig(), tmp_git_repo, wt_path, force=False)
        assert (wt_path / "a.local").exists()
        assert not (wt_path / "b.local").exists()

    def test_directory_pattern_enumerates_files(self, tmp_git_repo: Path) -> None:
        (tmp_git_repo / ".gitignore").write_text("cache/\n")
        cache = tmp_git_repo / "cache"
        cache.mkdir()
        (cache / "a.txt").write_text("a")
        (cache / "b.txt").write_text("b")
        (tmp_git_repo / ".worktreeinclude").write_text("cache/\n")
        wt_path = self._wt(tmp_git_repo)
        sync_files(GwtConfig(), tmp_git_repo, wt_path, force=False)
        assert (wt_path / "cache" / "a.txt").read_text() == "a"
        assert (wt_path / "cache" / "b.txt").read_text() == "b"

    def test_comments_and_blank_lines_ignored(self, tmp_git_repo: Path) -> None:
        (tmp_git_repo / ".gitignore").write_text(".env\n")
        (tmp_git_repo / ".env").write_text("s")
        (tmp_git_repo / ".worktreeinclude").write_text("# secrets\n\n.env\n")
        wt_path = self._wt(tmp_git_repo)
        result = sync_files(GwtConfig(), tmp_git_repo, wt_path, force=False)
        assert (wt_path / ".env").exists()
        assert result.copied == 1

    def test_local_file_alone_is_honored(self, tmp_git_repo: Path) -> None:
        (tmp_git_repo / ".gitignore").write_text(".env.local\n")
        (tmp_git_repo / ".env.local").write_text("LOCAL=1")
        (tmp_git_repo / ".worktreeinclude.local").write_text(".env.local\n")
        wt_path = self._wt(tmp_git_repo)
        result = sync_files(GwtConfig(), tmp_git_repo, wt_path, force=False)
        assert (wt_path / ".env.local").read_text() == "LOCAL=1"
        assert result.copied == 1

    def test_local_file_adds_to_shared_patterns(self, tmp_git_repo: Path) -> None:
        (tmp_git_repo / ".gitignore").write_text(".env\n.env.local\n")
        (tmp_git_repo / ".env").write_text("shared")
        (tmp_git_repo / ".env.local").write_text("personal")
        (tmp_git_repo / ".worktreeinclude").write_text(".env\n")
        (tmp_git_repo / ".worktreeinclude.local").write_text(".env.local\n")
        wt_path = self._wt(tmp_git_repo)
        result = sync_files(GwtConfig(), tmp_git_repo, wt_path, force=False)
        assert (wt_path / ".env").read_text() == "shared"
        assert (wt_path / ".env.local").read_text() == "personal"
        assert result.copied == 2

    def test_local_file_negates_shared_pattern(self, tmp_git_repo: Path) -> None:
        (tmp_git_repo / ".gitignore").write_text("*.secret\n")
        (tmp_git_repo / "a.secret").write_text("a")
        (tmp_git_repo / "b.secret").write_text("b")
        (tmp_git_repo / ".worktreeinclude").write_text("*.secret\n")
        # The local file is read last, so its negation wins over the shared pattern.
        (tmp_git_repo / ".worktreeinclude.local").write_text("!b.secret\n")
        wt_path = self._wt(tmp_git_repo)
        sync_files(GwtConfig(), tmp_git_repo, wt_path, force=False)
        assert (wt_path / "a.secret").exists()
        assert not (wt_path / "b.secret").exists()

    def test_supplements_config_copy(self, tmp_git_repo: Path) -> None:
        (tmp_git_repo / "plain.txt").write_text("p")  # non-ignored, via config.copy
        (tmp_git_repo / ".gitignore").write_text(".env\n")
        (tmp_git_repo / ".env").write_text("s")  # ignored, via .worktreeinclude
        (tmp_git_repo / ".worktreeinclude").write_text(".env\n")
        wt_path = self._wt(tmp_git_repo)
        result = sync_files(GwtConfig(copy=["plain.txt"]), tmp_git_repo, wt_path, force=False)
        assert (wt_path / "plain.txt").exists()
        assert (wt_path / ".env").exists()
        assert result.copied == 2

    def test_skip_copy_still_applies(self, tmp_git_repo: Path) -> None:
        (tmp_git_repo / ".gitignore").write_text("*.secret\n")
        (tmp_git_repo / "a.secret").write_text("a")
        (tmp_git_repo / "b.secret").write_text("b")
        (tmp_git_repo / ".worktreeinclude").write_text("*.secret\n")
        wt_path = self._wt(tmp_git_repo)
        sync_files(GwtConfig(skip_copy=["b.secret"]), tmp_git_repo, wt_path, force=False)
        assert (wt_path / "a.secret").exists()
        assert not (wt_path / "b.secret").exists()

    def test_no_file_is_noop(self, tmp_git_repo: Path) -> None:
        (tmp_git_repo / ".gitignore").write_text(".env\n")
        (tmp_git_repo / ".env").write_text("s")
        wt_path = self._wt(tmp_git_repo)
        result = sync_files(GwtConfig(), tmp_git_repo, wt_path, force=False)
        assert not (wt_path / ".env").exists()
        assert result.copied == 0
