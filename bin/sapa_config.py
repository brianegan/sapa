#!/usr/bin/env python3
"""Shared YAML loading for Sapa's project config consumers."""

from __future__ import annotations

import sys

try:
    import yaml
except ImportError:
    yaml = None


class ProjectConfigError(Exception):
    """A project config cannot be loaded through the supported interface."""


def require_yaml():
    """Return PyYAML or raise the same actionable error for every caller."""
    if yaml is None:
        raise ProjectConfigError(
            f"reading project config needs PyYAML, which is not importable by "
            f"{sys.executable} (install it with: {sys.executable} -m pip install pyyaml)"
        )
    return yaml


def load_mapping(path: str) -> dict:
    """Load a project config as its required top-level settings mapping."""
    yaml_module = require_yaml()
    try:
        with open(path, encoding="utf-8") as config_file:
            config = yaml_module.safe_load(config_file)
    except OSError as error:
        raise ProjectConfigError(f"could not read {path}: {error}") from error
    except yaml_module.YAMLError as error:
        raise ProjectConfigError(f"{path} is not valid YAML: {error}") from error

    if config is None:
        return {}
    if not isinstance(config, dict):
        raise ProjectConfigError(f"{path} does not hold a mapping of settings")
    return config


def string_value(path: str, key: str) -> str | None:
    """Return an optional string setting, rejecting present non-string values."""
    config = load_mapping(path)
    if key not in config:
        return None
    value = config[key]
    if not isinstance(value, str):
        raise ProjectConfigError(f"{key}: in {path} must be a string")
    return value


def main(argv: list[str]) -> int:
    if len(argv) != 4 or argv[1] != "get-string":
        print(f"usage: {argv[0]} get-string CONFIG KEY", file=sys.stderr)
        return 2
    try:
        value = string_value(argv[2], argv[3])
    except ProjectConfigError as error:
        print(f"sapa config: {error}", file=sys.stderr)
        return 2
    if value is not None:
        sys.stdout.write(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
