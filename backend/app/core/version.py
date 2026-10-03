"""The app version, from the installed package metadata (pyproject.toml)."""

from importlib.metadata import version

APP_VERSION = version("fee-refund-agent")
