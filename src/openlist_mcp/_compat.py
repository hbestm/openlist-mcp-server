"""Compatibility shim for the mcp SDK's FastMCP → MCPServer rename.

mcp 2.0.0 renamed the ``FastMCP`` class to ``MCPServer`` and moved it from
``mcp.server.fastmcp`` to ``mcp.server.mcpserver``. The class keeps the same
constructor keywords (``name``, ``instructions``), the same ``.tool()``
decorator, and the same ``.run()`` entry point, so a single import shim is all
that is needed to support both major versions.

Import ``FastMCP`` from this module instead of from the SDK directly.
"""

from __future__ import annotations

try:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP  # type: ignore[no-redef,attr-defined]

__all__ = ["FastMCP"]
