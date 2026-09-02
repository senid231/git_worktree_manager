from __future__ import annotations

from pathlib import Path

import pytest

from gwt.config import (
    DEFAULT_WORKTREES_ROOT,
    GwtConfig,
    ParsedConfig,
    default_config_content,
    load_config,
    merge_configs,
    validate_config,
)
from tests.conftest import write_config


class TestValidateConfig:
    def test_empty_config_is_valid(self) -> None:
        parsed = validate_config({}, Path(".gwt/config.yml"))
        assert parsed.config.worktrees_root == ".worktrees"
        assert parsed.explicit_keys == set()

    def test_valid_full_config(self) -> None:
        raw = {
            "worktrees_root": ".wt",
            "copy": [".env"],
            "link": ["node_modules"],
            "skip_copy": ["tmp/x"],
            "skip_link": [],
            "on_create": ["echo hi"],
            "on_remove": ["echo bye"],
            "commands": {"setup": "npm install"},
        }
        parsed = validate_config(raw, Path(".gwt/config.yml"))
        assert parsed.config.worktrees_root == ".wt"
        assert parsed.config.copy == [".env"]
        assert parsed.config.commands == {"setup": "npm install"}
        assert "worktrees_root" in parsed.explicit_keys

    def test_worktrees_root_rejects_absolute_path(self) -> None:
        with pytest.raises(ValueError, match="worktrees_root"):
            validate_config({"worktrees_root": "/absolute"}, Path(".gwt/config.yml"))

    def test_worktrees_root_rejects_parent_traversal(self) -> None:
        with pytest.raises(ValueError, match="worktrees_root"):
            validate_config({"worktrees_root": "../escape"}, Path(".gwt/config.yml"))

    def test_copy_rejects_non_list(self) -> None:
        with pytest.raises(TypeError, match="copy"):
            validate_config({"copy": "not_a_list"}, Path(".gwt/config.yml"))

    def test_commands_rejects_non_dict(self) -> None:
        with pytest.raises(TypeError, match="commands"):
            validate_config({"commands": ["not", "a", "dict"]}, Path(".gwt/config.yml"))

    def test_worktrees_root_rejects_empty_string(self) -> None:
        with pytest.raises(ValueError, match="worktrees_root"):
            validate_config({"worktrees_root": ""}, Path(".gwt/config.yml"))

    def test_unknown_keys_are_ignored(self) -> None:
        parsed = validate_config({"unknown_key": "value"}, Path(".gwt/config.yml"))
        assert parsed.config.worktrees_root == ".worktrees"


class TestMergeConfigs:
    def test_lists_are_concatenated(self) -> None:
        base = ParsedConfig(GwtConfig(copy=[".env"], on_create=["echo base"]), {"copy", "on_create"})
        local = ParsedConfig(GwtConfig(copy=["config/*.yml"], on_create=["echo local"]), {"copy", "on_create"})
        merged = merge_configs(base, local)
        assert merged.copy == [".env", "config/*.yml"]
        assert merged.on_create == ["echo base", "echo local"]

    def test_scalars_are_overridden(self) -> None:
        base = ParsedConfig(GwtConfig(worktrees_root=".worktrees"), {"worktrees_root"})
        local = ParsedConfig(GwtConfig(worktrees_root=".wt"), {"worktrees_root"})
        merged = merge_configs(base, local)
        assert merged.worktrees_root == ".wt"

    def test_commands_are_deep_merged(self) -> None:
        base = ParsedConfig(GwtConfig(commands={"setup": "npm install", "test": "npm test"}), {"commands"})
        local = ParsedConfig(GwtConfig(commands={"setup": "yarn install", "lint": "ruff check"}), {"commands"})
        merged = merge_configs(base, local)
        assert merged.commands == {"setup": "yarn install", "test": "npm test", "lint": "ruff check"}

    def test_local_without_explicit_keys_does_not_override_base(self) -> None:
        base = ParsedConfig(GwtConfig(worktrees_root=".custom", copy=[".env"]), {"worktrees_root", "copy"})
        local = ParsedConfig(GwtConfig(), set())  # nothing explicitly set
        merged = merge_configs(base, local)
        assert merged.worktrees_root == ".custom"
        assert merged.copy == [".env"]

    def test_local_explicit_default_value_overrides_base(self) -> None:
        base = ParsedConfig(GwtConfig(worktrees_root=".custom"), {"worktrees_root"})
        # local explicitly set to the default value
        local = ParsedConfig(GwtConfig(worktrees_root=".worktrees"), {"worktrees_root"})
        merged = merge_configs(base, local)
        assert merged.worktrees_root == ".worktrees"


class TestLoadConfig:
    def test_load_from_gwt_yml(self, tmp_git_repo: Path) -> None:
        write_config(tmp_git_repo, {"worktrees_root": ".wt", "copy": [".env"]})
        config = load_config(tmp_git_repo)
        assert config.worktrees_root == ".wt"
        assert config.copy == [".env"]

    def test_load_merges_local(self, tmp_git_repo: Path) -> None:
        write_config(tmp_git_repo, {"copy": [".env"]})
        write_config(tmp_git_repo, {"copy": ["config/*.yml"]}, local=True)
        config = load_config(tmp_git_repo)
        assert config.copy == [".env", "config/*.yml"]

    def test_load_missing_gwt_yml_returns_defaults(self, tmp_git_repo: Path) -> None:
        # A missing .gwt/config.yml is not an error: callers warn and fall back to defaults.
        config = load_config(tmp_git_repo)
        assert config.worktrees_root == DEFAULT_WORKTREES_ROOT
        assert config.copy == []

    def test_load_missing_gwt_yml_still_merges_local(self, tmp_git_repo: Path) -> None:
        write_config(tmp_git_repo, {"copy": ["config/*.yml"]}, local=True)
        config = load_config(tmp_git_repo)
        assert config.copy == ["config/*.yml"]

    def test_load_missing_local_is_ok(self, tmp_git_repo: Path) -> None:
        write_config(tmp_git_repo, {"copy": [".env"]})
        config = load_config(tmp_git_repo)
        assert config.copy == [".env"]


class TestDefaultConfigContent:
    def test_contains_explanatory_comments(self) -> None:
        content = default_config_content()
        assert "worktrees_root" in content
        assert "#" in content

    def test_is_valid_yaml(self) -> None:
        import yaml

        content = default_config_content()
        parsed = yaml.safe_load(content)
        assert isinstance(parsed, dict)

    def test_default_config_documents_extra_args(self) -> None:
        content = default_config_content()
        assert "gwt run <name> -- arg1 arg2" in content
        assert "$1" in content
        assert "${@:2}" in content
