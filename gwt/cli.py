from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, NoReturn

import click
import questionary
import typer

from gwt.config import (
    DEFAULT_WORKTREES_ROOT,
    GWT_CONFIG_FILE,
    GWT_LOCAL_CONFIG_FILE,
    WORKTREEINCLUDE_FILE,
    WORKTREEINCLUDE_LOCAL_FILE,
    default_config_content,
    default_local_config_content,
    default_worktreeinclude_content,
    default_worktreeinclude_local_content,
    load_config,
)
from gwt.context import RepoContext, detect_context
from gwt.shell import SUPPORTED_SHELLS, generate_shell_init
from gwt.sync import sync_files
from gwt.worktree import (
    WorktreeInfo,
    add_worktree,
    build_env_vars,
    find_worktree_by_branch,
    find_worktree_by_path,
    is_worktree_dirty,
    list_available_branches,
    list_worktrees,
    remove_worktree,
    run_hooks,
)


def _complete_add_branch(incomplete: str) -> list[str]:
    try:
        ctx = detect_context(Path.cwd())
        return [b for b in list_available_branches(ctx.repo_root) if b.startswith(incomplete)]
    except Exception:
        return []


def _complete_branch(incomplete: str) -> list[str]:
    try:
        ctx = detect_context(Path.cwd())
        worktrees = list_worktrees(ctx.repo_root)
        return [wt.branch for wt in worktrees if wt.branch and wt.branch.startswith(incomplete)]
    except Exception:
        return []


def _complete_worktree_dir(incomplete: str) -> list[str]:
    try:
        ctx = detect_context(Path.cwd())
        return [str(wt.path) for wt in list_worktrees(ctx.repo_root) if str(wt.path).startswith(incomplete)]
    except Exception:
        return []


def _complete_run_command(incomplete: str) -> list[str]:
    try:
        ctx = detect_context(Path.cwd())
        config = load_config(ctx.repo_root)
        return [cmd for cmd in config.commands if cmd.startswith(incomplete)]
    except Exception:
        return []


def _complete_shell(incomplete: str) -> list[str]:
    return [s for s in SUPPORTED_SHELLS if s.startswith(incomplete)]


app = typer.Typer(
    name="gwt",
    help="Git Worktree Manager — automated file syncing, hooks, and commands for git worktrees.",
    add_completion=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"gwt {version('gwt')}")
        raise typer.Exit()


@app.callback()
def _main(
    _version: bool = typer.Option(
        None, "--version", callback=_version_callback, is_eager=True, help="Show version and exit."
    ),
) -> None:
    pass


def _handle_error(msg: str) -> NoReturn:
    typer.echo(f"Error: {msg}", err=True)
    raise typer.Exit(code=1)


def _locate_worktree(repo_root: Path, branch: str | None, worktree_dir: str | None) -> WorktreeInfo:
    """Resolve a worktree from exactly one of --branch / --worktree-dir, or exit with an error."""
    if (branch is None) == (worktree_dir is None):
        _handle_error("Specify exactly one of --branch or --worktree-dir.")

    if branch is not None:
        wt_info = find_worktree_by_branch(repo_root, branch)
        if wt_info is None:
            _handle_error(f"No worktree found for branch '{branch}'.")
    else:
        assert worktree_dir is not None
        wt_info = find_worktree_by_path(repo_root, Path(worktree_dir))
        if wt_info is None:
            _handle_error(f"No worktree registered at path '{worktree_dir}'.")
    return wt_info


def _warn_missing_config(ctx: RepoContext) -> None:
    """Warn (but don't fail) when neither a config nor a worktreeinclude file is present.

    Config is optional when a worktreeinclude file is present; worktrees_root then falls
    back to the default silently, since that setup is deliberate and not worth a warning.
    """
    if ctx.has_config or ctx.has_worktreeinclude:
        return
    typer.echo(
        f"Warning: neither {GWT_CONFIG_FILE} nor {WORKTREEINCLUDE_FILE} is present; "
        "at least one of them should be present.",
        err=True,
    )


@dataclass(frozen=True)
class _InitFile:
    """One file `gwt init` can create, as offered in the interactive checkbox."""

    path: str
    description: str
    content: Callable[[], str]
    default: bool


