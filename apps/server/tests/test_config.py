from __future__ import annotations

from pathlib import Path

from config import Settings


def test_settings_loads_repo_root_env_for_uv_directory_commands() -> None:
    repo_root_env = Path(__file__).resolve().parents[3] / ".env"

    configured_env_files = Settings.model_config["env_file"]
    env_files = (configured_env_files,) if isinstance(configured_env_files, str) else tuple(configured_env_files)

    assert repo_root_env in env_files
