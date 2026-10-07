"""System administration tools for OpenList MCP Server.

Provides read-only (storage, driver, setting, index, user, meta) and
write (index build, setting save, etc.) tools for server administration.
All destructive write operations require confirm=true for safety.
"""

from __future__ import annotations

import json
from typing import Any

from .._compat import FastMCP
from ..client import OpenListError, get_client
from . import enforce_writable, validate_pagination

# Default permission mask for new users: bits 0-7 (see hidden/access/offline/
# mkdir/rename/move/copy/remove) plus 12-15 (read/decompress archives, share,
# custom share id). WebDAV/SFTP bits 8-11 are intentionally off.
DEFAULT_USER_PERMISSION = 0b1100111111111111  # 53247

_ROLE_TO_ID = {"general": 0, "user": 0, "guest": 1, "admin": 2}
_ID_TO_ROLE = {0: "general", 1: "guest", 2: "admin"}

# Storage model JSON fields (internal/model/storage.go) — everything the
# create/update endpoints accept. Used to rebuild a safe full payload.
_STORAGE_FIELDS = (
    "id",
    "mount_path",
    "driver",
    "order",
    "cache_expiration",
    "custom_cache_policies",
    "status",
    "addition",
    "remark",
    "modified",
    "disabled",
    "disable_index",
    "enable_sign",
    "order_by",
    "order_direction",
    "extract_folder",
    "web_proxy",
    "webdav_policy",
    "proxy_range",
    "down_proxy_url",
    "disable_proxy_sign",
)
_USER_FIELDS = (
    "id",
    "username",
    "base_path",
    "role",
    "disabled",
    "permission",
    "sso_id",
    "allow_ldap",
)


def _normalize_mount_path(mount_path: str) -> str:
    """Normalize a mount path to OpenList's canonical form (no trailing /)."""
    path = mount_path.strip()
    if not path:
        return "/"
    if not path.startswith("/"):
        path = "/" + path
    return path.rstrip("/") or "/"


def _parse_addition(addition: str) -> dict[str, Any]:
    """Parse the driver config JSON string into a dict (raises ValueError)."""
    if isinstance(addition, str):
        addition = addition.strip() or "{}"
        try:
            parsed = json.loads(addition)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "addition must be a valid JSON object string "
                '(e.g. \'{"root_folder_path": "/data"}\')'
            ) from exc
    else:
        parsed = addition
    if not isinstance(parsed, dict):
        raise ValueError('addition must be a JSON object (e.g. \'{"root_folder_path": "/data"}\')')
    return parsed


async def _save_driver_config(endpoint: str, body: dict[str, Any]) -> dict:
    """POST a driver config to admin/setting/set_* and return the response.

    The server saves the settings first and then probes the client (e.g. asks
    aria2 for its version). When the probe fails the endpoint returns 500 even
    though the configuration WAS persisted — surface that as a note instead of
    a hard failure so the user knows the config is already saved.
    """
    client = await get_client()
    try:
        data = await client.request("POST", endpoint, json=body)
    except OpenListError as exc:
        if "failed get" in str(exc) or "version" in str(exc):
            return {
                "_saved": True,
                "_note": f"Configuration saved, but the client probe failed: {exc}",
            }
        raise
    return data if isinstance(data, dict) else {"value": data}


