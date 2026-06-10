"""Share management tools for OpenList MCP Server."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from ..client import get_client
from . import enforce_path_allowed, enforce_writable, validate_pagination


def register_share_tools(mcp: FastMCP) -> None:
    """Register share management MCP tools."""

    @mcp.tool()
    async def create_share(
        files: list[str],
        pwd: str = "",
        expires: str = "",
        max_accessed: int = 0,
        remark: str = "",
    ) -> str:
        """Create share link(s) for one or more files or folders.

        Each item in files should be a full path on OpenList (e.g. "/documents/report.pdf").
        You can share multiple items in a single share link.

        Args:
            files: List of file/folder paths to include in the share (e.g. ["/docs/report.pdf", "/docs/images"]).
            pwd: Optional password to protect the share link.
            expires: Optional expiration time (ISO 8601 format, e.g. "2026-12-31T23:59:59Z"
                     or relative like "+7d" for 7 days). Leave empty for no expiration.
            max_accessed: Maximum number of times the share can be accessed (0 = unlimited).
            remark: Optional remark or note for the share link.

        Returns:
            JSON string with share details including the share URL/id.
        """
        if not files:
            return json.dumps(
                {"ok": False, "error": "At least one file must be specified to create a share."},
                ensure_ascii=False,
            )
        for f in files:
            enforce_path_allowed(f)
        enforce_writable("create_share")

        body: dict = {"files": files}
        if pwd:
            body["pwd"] = pwd
        if expires:
            body["expires"] = expires
        if max_accessed > 0:
            body["max_accessed"] = max_accessed
        if remark:
            body["remark"] = remark

        client = await get_client()
        data = await client.request("POST", "share/create", json=body)
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def get_share_info(share_id: str) -> str:
        """Get detailed information about a specific share link.

        Args:
            share_id: The unique ID of the share to query.

        Returns:
            JSON string with share details.
        """
        client = await get_client()
        data = await client.request("GET", "share/get", params={"id": share_id})
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def list_shares(page: int = 1, per_page: int = 50) -> str:
        """List all existing share links.

        Args:
            page: Page number for pagination. Defaults to 1.
            per_page: Number of items per page (max 200). Defaults to 50.

        Returns:
            JSON string containing share list with id, path, password status, expiration, etc.
        """
        validate_pagination(page, per_page)
        client = await get_client()
        data = await client.request(
            "GET",
            "share/list",
            params={"page": page, "per_page": per_page},
        )
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def update_share(
        share_id: str,
        files: list[str] | None = None,
        pwd: str = "",
        expires: str = "",
        max_accessed: int = 0,
        remark: str = "",
    ) -> str:
        """Update an existing share link's settings.

        Changes take effect immediately. The files list must be provided again
        (the same or updated) — OpenList requires at least one file for a share.

        Args:
            share_id: The unique ID of the share to update.
            files: Updated list of file/folder paths. Must include at least one item.
                   Pass the same list to keep existing files, or a new list to change them.
            pwd: New password. Leave empty to keep the existing password.
            expires: New expiration time (ISO 8601). Leave empty to keep existing.
            max_accessed: New max access count (0 = unlimited, -1 = keep existing).
            remark: New remark. Leave empty to keep existing.

        Returns:
            Success or error message.
        """
        enforce_writable("update_share")

        body: dict = {"id": share_id}

        if files is not None:
            for f in files:
                enforce_path_allowed(f)
            body["files"] = files
        elif pwd or expires or max_accessed > 0 or remark:
            # Fetch current files from the specific share
            client = await get_client()
            share_data = await client.request("GET", "share/get", params={"id": share_id})
            current_files = share_data.get("files", [])
            if current_files:
                body["files"] = current_files
            else:
                return json.dumps(
                    {
                        "ok": False,
                        "error": (
                            f"Share '{share_id}' not found or has no files. "
                            "Please provide the files parameter explicitly."
                        ),
                    },
                    ensure_ascii=False,
                )

        if pwd:
            body["pwd"] = pwd
        if expires:
            body["expires"] = expires
        if max_accessed > 0:
            body["max_accessed"] = max_accessed
        if remark:
            body["remark"] = remark

        client = await get_client()
        await client.request("POST", "share/update", json=body)
        return f"Share updated successfully: {share_id}"

    @mcp.tool()
    async def cancel_share(share_id: str, confirm: bool = False) -> str:
        """Cancel (disable) an existing share link, preventing further access.

        This is an alias for disable_share — the share can be re-enabled later.

        Args:
            share_id: The unique ID of the share to cancel.
            confirm: Must be true to actually cancel the share. Defaults to false.

        Returns:
            Success message or confirmation-required message.
        """
        if not confirm:
            return "⚠️ Share cancellation not performed. Re-run with confirm=true to cancel it."
        enforce_writable("cancel_share")
        client = await get_client()
        await client.request("POST", "share/disable", json={"id": share_id})
        return f"Share cancelled successfully: {share_id}"

    @mcp.tool()
    async def delete_share(share_id: str, confirm: bool = False) -> str:
        """Delete a share link permanently.

        Unlike cancel_share, this removes the share entirely and cannot be undone.

        Args:
            share_id: The unique ID of the share to delete.
            confirm: Must be true to actually delete the share. Defaults to false.

        Returns:
            Success message or confirmation-required message.
        """
        if not confirm:
            return "⚠️ Share deletion not performed. Re-run with confirm=true to delete it."
        enforce_writable("delete_share")
        client = await get_client()
        await client.request("POST", "share/delete", json={"id": share_id})
        return f"Share deleted successfully: {share_id}"

    @mcp.tool()
    async def enable_share(share_id: str) -> str:
        """Enable a previously disabled/cancelled share link.

        Args:
            share_id: The unique ID of the share to enable.

        Returns:
            Success or error message.
        """
        enforce_writable("enable_share")
        client = await get_client()
        await client.request("POST", "share/enable", json={"id": share_id})
        return f"Share enabled successfully: {share_id}"

    @mcp.tool()
    async def disable_share(share_id: str) -> str:
        """Disable a share link temporarily without deleting it.

        The share can be re-enabled later using enable_share.

        Args:
            share_id: The unique ID of the share to disable.

        Returns:
            Success or error message.
        """
        enforce_writable("disable_share")
        client = await get_client()
        await client.request("POST", "share/disable", json={"id": share_id})
        return f"Share disabled successfully: {share_id}"
