from __future__ import annotations

import glob as globmod
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from gwt.config import WORKTREEINCLUDE_FILE, WORKTREEINCLUDE_LOCAL_FILE, GwtConfig


@dataclass
class SyncResult:
    copied: int = 0
    linked: int = 0
    skipped: int = 0
    warnings: int = 0


def _resolve_globs(patterns: list[str], root: Path) -> list[Path]:
    """Expand glob patterns against root directory, return sorted unique relative paths."""
    resolved: set[Path] = set()
    for pattern in patterns:
        matches = globmod.glob(pattern, root_dir=root, recursive=True)
        for match in matches:
            resolved.add(Path(match))
    return sorted(resolved)


def _matches_any(path: Path, skip_patterns: list[str], root: Path) -> bool:
    """Check if a path matches any of the skip glob patterns."""
    for pattern in skip_patterns:
        skip_matches = globmod.glob(pattern, root_dir=root, recursive=True)
        if str(path) in skip_matches:
            return True
    return False


def _warn(msg: str) -> None:
    print(f"Warning: {msg}", file=sys.stderr)


def _worktreeinclude_files(repo_root: Path) -> list[Path]:
    """Return the existing worktreeinclude files, shared first then personal.

    The personal ``.worktreeinclude.local`` is read after the shared file, so its patterns
    are applied last and can negate (``!``) entries from the shared one.
    """
    names = (WORKTREEINCLUDE_FILE, WORKTREEINCLUDE_LOCAL_FILE)
    return [repo_root / name for name in names if (repo_root / name).is_file()]


def _worktreeinclude_paths(repo_root: Path) -> tuple[list[Path], list[Path]]:
    """Resolve the worktreeinclude files into files to copy into a new worktree.

    Follows the established ``.worktreeinclude`` convention (satococoa/git-worktreeinclude,
    Conductor): copy files that are *both* matched by the gitignore-style patterns in the
    file *and* ignored by Git. Tracked files are already checked out by ``git worktree add``,
    and untracked files Git does not ignore are deliberately left out.

    The files live at the main repo root and use gitignore syntax (``#`` comments, blank
    lines, ``!`` negation, ``/`` anchors, ``**``). Returns ``(to_copy, matched_not_ignored)``;
    the second list drives a warning for patterns that match files Git would not ignore.
    """
    include_files = _worktreeinclude_files(repo_root)
    if not include_files:
        return [], []

    # Untracked files matching the patterns. ``--others`` drops tracked files; the patterns
    # get full gitignore semantics via ``--exclude-from``. ``-z`` survives odd filenames.
    ls = subprocess.run(
        [
            "git",
            "ls-files",
            "-z",
            "--others",
            "--ignored",
            *(f"--exclude-from={f}" for f in include_files),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if ls.returncode != 0:
        _warn(f"git ls-files failed for {WORKTREEINCLUDE_FILE}: {ls.stderr.strip()}")
        return [], []
    candidates = [Path(p) for p in ls.stdout.split("\0") if p]
    if not candidates:
        return [], []

    # Keep only files Git actually ignores, so a stray non-ignored match is not copied
    # (mirrors the reference implementations' "must be git-ignored" rule).
    check = subprocess.run(
        ["git", "check-ignore", "-z", "--stdin"],
        cwd=repo_root,
        input="\0".join(str(p) for p in candidates),
        capture_output=True,
        text=True,
    )
    if check.returncode not in (0, 1):  # 0=some ignored, 1=none ignored, >1=error
        _warn(f"git check-ignore failed for {WORKTREEINCLUDE_FILE}: {check.stderr.strip()}")
        return sorted(candidates), []
    ignored = {Path(p) for p in check.stdout.split("\0") if p}
    to_copy = sorted(p for p in candidates if p in ignored)
    not_ignored = sorted(p for p in candidates if p not in ignored)
    return to_copy, not_ignored


def sync_files(config: GwtConfig, repo_root: Path, wt_path: Path, force: bool) -> SyncResult:
    """Sync files from repo root to worktree based on config rules."""
    result = SyncResult()

    # Process copy patterns (config `copy` plus any `.worktreeinclude` entries)
    copy_paths = _resolve_globs(config.copy, repo_root)
    if config.copy and not copy_paths:
        _warn(f"copy patterns matched no files: {config.copy}")
        result.warnings += 1

    include_paths, include_not_ignored = _worktreeinclude_paths(repo_root)
    for rel_path in include_not_ignored:
        _warn(f"{WORKTREEINCLUDE_FILE} matched a file Git does not ignore, skipping: {rel_path}")
        result.warnings += 1

    for rel_path in sorted(set(copy_paths) | set(include_paths)):
        if _matches_any(rel_path, config.skip_copy, repo_root):
            continue
        src = repo_root / rel_path
        dst = wt_path / rel_path
        if not src.exists():
            _warn(f"source does not exist, skipping: {rel_path}")
            result.warnings += 1
            continue
        if dst.exists() or dst.is_symlink():
            if not force:
                _warn(f"target already exists, skipping: {rel_path}")
                result.skipped += 1
                continue
            if dst.is_dir() and not dst.is_symlink():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        result.copied += 1

    # Process link patterns
    link_paths = _resolve_globs(config.link, repo_root)
    if config.link and not link_paths:
        _warn(f"link patterns matched no files: {config.link}")
        result.warnings += 1

    for rel_path in link_paths:
        if _matches_any(rel_path, config.skip_link, repo_root):
            continue
        src = repo_root / rel_path
        dst = wt_path / rel_path
        if not src.exists():
            _warn(f"source does not exist, skipping: {rel_path}")
            result.warnings += 1
            continue
        if dst.exists() or dst.is_symlink():
            if not force:
                _warn(f"target already exists, skipping: {rel_path}")
                result.skipped += 1
                continue
            if dst.is_dir() and not dst.is_symlink():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(src.resolve(), dst)
        result.linked += 1

    return result
