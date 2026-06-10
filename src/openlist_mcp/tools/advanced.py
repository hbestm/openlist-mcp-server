"""Advanced file operation tools for OpenList MCP Server.

Includes offline download, archive decompression, and related utilities.
"""

from __future__ import annotations

import base64
import contextlib
import ipaddress
import json
import os
import posixpath
import socket
from typing import Any
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP

from ..client import OpenListError, get_client
from ..config import get_config
from . import (
    enforce_path_allowed,
    enforce_writable,
    normalize_names,
    validate_name,
    validate_path,
)


def _human_size(size_bytes: int) -> str:
    """Format a byte count as a human-readable string."""
    if size_bytes == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = 0
    size = float(size_bytes)
    while size >= 1024 and i < len(units) - 1:
        size /= 1024
        i += 1
    return f"{size:.1f} {units[i]}"


# Internal IP ranges that should be blocked for SSRF prevention.
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),  # loopback
    ipaddress.ip_network("10.0.0.0/8"),  # RFC 1918
    ipaddress.ip_network("172.16.0.0/12"),  # RFC 1918
    ipaddress.ip_network("192.168.0.0/16"),  # RFC 1918
    ipaddress.ip_network("169.254.0.0/16"),  # link-local
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 unique-local
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]

# URL schemes allowed for offline download. Add new protocols here.
_SAFE_SCHEMES = {"http", "https", "magnet", "ftp", "sftp"}


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP address string belongs to a private/internal network."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(addr in network for network in _PRIVATE_NETWORKS)


def _reject_internal_url(url: str) -> None:
    """Reject URLs that resolve to internal/private IP addresses (SSRF prevention).

    Resolves the hostname to IP address(es) and raises ValueError if any
    resolved IP is in a private or loopback range.
    """
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise ValueError(f"URL has no hostname: {url}")

    # Direct IP check first (no DNS lookup needed)
    try:
        ipaddress.ip_address(host)
        if _is_private_ip(host):
            raise ValueError(
                f"URL points to a private/internal IP address ({host}), "
                "which is not allowed for security reasons."
            )
        # Public IP is fine, no need for DNS resolution
        return
    except ValueError:
        # Not a bare IP — resolve the hostname
        pass

    # DNS resolution for hostnames
    try:
        addrinfo = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise ValueError(
            f"Cannot resolve hostname '{host}' for SSRF check: {exc}. "
            f"If this is a valid external host, try again or use a direct IP URL."
        ) from exc

    for info in addrinfo:
        ip_str = str(info[4][0])
        if _is_private_ip(ip_str):
            raise ValueError(
                f"URL resolves to a private/internal IP address ({ip_str}), "
                "which is not allowed for security reasons."
            )


