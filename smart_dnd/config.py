"""Configuration management for Smart DND."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from smart_dnd.models import Config

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "smart-dnd"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"


# Set from the CLI's --config, so every load and save in this process uses that file.
_config_path_override: Optional[Path] = None


def set_default_config_path(path: Optional[str | Path]) -> None:
    global _config_path_override
    _config_path_override = Path(path).expanduser().resolve() if path else None


def get_config_path(custom_path: Optional[str | Path] = None) -> Path:
    if custom_path:
        return Path(custom_path)
    return _config_path_override or DEFAULT_CONFIG_FILE


def load_config(custom_path: Optional[str | Path] = None) -> Config:
    path = get_config_path(custom_path)
    if not path.exists():
        logger.info("Config file not found at %s. Creating default configuration.", path)
        config = Config()
        save_config(config, custom_path=path)
        return config

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return Config.from_dict(data)
    except Exception as e:
        logger.error("Failed to read config from %s: %s. Using default config.", path, e)
        return Config()


def save_config(config: Config, custom_path: Optional[str | Path] = None) -> None:
    path = get_config_path(custom_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2)
    tmp_path.replace(path)
    logger.debug("Saved configuration to %s", path)
