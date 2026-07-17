"""Read-only Streamable HTTP transport for the OmniFocus MCP server."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, MutableMapping
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.streamable_http import StreamableHTTPServerTransport

from omnifocus.mcp_server import read_only_server

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Scope]]
Send = Callable[[Scope], Awaitable[None]]


class ReadOnlyMCPHTTPApp:
    """ASGI adapter and lifespan owner for a stateless read-only MCP server."""

    def __init__(self) -> None:
        self._transport = StreamableHTTPServerTransport(
            mcp_session_id=None,
            is_json_response_enabled=True,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle one Streamable HTTP MCP request."""
        await self._transport.handle_request(scope, receive, send)

    @asynccontextmanager
    async def lifespan(self) -> AsyncIterator[None]:
        """Run the low-level MCP server for the lifetime of the ASGI application."""
        async with self._transport.connect() as (read_stream, write_stream):
            server_task = asyncio.create_task(
                read_only_server.run(
                    read_stream,
                    write_stream,
                    read_only_server.create_initialization_options(),
                    stateless=True,
                )
            )
            try:
                yield
            finally:
                await self._transport.terminate()
                await server_task