_INIT_FILES: tuple[_InitFile, ...] = (
    _InitFile(GWT_CONFIG_FILE, "shared config, commit this", default_config_content, True),
    _InitFile(GWT_LOCAL_CONFIG_FILE, "personal overrides, gitignored", default_local_config_content, False),
    _InitFile(WORKTREEINCLUDE_FILE, "gitignored files to copy, commit this", default_worktreeinclude_content, True),
    _InitFile(
        WORKTREEINCLUDE_LOCAL_FILE,
        "personal files to copy, gitignored",
        default_worktreeinclude_local_content,
        False,
    ),
)


def _is_interactive() -> bool:
    """Whether stdin and stdout are both attached to a terminal."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def _select_init_files(candidates: list[_InitFile], assume_yes: bool) -> list[_InitFile]:
    """Ask which files to create. Falls back to the defaults without a usable terminal."""
    defaults = [f for f in candidates if f.default]
    if assume_yes or not _is_interactive():
        return defaults

    width = max(len(f.path) for f in candidates)
    choices = [
        questionary.Choice(f"{f.path.ljust(width)}  {f.description}", value=f.path, checked=f.default)
        for f in candidates
    ]
    answer = questionary.checkbox("Which files should gwt create?", choices=choices).ask()
    if answer is None:  # Ctrl-C / Ctrl-D
        raise typer.Abort()
    return [f for f in candidates if f.path in answer]


@app.command()
def init(
    assume_yes: bool = typer.Option(False, "--yes", "-y", help="Skip the prompt and create the default set of files"),
) -> None:
    """Initialize GWT in the current git repository."""
    cwd = Path.cwd()
    try:
        ctx = detect_context(cwd)
    except ValueError:
        _handle_error("Not a git repository. Run 'gwt init' from a git repo root.")
        return

    if not ctx.is_main_repo:
        _handle_error("Must run 'gwt init' from the repo root, not a worktree branch.")
        return

    candidates = [f for f in _INIT_FILES if not (ctx.repo_root / f.path).exists()]
    for existing_file in (f for f in _INIT_FILES if f not in candidates):
        typer.echo(f"{existing_file.path} already exists, skipping")
    if not candidates:
        _handle_error("Nothing left to create. Already initialized.")
        return

    selected = _select_init_files(candidates, assume_yes)
    if not selected:
        typer.echo("Nothing selected; no files created.")
        return

    for init_file in selected:
        path = ctx.repo_root / init_file.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(init_file.content())
        typer.echo(f"Created {init_file.path}")

    # Gitignore the personal files and the worktrees dir (shared config stays committed)
    gitignore_path = ctx.repo_root / ".gitignore"
    entries_to_add = [GWT_LOCAL_CONFIG_FILE, WORKTREEINCLUDE_LOCAL_FILE, f"{DEFAULT_WORKTREES_ROOT}/"]
    existing = gitignore_path.read_text() if gitignore_path.exists() else ""
    lines_to_add = [entry for entry in entries_to_add if entry not in existing.splitlines()]
    if lines_to_add:
        with open(gitignore_path, "a") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            for line in lines_to_add:
                f.write(f"{line}\n")
        typer.echo("Updated .gitignore")


@app.command()
def add(
    branch: str = typer.Argument(help="Branch name to create worktree for", autocompletion=_complete_add_branch),
    force_sync: bool = typer.Option(False, "--force-sync", help="Overwrite existing files during sync"),
) -> None:
    """Create a worktree for the given branch."""
    cwd = Path.cwd()
    try:
        ctx = detect_context(cwd)
    except ValueError as e:
        _handle_error(str(e))
        return

    if not ctx.is_main_repo:
        _handle_error("Must run 'gwt add' from the repo root, not a worktree branch.")
        return

    _warn_missing_config(ctx)

    config = load_config(ctx.repo_root)

    try:
        wt_path = add_worktree(config, ctx.repo_root, branch, force_sync=force_sync)
    except ValueError as e:
        _handle_error(str(e))
        return

    # Run on_create hooks
    if config.on_create:
        env = build_env_vars(ctx.repo_root, wt_path, branch)
        try:
            run_hooks(config.on_create, wt_path, env)
        except RuntimeError as e:
            typer.echo(f"Warning: {e}", err=True)

    typer.echo(f"Created worktree for '{branch}' at {wt_path}")


@app.command()
def sync(
    branch: str | None = typer.Option(
        None, "--branch", "-b", help="Branch name of the worktree to sync", autocompletion=_complete_branch
    ),
    worktree_dir: str | None = typer.Option(
        None,
        "--worktree-dir",
        "-d",
        help="Path to the worktree to sync (absolute, ~-prefixed, or relative to the cwd)",
        autocompletion=_complete_worktree_dir,
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files during sync"),
    run_create_hooks: bool = typer.Option(False, "--run-hooks", help="Also run on_create hooks after syncing"),
    only_hooks: bool = typer.Option(False, "--only-hooks", help="Skip file sync; run on_create hooks only"),
) -> None:
    """Sync files into an existing worktree, located by branch or path.

    Useful for worktrees created by other tools (and possibly outside worktrees_root).
    """
    cwd = Path.cwd()
    try:
        ctx = detect_context(cwd)
    except ValueError as e:
        _handle_error(str(e))
        return

    _warn_missing_config(ctx)

    config = load_config(ctx.repo_root)

    if ctx.is_worktree and branch is None and worktree_dir is None:
        assert ctx.worktree_path is not None
        wt_info = find_worktree_by_path(ctx.repo_root, ctx.worktree_path)
        if wt_info is None:
            _handle_error("Cannot locate current worktree in git's worktree list.")
    else:
        wt_info = _locate_worktree(ctx.repo_root, branch, worktree_dir)

    if only_hooks and force:
        _handle_error("--only-hooks and --force are mutually exclusive.")

    if not only_hooks:
        result = sync_files(config, ctx.repo_root, wt_info.path, force=force)
        typer.echo(
            f"Synced into {wt_info.path}: {result.copied} copied, {result.linked} linked, {result.skipped} skipped"
        )

    if (run_create_hooks or only_hooks) and config.on_create:
        if wt_info.branch is None:
            typer.echo("Warning: worktree is in detached HEAD; skipping on_create hooks.", err=True)
            return
        env = build_env_vars(ctx.repo_root, wt_info.path, wt_info.branch)
        try:
            run_hooks(config.on_create, wt_info.path, env)
        except RuntimeError as e:
            typer.echo(f"Warning: {e}", err=True)


@app.command(name="remove-hooks")
def remove_hooks(
    branch: str | None = typer.Option(
        None,
        "--branch",
        "-b",
        help="Branch name of the worktree to run on_remove hooks for",
        autocompletion=_complete_branch,
    ),
    worktree_dir: str | None = typer.Option(
        None,
        "--worktree-dir",
        "-d",
        help="Path to the worktree to run on_remove hooks for (absolute, ~-prefixed, or relative to the cwd)",
        autocompletion=_complete_worktree_dir,
    ),
) -> None:
    """Run on_remove hooks for a worktree, located by branch or path.

    For tools that remove worktrees themselves but allow a custom cleanup script.
    Run this while the worktree still exists (before the external tool deletes it).
    """
    cwd = Path.cwd()
    try:
        ctx = detect_context(cwd)
    except ValueError as e:
        _handle_error(str(e))

    _warn_missing_config(ctx)

    config = load_config(ctx.repo_root)

    if ctx.is_worktree and branch is None and worktree_dir is None:
        assert ctx.worktree_path is not None
        wt_info = find_worktree_by_path(ctx.repo_root, ctx.worktree_path)
        if wt_info is None:
            _handle_error("Cannot locate current worktree in git's worktree list.")
    else:
        wt_info = _locate_worktree(ctx.repo_root, branch, worktree_dir)

    if not config.on_remove:
        typer.echo("No on_remove hooks configured.")
        return

    if wt_info.branch is None:
        _handle_error("Worktree is in detached HEAD; cannot run on_remove hooks without a branch.")

    env = build_env_vars(ctx.repo_root, wt_info.path, wt_info.branch)
    try:
        run_hooks(config.on_remove, wt_info.path, env)
    except RuntimeError as e:
        typer.echo(f"Warning: {e}", err=True)


@app.command()
def remove(
    branch: str = typer.Argument(help="Branch name of worktree to remove", autocompletion=_complete_branch),
    force: bool = typer.Option(False, "--force", help="Force removal even if worktree is dirty"),
) -> None:
    """Remove a worktree for the given branch."""
    cwd = Path.cwd()
    try:
        ctx = detect_context(cwd)
    except ValueError as e:
        _handle_error(str(e))
        return

    if not ctx.is_main_repo:
        _handle_error("Must run 'gwt remove' from the repo root, not a worktree branch.")
        return

    _warn_missing_config(ctx)

    config = load_config(ctx.repo_root)

    wt_info = find_worktree_by_branch(ctx.repo_root, branch)
    if wt_info is None:
        _handle_error(f"No worktree found for branch '{branch}'.")
        return

    if not force and is_worktree_dirty(wt_info.path):
        confirm = typer.confirm(f"Worktree for '{branch}' has uncommitted changes. Remove anyway?")
        if not confirm:
            raise typer.Abort()

    # Run on_remove hooks
    if config.on_remove:
        env = build_env_vars(ctx.repo_root, wt_info.path, branch)
        try:
            run_hooks(config.on_remove, wt_info.path, env)
        except RuntimeError as e:
            typer.echo(f"Warning: on_remove hook failed: {e}", err=True)

    try:
        remove_worktree(ctx.repo_root, branch, force=force)
    except Exception as e:
        _handle_error(f"Failed to remove worktree: {e}")
        return

    typer.echo(f"Removed worktree for '{branch}'")


@app.command(name="list")
def list_cmd() -> None:
    """List all worktrees."""
    cwd = Path.cwd()
    try:
        ctx = detect_context(cwd)
    except ValueError as e:
        _handle_error(str(e))
        return

    _warn_missing_config(ctx)

    worktrees = list_worktrees(ctx.repo_root)
    for wt in worktrees:
        branch_name = wt.branch or "(detached)"
        typer.echo(f"{branch_name}\t{wt.path}")


@app.command()
def cd(
    branch: str = typer.Argument(help="Branch name of worktree to navigate to", autocompletion=_complete_branch),
) -> None:
    """Print worktree path for shell cd wrapper."""
    cwd = Path.cwd()
    try:
        ctx = detect_context(cwd)
    except ValueError as e:
        _handle_error(str(e))
        return

    _warn_missing_config(ctx)

    wt_info = find_worktree_by_branch(ctx.repo_root, branch)
    if wt_info is None:
        _handle_error(f"No worktree found for branch '{branch}'.")
        return

    typer.echo(str(wt_info.path))


@app.command(context_settings={"ignore_unknown_options": True})
def run(
    command: str = typer.Argument(help="Named command from config to run", autocompletion=_complete_run_command),
    branch: str | None = typer.Option(
        None, "--branch", "-b", help="Branch worktree to run in", autocompletion=_complete_branch
    ),
    extra_args: Annotated[list[str] | None, typer.Argument(click_type=click.UNPROCESSED)] = None,
) -> None:
    """Run a named command from config in a worktree."""
    cwd = Path.cwd()
    try:
        ctx = detect_context(cwd)
    except ValueError as e:
        _handle_error(str(e))
        return

    _warn_missing_config(ctx)

    config = load_config(ctx.repo_root)

    # Determine target branch and worktree
    if ctx.is_worktree:
        if branch is not None:
            _handle_error("Cannot use --branch from within a worktree. The current branch is used automatically.")
            return
        target_branch = ctx.branch
        if target_branch is None:
            _handle_error("Cannot determine branch (detached HEAD).")
            return
        wt_path = ctx.worktree_path
        assert wt_path is not None
    else:
        if branch is None:
            _handle_error("--branch is required when running from the repo root.")
            return
        target_branch = branch
        wt_info = find_worktree_by_branch(ctx.repo_root, branch)
        if wt_info is None:
            _handle_error(f"No worktree found for branch '{branch}'.")
            return
        wt_path = wt_info.path

    if command not in config.commands:
        available = ", ".join(config.commands.keys()) if config.commands else "(none defined)"
        _handle_error(f"Command '{command}' not found in config. Available: {available}")
        return

    cmd_string = config.commands[command]
    env = build_env_vars(ctx.repo_root, wt_path, target_branch)

    # Replace the process for full terminal control
    os.chdir(wt_path)
    # "_" is a placeholder for $0; extra args become $1, $2, $@, etc.
    args = extra_args or []
    os.execvpe("bash", ["bash", "-c", cmd_string, "_", *args], env)


@app.command(name="shell-init")
def shell_init(
    shell: str = typer.Argument(help="Shell type (bash or zsh)", autocompletion=_complete_shell),
) -> None:
    """Output shell integration snippet for cd wrapper and completions."""
    cwd = Path.cwd()
    try:
        ctx = detect_context(cwd)
    except ValueError as e:
        _handle_error(str(e))
        return

    _warn_missing_config(ctx)

    try:
        output = generate_shell_init(shell)
    except ValueError as e:
        _handle_error(str(e))
        return

    typer.echo(output)
