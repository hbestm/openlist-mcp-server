"""File transfer tools for OpenList MCP Server."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path

from mcp.server.mcpserver import MCPServer as FastMCP

from ..client import get_client
from . import enforce_path_allowed, enforce_writable, validate_name

# Maximum base64 content length for upload_file (~75MB raw, ~100MB base64).
# For larger files, use upload_local_file which streams from disk.
MAX_BASE64_UPLOAD_BYTES = 104_857_600  # 100 MB base64 string length


def _allowed_upload_roots() -> list[Path]:
    roots = os.environ.get("OPENLIST_LOCAL_UPLOAD_ROOTS", "").strip()
    if not roots:
        return []
    return [Path(root).expanduser().resolve() for root in roots.split(os.pathsep) if root.strip()]


def _is_allowed_local_path(file_path: Path) -> bool:
    roots = _allowed_upload_roots()
    if not roots:
        return False
    resolved = file_path.resolve()
    return any(resolved == root or root in resolved.parents for root in roots)


async def _iter_file_chunks(file_path: Path, chunk_size: int = 1024 * 1024) -> AsyncIterator[bytes]:
    with file_path.open("rb") as file_obj:
        while chunk := file_obj.read(chunk_size):
            yield chunk
            await asyncio.sleep(0)


def register_transfer_tools(mcp: FastMCP) -> None:
    """Register file upload/download MCP tools."""

    @mcp.tool()
    async def get_download_url(
        path: str,
        password: str = "",
    ) -> str:
        """Get the download URL for a file on OpenList.

        This returns the direct download link (or proxy link) for a file.
        The URL may include a time-limited signature for security.

        Args:
            path: Full path to the file.
            password: Password if the path is password-protected. Defaults to "".

        Returns:
            The download URL for the file, or file info with raw_url.
        """
        enforce_path_allowed(path)
        client = await get_client()
        data = await client.request(
            "POST",
            "fs/get",
            json={"path": path, "password": password},
        )
        raw_url = data.get("raw_url", "")
        if raw_url:
            return json.dumps(
                {"download_url": raw_url, "path": path},
                indent=2,
                ensure_ascii=False,
            )
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def upload_file(
        path: str,
        file_name: str,
        file_content_base64: str,
        as_task: bool = True,
    ) -> str:
        """Upload a file to OpenList from base64-encoded content.

        Args:
            path: Target directory path on OpenList (e.g. "/documents").
            file_name: Name for the uploaded file (e.g. "report.pdf").
            file_content_base64: Base64-encoded file content.
            as_task: Process as async task for large files. Defaults to True.

        Returns:
            Success message or task ID for async uploads.
        """
        enforce_path_allowed(path)
        enforce_writable("upload_file")
        validate_name(file_name)

        if len(file_content_base64) > MAX_BASE64_UPLOAD_BYTES:
            raw_mb = len(file_content_base64) * 3 // 4 // 1024 // 1024
            return (
                f"File too large ({raw_mb} MB estimated raw). "
                f"Maximum base64 upload is {MAX_BASE64_UPLOAD_BYTES // 1024 // 1024} MB. "
                "For larger files, use upload_local_file which streams from disk."
            )

        client = await get_client()
        try:
            file_bytes = base64.b64decode(file_content_base64)
        except (ValueError, binascii.Error) as e:
            return f"Failed to decode base64 content: {e}"

        data = await client.upload(
            path=path,
            file_content=file_bytes,
            file_name=file_name,
            as_task=as_task,
        )
        if data is not None and data != {}:
            return f"Upload task created: {json.dumps(data, ensure_ascii=False)}"
        return f"File uploaded successfully: {path}/{file_name}"

    @mcp.tool()
    async def upload_local_file(
        local_path: str,
        remote_dir: str,
        remote_name: str = "",
        as_task: bool = True,
    ) -> str:
        """Upload a local file that the MCP server process can access.

        Use this when the agent and MCP server run on the same machine, or when the
        MCP server can read the provided file path. Set OPENLIST_LOCAL_UPLOAD_ROOTS
        to restrict readable upload paths (os.pathsep-separated). For generic MCP
        clients that cannot expose local files to the server, use upload_file with
        base64 content.

        Args:
            local_path: Local filesystem path readable by the MCP server process.
            remote_dir: Target directory path on OpenList (e.g. "/documents").
            remote_name: Optional remote filename. Defaults to the local filename.
            as_task: Process as async task for large files. Defaults to True.

        Returns:
            Success message or task ID for async uploads.
        """
        enforce_path_allowed(remote_dir)
        enforce_writable("upload_local_file")
        file_path = Path(local_path).expanduser()
        if not file_path.is_file():
            return f"Local file not found or not a regular file: {local_path}"
        if not _is_allowed_local_path(file_path):
            return (
                "Local file upload is not allowed for this path. "
                "Set OPENLIST_LOCAL_UPLOAD_ROOTS to include an allowed parent directory."
            )

        final_name = remote_name.strip() or file_path.name
        try:
            validate_name(final_name)
        except ValueError as exc:
            return f"remote_name must be a filename only, not a path: {exc}"

        client = await get_client()
        data = await client.upload(
            path=remote_dir,
            file_content=_iter_file_chunks(file_path),
            file_name=final_name,
            as_task=as_task,
        )
        if data is not None and data != {}:
            return f"Upload task created: {json.dumps(data, ensure_ascii=False)}"
        return f"File uploaded successfully: {remote_dir}/{final_name}"
