from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from git import Repo


@pytest.fixture()
def tmp_git_repo(tmp_path: Path) -> Path:
    """Create a bare temporary git repo with an initial commit."""
    repo = Repo.init(tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text("test repo")
    repo.index.add(["README.md"])
    repo.index.commit("initial commit")
    return tmp_path


def write_config(repo_path: Path, config: dict[str, Any], local: bool = False) -> Path:
    """Write a .gwt/config.yml or .gwt/config.local.yml file."""
    filename = "config.local.yml" if local else "config.yml"
    config_path = repo_path / ".gwt" / filename
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.dump(config, default_flow_style=False))
    return config_path
