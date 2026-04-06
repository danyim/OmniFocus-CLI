"""OmniFocus CLI — independent CLI, MCP server, and HTTPS API for OmniFocus 4.

Connects directly to a WebDAV sync server, decrypts the .ofocus bundle,
and exposes task management via a Click CLI, an MCP server, and a secure
HTTPS API.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

__author__ = "Maciej Szymczak <maciej@szymczak.at>"

try:
    __version__ = version("omnifocus-cli")
except PackageNotFoundError:
    __version__ = "0+unknown"
