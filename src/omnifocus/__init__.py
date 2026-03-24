"""OmniFocus CLI — independent CLI and MCP server for OmniFocus 4.

Connects directly to a WebDAV sync server, decrypts the .ofocus bundle,
and exposes task management via a Click CLI and an MCP server for Claude.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

__author__ = "Maciej Szymczak <maciej@szymczak.at>"

try:
    __version__ = version("omnifocus-cli")
except PackageNotFoundError:
    __version__ = "0+unknown"
