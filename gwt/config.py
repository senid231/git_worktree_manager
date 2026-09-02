from __future__ import annotations

from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

GWT_CONFIG_FILE = ".gwt/config.yml"
GWT_LOCAL_CONFIG_FILE = ".gwt/config.local.yml"
DEFAULT_WORKTREES_ROOT = ".worktrees"
WORKTREEINCLUDE_FILE = ".worktreeinclude"
WORKTREEINCLUDE_LOCAL_FILE = ".worktreeinclude.local"

_LIST_FIELDS = ("copy", "link", "skip_copy", "skip_link", "on_create", "on_remove")
_SCALAR_FIELDS = ("worktrees_root",)
_MAP_FIELDS = ("commands",)


@dataclass
class GwtConfig:
    worktrees_root: str = DEFAULT_WORKTREES_ROOT
    copy: list[str] = field(default_factory=list)
    link: list[str] = field(default_factory=list)
    skip_copy: list[str] = field(default_factory=list)
    skip_link: list[str] = field(default_factory=list)
    on_create: list[str] = field(default_factory=list)
    on_remove: list[str] = field(default_factory=list)
    commands: dict[str, str] = field(default_factory=dict)


@dataclass
class ParsedConfig:
    """A validated config together with the set of keys explicitly present in the YAML."""

    config: GwtConfig
    explicit_keys: set[str]


def validate_config(raw: dict[str, Any], source: Path) -> ParsedConfig:
    """Validate raw YAML dict and return a ParsedConfig. Raises on invalid values."""
    kwargs: dict[str, Any] = {}
    explicit: set[str] = set()

    if "worktrees_root" in raw:
        val = raw["worktrees_root"]
        if not isinstance(val, str):
            raise TypeError(f"worktrees_root must be a string in {source}")
        if not val:
            raise ValueError(f"worktrees_root must not be empty in {source}")
        if val.startswith("/"):
            raise ValueError(f"worktrees_root must be a relative path in {source}")
        if ".." in Path(val).parts:
            raise ValueError(f"worktrees_root must not contain '..' in {source}")
        kwargs["worktrees_root"] = val
        explicit.add("worktrees_root")

    for key in _LIST_FIELDS:
        if key in raw:
            val = raw[key]
            if not isinstance(val, list):
                raise TypeError(f"{key} must be a list in {source}")
            if not all(isinstance(item, str) for item in val):
                raise TypeError(f"{key} items must be strings in {source}")
            kwargs[key] = val
            explicit.add(key)

    if "commands" in raw:
        val = raw["commands"]
        if not isinstance(val, dict):
            raise TypeError(f"commands must be a mapping in {source}")
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in val.items()):
            raise TypeError(f"commands keys and values must be strings in {source}")
        kwargs["commands"] = val
        explicit.add("commands")

    return ParsedConfig(config=GwtConfig(**kwargs), explicit_keys=explicit)


def merge_configs(base: ParsedConfig, local: ParsedConfig) -> GwtConfig:
    """Deep-merge local config on top of base config."""
    merged_kwargs: dict[str, Any] = {}

    # Scalars: local overrides base only if explicitly set in local YAML
    for key in _SCALAR_FIELDS:
        if key in local.explicit_keys:
            merged_kwargs[key] = getattr(local.config, key)
        else:
            merged_kwargs[key] = getattr(base.config, key)

    # Lists: concatenate (only explicitly set lists from local are appended)
    for key in _LIST_FIELDS:
        base_list: list[str] = getattr(base.config, key)
        local_list: list[str] = getattr(local.config, key) if key in local.explicit_keys else []
        merged_kwargs[key] = base_list + local_list

    # Maps: deep merge (only explicitly set maps from local are merged)
    for key in _MAP_FIELDS:
        base_map: dict[str, str] = getattr(base.config, key)
        local_map: dict[str, str] = getattr(local.config, key) if key in local.explicit_keys else {}
        merged_kwargs[key] = {**base_map, **local_map}

    return GwtConfig(**merged_kwargs)


def load_config(repo_root: Path) -> GwtConfig:
    """Load and merge .gwt/config.yml and optional .gwt/config.local.yml from repo root.

    A missing .gwt/config.yml is not an error: it falls back to defaults (so a repo with
    only a .worktreeinclude still works). Callers warn about the missing file.
    """
    config_path = repo_root / GWT_CONFIG_FILE
    if config_path.exists():
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}
        base = validate_config(raw, config_path)
    else:
        base = ParsedConfig(config=GwtConfig(), explicit_keys=set())

    local_path = repo_root / GWT_LOCAL_CONFIG_FILE
    if local_path.exists():
        with open(local_path) as f:
            local_raw = yaml.safe_load(f) or {}
        local = validate_config(local_raw, local_path)
        return merge_configs(base, local)

    return base.config


def _packaged_template(name: str) -> str:
    return str(files("gwt").joinpath(name).read_text(encoding="utf-8"))


def default_config_content() -> str:
    """Return the default .gwt/config.yml content (packaged as config.yml.example)."""
    return _packaged_template("config.yml.example")


def default_local_config_content() -> str:
    """Return the default .gwt/config.local.yml content."""
    return _packaged_template("config.local.yml.example")


def default_worktreeinclude_content() -> str:
    """Return the default .worktreeinclude content."""
    return _packaged_template("worktreeinclude.example")


def default_worktreeinclude_local_content() -> str:
    """Return the default .worktreeinclude.local content."""
    return _packaged_template("worktreeinclude.local.example")
