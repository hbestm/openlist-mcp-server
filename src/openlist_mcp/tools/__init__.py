"""OpenList MCP Tools package."""

import posixpath

from ..config import get_config


def validate_path(path: str) -> None:
    """Validate that a path does not contain directory traversal sequences.

    Rejects paths with '..' as a path component to prevent directory traversal.
    Unlike a simple substring match, this only rejects '..' when it appears
    as a standalone component between separators, allowing legitimate names
    like 'backup..2024.tar.gz' or '/foo.v2/bar'.
    """
    if not path:
        raise ValueError("Path must not be empty")

    normalized_separators = path.replace("\\", "/")

    # Check each path component - reject only exact '..', not filenames containing '..'
    parts = normalized_separators.split("/")
    if ".." in parts:
        raise ValueError(f"Path must not contain directory traversal: {path}")

    # OpenList paths are URL/POSIX-style paths, even when the MCP server runs on Windows.
    normalized = posixpath.normpath(normalized_separators)
    if normalized_separators == "/":
        return
    if normalized_separators != normalized:
        raise ValueError(f"Path must not contain unsafe path components: {path}")


def enforce_path_allowed(path: str) -> None:
    """Validate a path and enforce optional MCP path allowlist."""
    validate_path(path)
    config = get_config()
    allowed_paths = config.allowed_paths
    if not allowed_paths:
        return

    normalized = path.replace("\\", "/")
    if normalized != "/":
        normalized = posixpath.normpath(normalized)

    for allowed in allowed_paths:
        if allowed == "/" or normalized == allowed or normalized.startswith(f"{allowed}/"):
            return
    raise PermissionError(
        f"Path is outside OPENLIST_ALLOWED_PATHS: {path}. Allowed paths: {', '.join(allowed_paths)}"
    )


def enforce_writable(operation: str) -> None:
    """Block write/high-impact tools when OPENLIST_READONLY is enabled."""
    if get_config().read_only:
        raise PermissionError(f"{operation} is disabled because OPENLIST_READONLY is enabled")


def validate_name(name: str) -> None:
    """Validate that a name is a single file/folder name, not a path."""
    if not name:
        raise ValueError("Name must not be empty")
    if name in (".", ".."):
        raise ValueError(f"Name must not be current or parent directory: {name}")
    if "/" in name or "\\" in name:
        raise ValueError(f"Name must not contain path separators: {name}")


def normalize_names(names: list[str] | str) -> list[str]:
    """Normalize and validate one or more filename-only values."""
    if isinstance(names, str):
        name_list = [name.strip() for name in names.split(",") if name.strip()]
    else:
        name_list = [name.strip() for name in names if name.strip()]

    for name in name_list:
        validate_name(name)
    return name_list


def validate_pagination(page: int, per_page: int, max_per_page: int = 200) -> None:
    """Validate pagination values before forwarding them to OpenList."""
    if page < 1:
        raise ValueError("page must be greater than or equal to 1")
    if per_page < 1 or per_page > max_per_page:
        raise ValueError(f"per_page must be between 1 and {max_per_page}")


async def _list_items(client, path: str, password: str = ""):
    """List items in a directory, returning parsed items or empty list on error."""
    try:
        data = await client.request("POST", "fs/list", json={"path": path, "page": 1, "per_page": 200, "password": password})
        items = data.get("content", data.get("value", []))
        if not isinstance(items, list):
            items = []
        return items
    except Exception:
        return []

def _human_size(size_bytes: int) -> str:
    """Format a byte count as a human-readable string."""
    if size_bytes == 0:
        return '0 B'
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = 0
    size = float(size_bytes)
    while size >= 1024 and i < len(units) - 1:
        size /= 1024
        i += 1
    return f"{size:.1f} {units[i]}"
