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


def _string_command(path: str, key: str) -> str | None:
    """Return the optional string command stored under `key`, or None."""
    config = load_mapping(path)
    if key not in config:
        return None
    value = config[key]
    if not isinstance(value, str):
        raise ProjectConfigError(f"`{key}:` in {path} must be a string")
    return value


def setup_command(path: str) -> str | None:
    """Return the optional project worktree setup command."""
    return _string_command(path, "setup")


def teardown_command(path: str) -> str | None:
    """Return the optional project teardown command."""
    return _string_command(path, "teardown")


# The CLI commands, each a shell-callable accessor. Both read a string key through
# the same loader, so `sapa-worktree` and `sapa-teardown` share one reader tool.
COMMANDS = {
    "setup": setup_command,
    "teardown": teardown_command,
}


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[2] not in COMMANDS:
        print(f"usage: {argv[0]} CONFIG {{{'|'.join(COMMANDS)}}}", file=sys.stderr)
        return 2
    try:
        value = COMMANDS[argv[2]](argv[1])
    except ProjectConfigError as error:
        print(f"sapa config: {error}", file=sys.stderr)
        return 2
    if value is not None:
        sys.stdout.write(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