def register_admin_tools(mcp: FastMCP) -> None:
    """Register system administration MCP tools."""

    # ─────────────────────────── Storage (read-only) ───────────────────────────

    @mcp.tool()
    async def list_storages() -> str:
        """List all configured storage backends on the OpenList server.

        Returns details about each storage including mount path, driver type,
        status, total space, and free space. Read-only — no modification.

        Returns:
            JSON string with storage list.
        """
        client = await get_client()
        data = await client.request("GET", "admin/storage/list")
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def get_storage_info(storage_id: int) -> str:
        """Get detailed information about a specific storage backend.

        Args:
            storage_id: The numeric ID of the storage to query. Use list_storages
                       to see available IDs.

        Returns:
            JSON string with storage details.
        """
        client = await get_client()
        data = await client.request("GET", "admin/storage/get", params={"id": storage_id})
        return json.dumps(data, indent=2, ensure_ascii=False)

    # ─────────────────────────── Driver (read-only) ────────────────────────────

    @mcp.tool()
    async def list_drivers() -> str:
        """List all registered storage driver names on the server.

        Shows what storage backend types are available (Local, S3, OneDrive,
        115, 189PC, AliyunDrive, etc.).

        Returns:
            JSON list of driver names.
        """
        client = await get_client()
        data = await client.request("GET", "admin/driver/names")
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def get_driver_info(driver: str) -> str:
        """Get detailed information about a specific storage driver.

        Shows the driver's configuration fields and their types.

        Args:
            driver: Driver name (e.g. "Local", "S3", "189PC"). Use list_drivers
                   to see available names.

        Returns:
            JSON string with driver info.
        """
        client = await get_client()
        data = await client.request("GET", "admin/driver/info", params={"driver": driver})
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def list_drivers_detail() -> str:
        """List all storage drivers with full configuration templates.

        Unlike list_drivers (which only returns driver names), this endpoint
        returns detailed configuration fields and their types for every
        registered driver. Useful when creating or updating storage backends.

        Returns:
            JSON array of drivers with their configuration templates.
        """
        client = await get_client()
        data = await client.request("GET", "admin/driver/list")
        return json.dumps(data, indent=2, ensure_ascii=False)

    # ─────────────────────────── Settings (read + write) ───────────────────────

    @mcp.tool()
    async def get_settings() -> str:
        """List all global settings on the OpenList server.

        Returns all configuration key-value pairs including site title,
        pagination settings, preview options, etc. Read-only.

        Returns:
            JSON string with all settings.
        """
        client = await get_client()
        data = await client.request("GET", "admin/setting/list")
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def get_setting(key: str) -> str:
        """Get a single global setting by its key.

        Args:
            key: The setting key (e.g. "site_title", "pagination_type",
                "logo", "favicon"). Use get_settings to see all keys.

        Returns:
            JSON string with the setting value.
        """
        client = await get_client()
        data = await client.request("GET", "admin/setting/get", params={"key": key})
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def save_settings(
        settings: list[dict],
        confirm: bool = False,
    ) -> str:
        """Update one or more global system settings.

        Provide settings as a list of objects with "key" and "value" fields.
        All settings are saved atomically in a single request.

        Examples:
          - Set site title:  [{"key": "site_title", "value": "My Cloud"}]
          - Change pagination: [{"key": "pagination_type", "value": "0"}]

        Args:
            settings: List of {"key": "...", "value": "..."} objects to update.
            confirm: Must be true to actually save. Defaults to false.

        Returns:
            Success message or confirmation-required message.
        """
        if not confirm:
            return "⚠️ Settings save not performed. Re-run with confirm=true to save these settings."
        if not settings:
            return "No settings provided to save."
        enforce_writable("save_settings")
        client = await get_client()
        await client.request("POST", "admin/setting/save", json=settings)
        return f"Settings saved successfully ({len(settings)} key(s))."

    @mcp.tool()
    async def delete_setting(
        key: str,
        confirm: bool = False,
    ) -> str:
        """Delete a custom setting by its key.

        Removes a previously saved custom setting from the server.
        Built-in settings may not be deletable.

        Args:
            key: The setting key to delete (e.g. "custom_logo").
            confirm: Must be true to actually delete. Defaults to false.

        Returns:
            Success message or confirmation-required message.
        """
        if not confirm:
            return (
                "⚠️ Setting deletion not performed. Re-run with confirm=true to delete this setting."
            )
        if not key:
            return "No setting key provided."
        enforce_writable("delete_setting")
        client = await get_client()
        # The server reads the key from the query string (c.Query("key")),
        # not from the JSON body.
        await client.request("POST", "admin/setting/delete", params={"key": key})
        return f"Setting deleted successfully: {key}"

    # ─────────────────────────── Search Index ──────────────────────────────────

    @mcp.tool()
    async def get_index_progress() -> str:
        """Get the current search index building progress.

        Useful for determining whether search results are up to date.

        Returns:
            JSON string with index progress info.
        """
        client = await get_client()
        data = await client.request("GET", "admin/index/progress")
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def build_search_index(confirm: bool = False) -> str:
        """Build the full-text search index for all storages.

        This scans all mounted storage backends and rebuilds the search index
        from scratch. May take a long time on large deployments. Use
        get_index_progress to monitor progress.

        Args:
            confirm: Must be true to actually build. Defaults to false.

        Returns:
            Success message or confirmation-required message.
        """
        if not confirm:
            return (
                "Search index build not performed. "
                "⚠️ Re-run with confirm=true to build the search index."
            )
        enforce_writable("build_search_index")
        client = await get_client()
        await client.request("POST", "admin/index/build")
        return "Search index build started. Use get_index_progress to monitor."

    @mcp.tool()
    async def update_search_index(
        paths: list[str] | None = None,
        confirm: bool = False,
    ) -> str:
        """Update the search index for specific paths.

        Unlike a full rebuild, this incrementally updates the index for
        the specified paths only. Faster than a full rebuild when only
        certain directories have changed.

        Args:
            paths: List of directory paths to re-index. If omitted or empty,
                   the server may update all paths.
            confirm: Must be true to actually update. Defaults to false.

        Returns:
            Success message or confirmation-required message.
        """
        if not confirm:
            return (
                "Search index update not performed. "
                "⚠️ Re-run with confirm=true to update the search index."
            )
        enforce_writable("update_search_index")
        client = await get_client()
        body = {"paths": paths} if paths else {}
        await client.request("POST", "admin/index/update", json=body)
        return "Search index update started."

    @mcp.tool()
    async def stop_indexing(confirm: bool = False) -> str:
        """Stop the current search index building or updating operation.

        Useful when an indexing operation is taking too long or consuming
        too many server resources.

        Args:
            confirm: Must be true to actually stop. Defaults to false.

        Returns:
            Success message or confirmation-required message.
        """
        if not confirm:
            return "⚠️ Indexing stop not performed. Re-run with confirm=true to stop indexing."
        enforce_writable("stop_indexing")
        client = await get_client()
        await client.request("POST", "admin/index/stop")
        return "Indexing operation stopped."

    @mcp.tool()
    async def clear_search_index(confirm: bool = False) -> str:
        """Delete all search index data.

        WARNING: This removes the entire search index. Searching will return
        no results until a new index is built via build_search_index.

        Args:
            confirm: Must be true to actually clear. Defaults to false.

        Returns:
            Success message or confirmation-required message.
        """
        if not confirm:
            return (
                "Search index clear not performed. "
                "⚠️ Re-run with confirm=true to clear the search index."
            )
        enforce_writable("clear_search_index")
        client = await get_client()
        await client.request("POST", "admin/index/clear")
        return "Search index cleared. Use build_search_index to rebuild."

    # ─────────────────────────── User Management ───────────────────────────────

    @mcp.tool()
    async def list_users(
        page: int = 1,
        per_page: int = 30,
    ) -> str:
        """List all user accounts on the server (Admin only).

        Returns paginated list of users with their roles, permissions,
        and account status. Read-only — no modification.

        Args:
            page: Page number for pagination. Defaults to 1.
            per_page: Number of items per page. Defaults to 30.

        Returns:
            JSON string with user list including id, username, role, etc.
        """
        validate_pagination(page, per_page, max_per_page=200)
        client = await get_client()
        data = await client.request(
            "GET",
            "admin/user/list",
            params={"page": page, "per_page": per_page},
        )
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def get_user(user_id: int) -> str:
        """Get detailed information about a specific user (Admin only).

        Shows user details including username, role, permissions bitmap,
        base path, 2FA status, and whether the account is disabled.

        Args:
            user_id: The numeric ID of the user to query. Use list_users
                    to see available user IDs.

        Returns:
            JSON string with user details.
        """
        client = await get_client()
        data = await client.request("GET", "admin/user/get", params={"id": user_id})
        return json.dumps(data, indent=2, ensure_ascii=False)

    # ─────────────────────────── Meta Management ───────────────────────────────

    @mcp.tool()
    async def list_metas() -> str:
        """List all metadata configurations on the server (Admin only).

        Returns all directory-level metadata such as password protection,
        readme text, header content, and visibility settings.

        Returns:
            JSON array of metadata configurations.
        """
        client = await get_client()
        data = await client.request("GET", "admin/meta/list")
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def get_meta(meta_id: int) -> str:
        """Get a specific metadata configuration by its ID (Admin only).

        Args:
            meta_id: The numeric ID of the metadata to query. Use list_metas
                    to see available IDs.

        Returns:
            JSON string with metadata configuration.
        """
        client = await get_client()
        data = await client.request("GET", "admin/meta/get", params={"id": meta_id})
        return json.dumps(data, indent=2, ensure_ascii=False)

    # ─────────────────────────── Token Management ──────────────────────────────

    @mcp.tool()
    async def reset_api_token(confirm: bool = False) -> str:
        """Reset the server API token (Admin only).

        Generates a new API token. The current token will be invalidated
        immediately. All active sessions using the old token will need to
        re-authenticate.

        Args:
            confirm: Must be true to actually reset. Defaults to false.

        Returns:
            Success message or confirmation-required message.
        """
        if not confirm:
            return (
                "⚠️ API token reset not performed. Re-run with confirm=true to reset the API token."
            )
        enforce_writable("reset_api_token")
        client = await get_client()
        data = await client.request("POST", "admin/setting/reset_token")
        result = json.dumps(data, indent=2, ensure_ascii=False)
        return f"API token reset successfully. Result: {result}"

    # ─────────────────────────── Manual Scan ───────────────────────────────────

    @mcp.tool()
    async def start_manual_scan(
        path: str,
        limit: float = 0,
        confirm: bool = False,
    ) -> str:
        """Start a one-off manual scan of a storage mount (Admin only).

        Useful when a driver misses changes (e.g. files added out-of-band)
        and you do not want to rescan every mount. Use
        get_manual_scan_progress to monitor, and stop_manual_scan to cancel.

        Args:
            path: Storage mount path to scan (e.g. "/my-drive").
            limit: Optional scan limit (objects to process). 0 = no limit.
            confirm: Must be true to actually start. Defaults to false.

        Returns:
            Success message or confirmation-required message.
        """
        if not confirm:
            return "⚠️ Manual scan not started. Re-run with confirm=true to start the scan."
        enforce_writable("start_manual_scan")
        body: dict = {"path": path}
        if limit and limit > 0:
            body["limit"] = limit
        client = await get_client()
        await client.request("POST", "admin/scan/start", json=body)
        return f"Manual scan started for: {path}"

    @mcp.tool()
    async def stop_manual_scan(confirm: bool = False) -> str:
        """Stop a running manual scan (Admin only).

        Args:
            confirm: Must be true to actually stop. Defaults to false.

        Returns:
            Success message or confirmation-required message.
        """
        if not confirm:
            return "⚠️ Manual scan stop not performed. Re-run with confirm=true to stop the scan."
        enforce_writable("stop_manual_scan")
        client = await get_client()
        await client.request("POST", "admin/scan/stop")
        return "Manual scan stopped."

    @mcp.tool()
    async def get_manual_scan_progress() -> str:
        """Get the progress of the running (or last) manual scan (Admin only).

        Returns the number of objects scanned and whether the scan is done.

        Returns:
            JSON string with {obj_count, is_done}.
        """
        client = await get_client()
        data = await client.request("GET", "admin/scan/progress")
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def set_115(temp_dir: str = "", confirm: bool = False) -> str:
        """Configure the 115 offline-download client (Admin only).

        Args:
            temp_dir: Server-side temporary download folder for this client.
            confirm: Must be true to actually save. Defaults to false.

        Returns:
            Confirmation or error message.
        """
        if not confirm:
            return "⚠️ 115 not configured. Re-run with confirm=true to save."
        enforce_writable("set_115")
        if not temp_dir.strip():
            return json.dumps(
                {"ok": False, "error": "temp_dir is required (server-side download temp folder)."}
            )
        data = await _save_driver_config("admin/setting/set_115", {"temp_dir": temp_dir.strip()})
        return f"115 configured. Server: {json.dumps(data, ensure_ascii=False)}"

    @mcp.tool()
    async def set_115_open(temp_dir: str = "", confirm: bool = False) -> str:
        """Configure the 115 Open offline-download client (Admin only).

        Args:
            temp_dir: Server-side temporary download folder for this client.
            confirm: Must be true to actually save. Defaults to false.

        Returns:
            Confirmation or error message.
        """
        if not confirm:
            return "⚠️ 115 Open not configured. Re-run with confirm=true to save."
        enforce_writable("set_115_open")
        if not temp_dir.strip():
            return json.dumps(
                {"ok": False, "error": "temp_dir is required (server-side download temp folder)."}
            )
        data = await _save_driver_config(
            "admin/setting/set_115_open", {"temp_dir": temp_dir.strip()}
        )
        return f"115 Open configured. Server: {json.dumps(data, ensure_ascii=False)}"

    @mcp.tool()
    async def set_123_pan(temp_dir: str = "", confirm: bool = False) -> str:
        """Configure the 123 Pan offline-download client (Admin only).

        Args:
            temp_dir: Server-side temporary download folder for this client.
            confirm: Must be true to actually save. Defaults to false.

        Returns:
            Confirmation or error message.
        """
        if not confirm:
            return "⚠️ 123 Pan not configured. Re-run with confirm=true to save."
        enforce_writable("set_123_pan")
        if not temp_dir.strip():
            return json.dumps(
                {"ok": False, "error": "temp_dir is required (server-side download temp folder)."}
            )
        data = await _save_driver_config(
            "admin/setting/set_123_pan", {"temp_dir": temp_dir.strip()}
        )
        return f"123 Pan configured. Server: {json.dumps(data, ensure_ascii=False)}"

    @mcp.tool()
    async def set_pikpak(temp_dir: str = "", confirm: bool = False) -> str:
        """Configure the PikPak offline-download client (Admin only).

        Args:
            temp_dir: Server-side temporary download folder for this client.
            confirm: Must be true to actually save. Defaults to false.

        Returns:
            Confirmation or error message.
        """
        if not confirm:
            return "⚠️ PikPak not configured. Re-run with confirm=true to save."
        enforce_writable("set_pikpak")
        if not temp_dir.strip():
            return json.dumps(
                {"ok": False, "error": "temp_dir is required (server-side download temp folder)."}
            )
        data = await _save_driver_config("admin/setting/set_pikpak", {"temp_dir": temp_dir.strip()})
        return f"PikPak configured. Server: {json.dumps(data, ensure_ascii=False)}"

    @mcp.tool()
    async def set_thunder(temp_dir: str = "", confirm: bool = False) -> str:
        """Configure the Thunder offline-download client (Admin only).

        Args:
            temp_dir: Server-side temporary download folder for this client.
            confirm: Must be true to actually save. Defaults to false.

        Returns:
            Confirmation or error message.
        """
        if not confirm:
            return "⚠️ Thunder not configured. Re-run with confirm=true to save."
        enforce_writable("set_thunder")
        if not temp_dir.strip():
            return json.dumps(
                {"ok": False, "error": "temp_dir is required (server-side download temp folder)."}
            )
        data = await _save_driver_config(
            "admin/setting/set_thunder", {"temp_dir": temp_dir.strip()}
        )
        return f"Thunder configured. Server: {json.dumps(data, ensure_ascii=False)}"

    @mcp.tool()
    async def set_thunderx(temp_dir: str = "", confirm: bool = False) -> str:
        """Configure the ThunderX offline-download client (Admin only).

        Args:
            temp_dir: Server-side temporary download folder for this client.
            confirm: Must be true to actually save. Defaults to false.

        Returns:
            Confirmation or error message.
        """
        if not confirm:
            return "⚠️ ThunderX not configured. Re-run with confirm=true to save."
        enforce_writable("set_thunderx")
        if not temp_dir.strip():
            return json.dumps(
                {"ok": False, "error": "temp_dir is required (server-side download temp folder)."}
            )
        data = await _save_driver_config(
            "admin/setting/set_thunderx", {"temp_dir": temp_dir.strip()}
        )
        return f"ThunderX configured. Server: {json.dumps(data, ensure_ascii=False)}"

    @mcp.tool()
    async def set_thunder_browser(temp_dir: str = "", confirm: bool = False) -> str:
        """Configure the Thunder Browser offline-download client (Admin only).

        Args:
            temp_dir: Server-side temporary download folder for this client.
            confirm: Must be true to actually save. Defaults to false.

        Returns:
            Confirmation or error message.
        """
        if not confirm:
            return "⚠️ Thunder Browser not configured. Re-run with confirm=true to save."
        enforce_writable("set_thunder_browser")
        if not temp_dir.strip():
            return json.dumps(
                {"ok": False, "error": "temp_dir is required (server-side download temp folder)."}
            )
        data = await _save_driver_config(
            "admin/setting/set_thunder_browser", {"temp_dir": temp_dir.strip()}
        )
        return f"Thunder Browser configured. Server: {json.dumps(data, ensure_ascii=False)}"

    @mcp.tool()
    async def set_guangyapan(temp_dir: str = "", confirm: bool = False) -> str:
        """Configure the GuangYaPan offline-download client (Admin only).

        Args:
            temp_dir: Server-side temporary download folder for this client.
            confirm: Must be true to actually save. Defaults to false.

        Returns:
            Confirmation or error message.
        """
        if not confirm:
            return "⚠️ GuangYaPan not configured. Re-run with confirm=true to save."
        enforce_writable("set_guangyapan")
        if not temp_dir.strip():
            return json.dumps(
                {"ok": False, "error": "temp_dir is required (server-side download temp folder)."}
            )
        data = await _save_driver_config(
            "admin/setting/set_guangyapan", {"temp_dir": temp_dir.strip()}
        )
        return f"GuangYaPan configured. Server: {json.dumps(data, ensure_ascii=False)}"

    @mcp.tool()
    async def set_123_open(
        temp_dir: str = "", callback_url: str = "", confirm: bool = False
    ) -> str:
        """Configure the 123 Open offline-download client (Admin only).

        Args:
            temp_dir: Server-side temporary download folder.
            callback_url: Optional upload callback URL.
            confirm: Must be true to actually save. Defaults to false.

        Returns:
            Confirmation or error message.
        """
        if not confirm:
            return "⚠️ 123 Open not configured. Re-run with confirm=true to save."
        enforce_writable("set_123_open")
        if not temp_dir.strip():
            return json.dumps(
                {"ok": False, "error": "temp_dir is required (server-side download temp folder)."}
            )
        body: dict[str, Any] = {"temp_dir": temp_dir.strip()}
        if callback_url:
            body["callback_url"] = callback_url.strip()
        data = await _save_driver_config("admin/setting/set_123_open", body)
        return f"123 Open configured. Server: {json.dumps(data, ensure_ascii=False)}"

    # ─────────────────────────── Users (write) ────────────────────────────

    @mcp.tool()
    async def create_user(
        username: str,
        password: str = "",
        base_path: str = "/",
        role: str = "user",
        permission: int | None = None,
        disabled: bool = False,
        confirm: bool = False,
    ) -> str:
        """Create a new OpenList user (Admin only).

        Args:
            username: Login name (unique).
            password: Initial password. Leave empty only if you change it
                      afterwards with update_user.
            base_path: Restrict this user to a path, e.g. "/public/docs".
            role: "user" (default), "guest" or "admin". Servers refuse to
                  create "admin"/"guest" accounts; only "user" is possible.
            permission: Permission bitmask (see below). Defaults to a common
                        set: browse, upload, rename/move/copy/remove, archives,
                        sharing (bits 0-7 + 12-15), without WebDAV/SFTP.
            disabled: Create the account disabled (cannot log in).
            confirm: Must be true to actually create. Defaults to false.

        Permission bits (binary): 0 see hidden, 1 access w/o password,
        2 add offline tasks, 3 mkdir+upload, 4 rename, 5 move, 6 copy,
        7 remove, 8 webdav read, 9 webdav write, 10 ftp read, 11 ftp write,
        12 read archives, 13 decompress, 14 share, 15 custom share id.

        Returns:
            Confirmation or error message.
        """
        if not confirm:
            return "⚠️ User not created. Re-run with confirm=true to create it."
        enforce_writable("create_user")
        username = username.strip()
        if not username:
            return json.dumps({"ok": False, "error": "username is required."})
        role_id = _ROLE_TO_ID.get(role.strip().lower())
        if role_id is None:
            return json.dumps(
                {"ok": False, "error": f"invalid role {role!r}; use user/guest/admin."}
            )
        if role_id in (1, 2):
            return json.dumps(
                {
                    "ok": False,
                    "error": "cannot create guest/admin accounts via API (server rejects them).",
                }
            )
        body: dict[str, Any] = {
            "username": username,
            "password": password,
            "base_path": base_path if base_path.startswith("/") else "/" + base_path,
            "role": role_id,
            "permission": DEFAULT_USER_PERMISSION if permission is None else permission,
            "disabled": disabled,
        }
        client = await get_client()
        await client.request("POST", "admin/user/create", json=body)
        return f"User created: {username} (role={_ID_TO_ROLE.get(role_id, role_id)}, base_path={base_path})"

    @mcp.tool()
    async def update_user(
        user_id: int,
        password: str = "",
        base_path: str = "",
        disabled: bool | None = None,
        permission: int | None = None,
        confirm: bool = False,
    ) -> str:
        """Update an existing user (Admin only).

        The current profile is read first and only the provided fields change.
        Role cannot be changed through this API (server restriction).

        Args:
            user_id: Numeric user ID (see list_users).
            password: New password. Pass empty to keep the current one.
            base_path: New base path restriction (optional).
            disabled: True/False to enable or disable the account (optional).
                      Admin accounts cannot be disabled (server restriction).
            permission: New permission bitmask (optional; see create_user).
            confirm: Must be true to actually update. Defaults to false.

        Returns:
            Confirmation or error message.
        """
        if not confirm:
            return "⚠️ User not updated. Re-run with confirm=true to update it."
        enforce_writable("update_user")
        client = await get_client()
        existing = await client.request("GET", "admin/user/get", params={"id": user_id})
        if not existing or not existing.get("id"):
            return json.dumps({"ok": False, "error": f"user {user_id} not found."})
        body = {k: v for k, v in existing.items() if k in _USER_FIELDS}
        if password:
            body["password"] = password
        if base_path:
            body["base_path"] = base_path if base_path.startswith("/") else "/" + base_path
        if disabled is not None:
            body["disabled"] = disabled
        if permission is not None:
            body["permission"] = permission
        await client.request("POST", "admin/user/update", json=body)
        return f"User updated: id={user_id} (username={body.get('username')})"

    # ─────────────────────── Storage (write) ──────────────────────────────

    @mcp.tool()
    async def create_storage(
        mount_path: str,
        driver: str,
        addition: str = "{}",
        remark: str = "",
        order: int = 0,
        cache_expiration: int = 0,
        disabled: bool = False,
        disable_index: bool = False,
        enable_sign: bool = False,
        confirm: bool = False,
    ) -> str:
        """Create a new storage backend (Admin only, irreversible-ish).

        Args:
            mount_path: Mount path on OpenList, e.g. "/backup". Must not exist yet.
            driver: Storage driver name from list_drivers, e.g. "Local", "S3", "115".
            addition: Driver configuration as a JSON object string, e.g.
                      '{"root_folder_path": "/data", "chunk_size": 50}'.
                      See get_driver_info(driver) for the exact fields.
            remark: Optional human-readable remark.
            order: Sort order (lower = earlier).
            cache_expiration: Cache expiration seconds (0 = default).
            disabled: Create the storage in disabled state (no mount attempt).
            disable_index: Do not index this storage for search.
            enable_sign: Sign URLs for this storage.
            confirm: Must be true to actually create. Defaults to false.

        Returns:
            Confirmation or error message.
        """
        if not confirm:
            return "⚠️ Storage not created. Re-run with confirm=true to create it."
        enforce_writable("create_storage")
        mount_path = _normalize_mount_path(mount_path)
        driver = driver.strip()
        if not driver:
            return json.dumps({"ok": False, "error": "driver is required (see list_drivers)."})
        try:
            addition_obj = _parse_addition(addition)
        except ValueError as exc:
            return json.dumps({"ok": False, "error": str(exc)})
        body = {
            "mount_path": mount_path,
            "driver": driver,
            "addition": json.dumps(addition_obj, ensure_ascii=False),
            "remark": remark,
            "order": order,
            "cache_expiration": cache_expiration,
            "disabled": disabled,
            "disable_index": disable_index,
            "enable_sign": enable_sign,
        }
        client = await get_client()
        try:
            await client.request("POST", "admin/storage/create", json=body)
        except OpenListError as exc:
            if "already created" in str(exc):
                # The record was persisted server-side even though mounting
                # failed (e.g. a bad root_folder_path / addition). The mount
                # then exists in a broken state; tell the user it can be
                # inspected, updated or deleted.
                return json.dumps(
                    {
                        "ok": False,
                        "error": (
                            f"Storage record created but mounting failed: {exc}. "
                            "The mount may already exist in list_storages; use "
                            "get_storage_info/update_storage to fix its addition "
                            "(e.g. a valid root_folder_path) or delete_storage to remove it."
                        ),
                    }
                )
            raise
        return f"Storage created: {driver} at {mount_path}"

    @mcp.tool()
    async def update_storage(
        storage_id: int,
        mount_path: str = "",
        driver: str = "",
        addition: str = "",
        remark: str = "",
        order: int | None = None,
        cache_expiration: int | None = None,
        disabled: bool | None = None,
        disable_index: bool | None = None,
        enable_sign: bool | None = None,
        confirm: bool = False,
    ) -> str:
        """Update an existing storage backend (Admin only).

        The full current configuration is read first and only the provided
        fields are changed, so unspecified settings are preserved.

        Args:
            storage_id: ID of the storage to update (see list_storages).
            mount_path: New mount path (optional).
            driver: New driver type (optional — changing driver usually
                    requires a compatible addition).
            addition: New driver config JSON string (optional).
            remark: New remark (optional).
            order / cache_expiration / disabled / disable_index / enable_sign:
                Optional new values; omitted fields keep their current value.
            confirm: Must be true to actually update. Defaults to false.

        Returns:
            Confirmation or error message.
        """
        if not confirm:
            return "⚠️ Storage not updated. Re-run with confirm=true to update it."
        enforce_writable("update_storage")
        client = await get_client()
        existing = await client.request("GET", "admin/storage/get", params={"id": storage_id})
        if not existing or not existing.get("id"):
            return json.dumps({"ok": False, "error": f"storage {storage_id} not found."})
        body = {k: v for k, v in existing.items() if k in _STORAGE_FIELDS}
        if mount_path:
            body["mount_path"] = _normalize_mount_path(mount_path)
        if driver:
            body["driver"] = driver.strip()
        if addition:
            try:
                body["addition"] = json.dumps(_parse_addition(addition), ensure_ascii=False)
            except ValueError as exc:
                return json.dumps({"ok": False, "error": str(exc)})
        if remark:
            body["remark"] = remark
        if order is not None:
            body["order"] = order
        if cache_expiration is not None:
            body["cache_expiration"] = cache_expiration
        if disabled is not None:
            body["disabled"] = disabled
        if disable_index is not None:
            body["disable_index"] = disable_index
        if enable_sign is not None:
            body["enable_sign"] = enable_sign
        await client.request("POST", "admin/storage/update", json=body)
        return f"Storage updated: id={storage_id} (mount {body.get('mount_path')})"

    @mcp.tool()
    async def delete_storage(storage_id: int, confirm: bool = False) -> str:
        """Delete a storage backend and its configuration (Admin only).

        Warning: this removes the mount from OpenList and cannot be undone.

        Args:
            storage_id: Numeric storage ID to delete (see list_storages).
            confirm: Must be true to actually delete. Defaults to false.

        Returns:
            Confirmation or error message.
        """
        if not confirm:
            return "⚠️ Storage not deleted. Re-run with confirm=true to delete it."
        enforce_writable("delete_storage")
        client = await get_client()
        await client.request("POST", "admin/storage/delete", params={"id": storage_id})
        return f"Storage deleted: id={storage_id}"

    @mcp.tool()
    async def enable_storage(storage_id: int, confirm: bool = False) -> str:
        """Enable and remount an existing storage backend (Admin only).

        Args:
            storage_id: Numeric storage ID (see list_storages).
            confirm: Must be true to actually enable. Defaults to false.

        Returns:
            Confirmation or error message.
        """
        if not confirm:
            return "⚠️ Storage not enabled. Re-run with confirm=true to enable it."
        enforce_writable("enable_storage")
        client = await get_client()
        await client.request("POST", "admin/storage/enable", params={"id": storage_id})
        return f"Storage enabled: id={storage_id}"

    @mcp.tool()
    async def disable_storage(storage_id: int, confirm: bool = False) -> str:
        """Disable a storage backend without deleting it (Admin only).

        Files remain on the backend; the mount is simply taken offline.

        Args:
            storage_id: Numeric storage ID (see list_storages).
            confirm: Must be true to actually disable. Defaults to false.

        Returns:
            Confirmation or error message.
        """
        if not confirm:
            return "⚠️ Storage not disabled. Re-run with confirm=true to disable it."
        enforce_writable("disable_storage")
        client = await get_client()
        await client.request("POST", "admin/storage/disable", params={"id": storage_id})
        return f"Storage disabled: id={storage_id}"

    @mcp.tool()
    async def load_all_storages(confirm: bool = False) -> str:
        """Reload/mount every enabled storage backend (Admin only).

        Useful after changing storage configuration outside OpenList. Existing
        mounts are re-initialized, which may briefly interrupt access.

        Args:
            confirm: Must be true to actually reload. Defaults to false.

        Returns:
            Confirmation or error message.
        """
        if not confirm:
            return "⚠️ Storages not reloaded. Re-run with confirm=true to reload all."
        enforce_writable("load_all_storages")
        client = await get_client()
        await client.request("POST", "admin/storage/load_all")
        return "All enabled storages reloaded."

    # ─────────────────── Driver / download clients (write) ────────────────

    @mcp.tool()
    async def set_aria2(uri: str = "", secret: str = "", confirm: bool = False) -> str:
        """Configure the aria2 offline-download client (Admin only).

        Args:
            uri: aria2 RPC endpoint, e.g. "http://127.0.0.1:6800/jsonrpc".
            secret: Optional aria2 RPC secret token.
            confirm: Must be true to actually save. Defaults to false.

        Returns:
            Server response (usually the aria2 version) or error.
        """
        if not confirm:
            return "⚠️ aria2 not configured. Re-run with confirm=true to save."
        enforce_writable("set_aria2")
        if not uri.strip():
            return json.dumps(
                {"ok": False, "error": "uri is required (e.g. http://127.0.0.1:6800/jsonrpc)."}
            )
        data = await _save_driver_config(
            "admin/setting/set_aria2", {"uri": uri.strip(), "secret": secret}
        )
        return f"aria2 configured. Server: {json.dumps(data, ensure_ascii=False)}"

    @mcp.tool()
    async def set_qbittorrent(url: str = "", seedtime: str = "", confirm: bool = False) -> str:
        """Configure the qBittorrent offline-download client (Admin only).

        Args:
            url: qBittorrent WebUI URL, e.g. "http://127.0.0.1:8080".
            seedtime: Seed time in minutes (0 = unlimited).
            confirm: Must be true to actually save. Defaults to false.

        Returns:
            Confirmation or error message.
        """
        if not confirm:
            return "⚠️ qBittorrent not configured. Re-run with confirm=true to save."
        enforce_writable("set_qbittorrent")
        if not url.strip():
            return json.dumps(
                {"ok": False, "error": "url is required (e.g. http://127.0.0.1:8080)."}
            )
        data = await _save_driver_config(
            "admin/setting/set_qbit", {"url": url.strip(), "seedtime": seedtime}
        )
        return f"qBittorrent configured. Server: {json.dumps(data, ensure_ascii=False)}"

    @mcp.tool()
    async def set_transmission(uri: str = "", seedtime: str = "", confirm: bool = False) -> str:
        """Configure the Transmission offline-download client (Admin only).

        Args:
            uri: Transmission RPC URI, e.g. "http://127.0.0.1:9091/transmission/rpc".
            seedtime: Seed time in minutes (0 = unlimited).
            confirm: Must be true to actually save. Defaults to false.

        Returns:
            Confirmation or error message.
        """
        if not confirm:
            return "⚠️ Transmission not configured. Re-run with confirm=true to save."
        enforce_writable("set_transmission")
        if not uri.strip():
            return json.dumps(
                {
                    "ok": False,
                    "error": "uri is required (e.g. http://127.0.0.1:9091/transmission/rpc).",
                }
            )
        data = await _save_driver_config(
            "admin/setting/set_transmission", {"uri": uri.strip(), "seedtime": seedtime}
        )
        return f"Transmission configured. Server: {json.dumps(data, ensure_ascii=False)}"

    # (temp_dir-style setters are defined explicitly below for unique tool names)