def register_advanced_tools(mcp: FastMCP) -> None:
    """Register advanced file operation MCP tools."""

    @mcp.tool()
    async def get_capabilities() -> str:
        """Summarize this MCP server's OpenList capabilities and safety settings.

        Returns public server settings, the authenticated user profile when available,
        configured offline download tools, and local MCP safety configuration.
        Use this before high-impact operations to understand what the server supports.
        """
        config = get_config()
        client = await get_client()

        # Best-effort: each endpoint can fail independently
        public_settings = {}
        with contextlib.suppress(Exception):
            public_settings = await client.request(
                "GET",
                "public/settings",
                require_auth=False,
            )

        user = None
        with contextlib.suppress(Exception):
            user = await client.request("GET", "me")

        download_tools = []
        with contextlib.suppress(Exception):
            download_tools_data = await client.request(
                "GET",
                "public/offline_download_tools",
                require_auth=False,
            )
            download_tools = (
                download_tools_data
                if isinstance(download_tools_data, list)
                else download_tools_data.get(
                    "value",
                    download_tools_data.get("data", []),
                )
            )

        capabilities = {
            "server": {
                "base_url": config.base_url,
                "uses_https": config.base_url.startswith("https://"),
                "public_settings": public_settings,
            },
            "authentication": {
                "credentials_configured": config.is_authenticated,
                "totp_secret_configured": config.has_totp_secret,
                "user": user,
            },
            "features": {
                "file_browse": True,
                "file_manage": True,
                "file_transfer": True,
                "shares": True,
                "tasks": True,
                "offline_download_tools": download_tools,
                "archive_decompress": True,
            },
            "mcp_safety": {
                "high_impact_operations_require_confirm": True,
                "read_only": config.read_only,
                "allowed_paths": config.allowed_paths,
                "local_upload_roots_configured": bool(
                    os.environ.get("OPENLIST_LOCAL_UPLOAD_ROOTS", "")
                ),
            },
        }
        return json.dumps(capabilities, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def offline_download(
        url: str,
        path: str = "/",
        tool: str = "aria2",
        delete_policy: str = "",
    ) -> str:
        """Download a file from a remote URL directly to the OpenList server.

        The server fetches the file in the background. Use get_task_info with the
        returned task ID to monitor progress.

        Available download tools on the server can be queried via `list_download_tools`.
        Common options include: "aria2" (supports http/https/magnet/torrent),
        "qbittorrent" (BitTorrent/HTTP), "transmission" (BitTorrent/HTTP).

        Args:
            url: Remote URL to download from.
            path: Destination directory on OpenList (e.g. "/downloads"). Defaults to root.
            tool: Download tool name. Defaults to "aria2". Use `list_download_tools`
                  to see what's available on this server.
            delete_policy: Optional delete policy for completed tasks.

        Returns:
            JSON string with created task info.
        """
        enforce_path_allowed(path)
        enforce_writable("offline_download")

        # SSRF prevention: only allow http/https/magnet URLs
        parsed = urlparse(url)
        if parsed.scheme not in _SAFE_SCHEMES:
            raise ValueError(
                f"Unsupported URL scheme '{parsed.scheme}'. "
                "Only http, https, magnet, ftp, and sftp URLs are allowed for offline download."
            )

        # SSRF prevention: reject URLs pointing to internal/private networks
        # Magnet links have no hostname and can't be used for SSRF, skip check
        if parsed.scheme != "magnet":
            _reject_internal_url(url)

        client = await get_client()
        body: dict[str, Any] = {"urls": [url], "path": path}
        if tool:
            body["tool"] = tool
        if delete_policy:
            body["delete_policy"] = delete_policy

        data = await client.request("POST", "fs/add_offline_download", json=body)
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def batch_download(
        urls: list[str],
        path: str = "/",
        tool: str = "aria2",
        delete_policy: str = "",
    ) -> str:
        """Download multiple files from remote URLs at once.

        Each URL is added as a separate offline download task. Use
        `list_tasks` or `get_task_info` to monitor progress.

        Args:
            urls: List of remote URLs to download.
            path: Destination directory on OpenList (e.g. "/downloads").
            tool: Download tool name. Defaults to "aria2".
            delete_policy: Optional delete policy for completed tasks.

        Returns:
            JSON string with results for each URL.
        """
        enforce_path_allowed(path)
        enforce_writable("batch_download")

        if not urls:
            return json.dumps({"ok": False, "error": "No URLs provided."}, ensure_ascii=False)

        # SSRF check for each URL
        for url in urls:
            parsed = urlparse(url)
            if parsed.scheme not in _SAFE_SCHEMES:
                raise ValueError(
                    f"Unsupported URL scheme '{parsed.scheme}' in '{url}'. "
                    "Only http, https, magnet, ftp, and sftp URLs are allowed."
                )
            if parsed.scheme != "magnet":
                _reject_internal_url(url)

        client = await get_client()
        results = []
        for url in urls:
            try:
                body: dict[str, Any] = {"urls": [url], "path": path}
                if tool:
                    body["tool"] = tool
                if delete_policy:
                    body["delete_policy"] = delete_policy
                data = await client.request("POST", "fs/add_offline_download", json=body)
                results.append({"url": url, "status": "created", "result": data})
            except Exception as e:
                results.append({"url": url, "status": "failed", "error": str(e)})

        return json.dumps(results, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def find_duplicates(
        path: str = "/",
        by: str = "name_size",
        password: str = "",
    ) -> str:
        """Find potentially duplicate files in a directory tree.

        Groups files by name+size (default) or by size only, and returns
        groups with more than one member as potential duplicates.

        Args:
            path: Directory to search. Defaults to "/".
            by: Grouping criteria: "name_size" (default) or "size_only".
            password: Password if the path is password-protected.

        Returns:
            JSON string with grouped potential duplicates.
        """
        client = await get_client()
        groups: dict[str, list[dict]] = {}
        seen = set()

        async def _walk(dir_path: str, depth: int = 0) -> None:
            if depth > 8:
                return
            if dir_path in seen:
                return
            seen.add(dir_path)

            items = await _list_items(client, dir_path, password)
            if not items:
                return

            for item in items:
                name = item["name"]
                size = item.get("size", 0) or 0
                typ = item.get("type", "")
                is_dir = typ in (1, "dir", "folder")

                if is_dir:
                    sub_path = f"{dir_path.rstrip('/')}/{name}"
                    await _walk(sub_path, depth + 1)
                else:
                    # Build group key
                    key = f"size:{size}" if by == "size_only" else f"{name}:{size}"

                    entry = {"path": f"{dir_path.rstrip('/')}/{name}", "size": size}
                    if key not in groups:
                        groups[key] = []
                    groups[key].append(entry)

        await _walk(path)

        # Filter groups with more than one entry
        duplicates = {k: v for k, v in groups.items() if len(v) > 1}

        result = {
            "path": path,
            "group_by": by,
            "total_duplicate_groups": len(duplicates),
            "total_duplicate_files": sum(len(v) for v in duplicates.values()),
            "duplicates": [
                {
                    "key": k,
                    "files": v,
                    "count": len(v),
                    "size": v[0]["size"],
                    "size_human": _human_size(v[0]["size"]),
                }
                for k, v in sorted(duplicates.items(), key=lambda x: -len(x[1]))
            ],
        }
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def content_preview(
        path: str,
        max_chars: int = 5000,
        password: str = "",
    ) -> str:
        """Preview the first portion of a text file's content.

        Useful for quickly inspecting log files, CSV data, source code,
        configuration files, or other text-based files without downloading
        the entire file. Fetches the raw content via download URL.

        For binary files or very large files, the preview may be truncated.

        Args:
            path: Full path to the file to preview.
            max_chars: Maximum number of characters to return. Defaults to 5000.
            password: Password if the path is password-protected.

        Returns:
            The file content preview as plain text, or an error message.
        """
        enforce_path_allowed(path)
        client = await get_client()

        # Get the file info to find raw_url
        data = await client.request(
            "POST",
            "fs/get",
            json={"path": path, "password": password},
        )
        raw_url = data.get("raw_url", "") if isinstance(data, dict) else ""

        if not raw_url:
            return json.dumps(
                {"ok": False, "error": "No download URL available for this file."},
                ensure_ascii=False,
            )

        # Fetch with range to limit bytes
        import httpx

        try:
            async with httpx.AsyncClient(timeout=15) as hc:
                resp = await hc.get(raw_url, headers={"Range": f"bytes=0-{max_chars * 2}"})
                content_bytes = resp.content
        except Exception as e:
            return json.dumps(
                {"ok": False, "error": f"Failed to fetch content: {e}"},
                ensure_ascii=False,
            )

        # Try to decode as text
        try:
            text = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = content_bytes.decode("latin-1")
            except Exception:
                return json.dumps(
                    {"ok": False, "error": "File is binary — cannot preview as text."},
                    ensure_ascii=False,
                )

        # Truncate
        if len(text) > max_chars:
            text = text[:max_chars] + "\n... (truncated)"

        # Wrap in a code block for readability
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        lang_map = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "html": "html",
            "css": "css",
            "json": "json",
            "xml": "xml",
            "yaml": "yaml",
            "yml": "yaml",
            "md": "markdown",
            "sh": "bash",
            "bash": "bash",
            "csv": "csv",
            "txt": "text",
        }
        lang = lang_map.get(ext, "")

        result = {
            "path": path,
            "total_bytes": len(content_bytes),
            "preview_chars": len(text),
            "preview": text,
            "language": lang,
        }
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def get_archive_extensions() -> str:
        """Get the list of archive file extensions supported by the server.

        Helps determine which archive formats can be decompressed (zip, rar,
        7z, tar.gz, etc.).

        Returns:
            JSON list of supported extensions.
        """
        client = await get_client()
        data = await client.request("GET", "public/archive_extensions", require_auth=False)
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def get_archive_meta(
        path: str,
        archive_pass: str = "",
        refresh: bool = False,
    ) -> str:
        """Get metadata of an archive file without extracting it.

        Returns format, encryption status, comment, file structure,
        and download URL information for the archive.

        Args:
            path: Full path to the archive file (e.g. "/downloads/data.zip").
            archive_pass: Optional password for encrypted archives.
            refresh: Whether to refresh archive cache.

        Returns:
            JSON string with archive metadata including format, encryption status,
            file tree, and direct download info.
        """
        enforce_path_allowed(path)

        client = await get_client()
        body: dict[str, Any] = {
            "path": path,
            "refresh": refresh,
        }
        if archive_pass:
            body["archive_pass"] = archive_pass

        data = await client.request("POST", "fs/archive/meta", json=body)
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def decompress_archive(
        src_dir: str,
        names: list[str] | str,
        dst_dir: str = "",
        archive_pass: str = "",
        overwrite: bool = False,
        put_into_new_dir: bool = False,
    ) -> str:
        """Decompress an archive file (zip, rar, 7z, tar.gz, etc.) on the OpenList server.

        The archive file must already exist on the server.

        Args:
            src_dir: Directory containing the archive file(s) (e.g. "/downloads").
            names: List of archive filenames or comma-separated string to decompress
                   (e.g. ["data.zip", "backup.7z"] or "data.zip,backup.7z").
            dst_dir: Optional extraction target directory. Defaults to same as src_dir.
            archive_pass: Optional password for encrypted archives.
            overwrite: Whether to overwrite existing files. Defaults to false.
            put_into_new_dir: Whether to place extracted files in a new directory named after the archive. Defaults to false.

        Returns:
            JSON string with decompression result.
        """
        enforce_path_allowed(src_dir)
        enforce_writable("decompress_archive")
        name_list = normalize_names(names)
        if not name_list:
            return json.dumps(
                {"ok": False, "error": "No archive files specified."},
                ensure_ascii=False,
            )

        client = await get_client()
        body: dict[str, Any] = {
            "src_dir": src_dir,
            "name": name_list,
            "overwrite": overwrite,
            "put_into_new_dir": put_into_new_dir,
        }
        if dst_dir:
            enforce_path_allowed(dst_dir)
            body["dst_dir"] = dst_dir
        if archive_pass:
            body["archive_pass"] = archive_pass

        data = await client.request("POST", "fs/archive/decompress", json=body)
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def list_archive_files(
        src_dir: str,
        name: str,
        inner_path: str = "/",
        archive_pass: str = "",
        refresh: bool = False,
    ) -> str:
        """List files inside an archive without extracting it.

        Args:
            src_dir: Directory containing the archive file.
            name: Archive filename, not a full path.
            inner_path: Inner archive directory to list. Defaults to "/".
            archive_pass: Optional password for encrypted archives.
            refresh: Whether to refresh archive cache when supported by OpenList.

        Returns:
            JSON string containing archive entries.
        """
        enforce_path_allowed(src_dir)
        validate_name(name)
        validate_path(inner_path)
        archive_path = posixpath.join(src_dir.rstrip("/"), name)
        client = await get_client()
        body: dict[str, Any] = {
            "path": archive_path,
            "inner_path": inner_path,
            "refresh": refresh,
        }
        if archive_pass:
            body["archive_pass"] = archive_pass

        data = await client.request("POST", "fs/archive/list", json=body)
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def get_me() -> str:
        """Get the current authenticated user's profile information.

        Returns user details including username, role, permissions, and 2FA status.
        """
        client = await get_client()
        data = await client.request("GET", "me")
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def logout() -> str:
        """Logout from the OpenList server and invalidate the current token.

        After logout, the next API call will trigger automatic re-login
        using configured credentials.
        """
        client = await get_client()
        await client.request("GET", "auth/logout")
        # Clear the cached token via the public method
        client.clear_token()
        return "Logged out successfully. Token invalidated."

    @mcp.tool()
    async def list_download_tools() -> str:
        """List available offline download tools configured on this OpenList server.

        The result depends on which download tools (aria2, Transmission, qBittorrent, etc.)
        are installed and configured on the OpenList server. Only tools that are
        properly set up will appear in the list.

        Returns:
            JSON array of available download tool names.
        """
        client = await get_client()
        data = await client.request("GET", "public/offline_download_tools", require_auth=False)
        tools = data if isinstance(data, list) else data.get("value", data.get("data", []))
        return json.dumps(tools, ensure_ascii=False)

    @mcp.tool()
    async def parse_torrent(
        torrent_data: str,
    ) -> str:
        """Parse a torrent file and return its contents (file list, metadata).

        Provide the torrent file content as a base64-encoded string.
        Returns information about the torrent including file names, sizes,
        piece count, and whether the storage backend supports rapid upload.

        Args:
            torrent_data: Base64-encoded content of the .torrent file.

        Returns:
            JSON string with parsed torrent info including file list.
        """
        client = await get_client()
        data = await client.request(
            "POST",
            "fs/torrent/parse",
            json={"torrent_data": torrent_data},
        )
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def torrent_upload_parse(
        torrent_data: str,
    ) -> str:
        """Upload and parse a torrent file via multipart form.

        Unlike parse_torrent (which sends base64 in JSON body), this sends the
        torrent file as a multipart form upload — matching how the OpenList
        web UI handles torrent files. The server returns parsed metadata plus
        a base64-encoded copy of the torrent data that can be fed directly
        into torrent_rapid_upload.

        Args:
            torrent_data: Base64-encoded content of the .torrent file.

        Returns:
            JSON string with parsed torrent info (name, files, info_hash, etc.)
            plus a 'torrent_data' field for reuse in rapid upload.
        """

        client = await get_client()
        raw_bytes = base64.b64decode(torrent_data)
        data = await client.multipart_form(
            "fs/torrent/upload_parse",
            field_name="torrent",
            file_bytes=raw_bytes,
            file_name="file.torrent",
            content_type="application/x-bittorrent",
        )
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def generate_torrent(
        path: str,
    ) -> str:
        """Generate a .torrent file for an existing file on the OpenList server.

        Creates a BitTorrent metainfo file that can be used to share the file
        via BitTorrent. The generated torrent is stored alongside the original file.

        Args:
            path: Full path to the file on OpenList (e.g. "/downloads/myfile.iso").

        Returns:
            JSON string with generation result and path to the .torrent file.
        """
        enforce_path_allowed(path)
        enforce_writable("generate_torrent")
        client = await get_client()
        data = await client.request(
            "POST",
            "fs/torrent/generate",
            json={"path": path},
        )
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def torrent_rapid_upload(
        torrent_data: str,
        path: str = "/",
    ) -> str:
        """Rapid upload (server-side import) from a torrent file.

        If the storage backend supports CAS (Content Addressable Storage)
        and already has the files referenced in the torrent, this can complete
        instantly without downloading. This feature depends on the storage
        driver — local storage typically does not support CAS.

        Falls back to a normal message if CAS is not available on the backend.

        Args:
            torrent_data: Base64-encoded content of the .torrent file.
            path: Destination directory path on OpenList (e.g. "/downloads").

        Returns:
            JSON string with the upload/task result, or a message explaining
            that CAS/rapid upload is not supported on this storage backend.
        """
        enforce_writable("torrent_rapid_upload")
        enforce_path_allowed(path)
        client = await get_client()
        data = await client.request(
            "POST",
            "fs/torrent/rapid_upload",
            json={"torrent_data": torrent_data, "path": path},
        )
        return json.dumps(data, indent=2, ensure_ascii=False)
