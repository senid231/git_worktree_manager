# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-09-02

First public release.

GWT is a Python CLI that automates git worktree setup:

- **Worktree management** — `gwt add`, `gwt remove`, `gwt list`, and `gwt sync` / `gwt remove-hooks` for
  worktrees created by other tools, including ones outside `worktrees_root`.
- **Hooks** — `on_create` and `on_remove` shell commands with `GWT_*` environment variables available.
- **Named commands** — `gwt run <name>` executes configured commands inside a worktree, with argument
  forwarding after `--`.
- **Shell integration** — `gwt shell-init bash|zsh` provides the `gcd` alias and tab completion.
- **File syncing** — copy or symlink files into each new worktree via glob patterns, with skip filters, plus
  support for repo-root `.worktreeinclude` (shared) and `.worktreeinclude.local` (personal, gitignored) files
  in gitignore syntax listing gitignored files to copy; the local file is read last and can negate shared
  patterns.
- **Layered config** — `.gwt/config.yml` (shared, committed) merged with `.gwt/config.local.yml` (personal,
  gitignored); both are optional when a worktreeinclude file is present. Worktrees default to `.worktrees`.
- **Interactive `gwt init`** — a checkbox prompt selects which of the four files to create, skipping ones that
  already exist; `--yes` or a non-interactive terminal creates the default set.
